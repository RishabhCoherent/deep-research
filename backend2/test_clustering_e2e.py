"""End-to-end test for the new hybrid claim extraction + clustering pipeline.

Runs:
  1. numeric_prefilter (Stage 1, deterministic) on fixture passages.
  2. _structure_claims_batched (Stage 2, LLM) — REAL Anthropic Haiku calls.
  3. cluster_numeric_claims (clustering) on the structured claims.

Reports:
  - Prefilter candidate count.
  - LLM-structured claim count.
  - Cluster size distribution.
  - Wall-clock time per stage.
  - Token usage + estimated USD cost (Anthropic Haiku 3.5 rates).

Usage:
    cd backend2 && python test_clustering_e2e.py
    cd backend2 && python test_clustering_e2e.py --fixture clustering_test_runs/<slug>/run.json
    cd backend2 && python test_clustering_e2e.py --provider openai     # force OpenAI
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


# ── Provider & token-tracking setup (must run BEFORE importing agent code) ──

def _select_provider(force: str | None) -> str:
    if force:
        os.environ["LLM_PROVIDER"] = force
        return force
    return os.environ.get("LLM_PROVIDER", "anthropic")


# Anthropic Haiku 3.5 list pricing (Apr 2026): $1.00/MTok input, $5.00/MTok output.
# OpenAI gpt-4o-mini: $0.15/MTok input, $0.60/MTok output.
_PRICES_PER_MTOK = {
    "anthropic": {"in": 1.00, "out": 5.00},
    "openai":    {"in": 0.15, "out": 0.60},
}


class TokenTracker:
    """LangChain callback that accumulates input/output tokens across calls."""
    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.n_calls = 0

    def on_llm_end(self, response, **_kwargs):  # langchain BaseCallbackHandler hook
        try:
            for gen_list in response.generations:
                for gen in gen_list:
                    msg = getattr(gen, "message", None)
                    usage = getattr(msg, "usage_metadata", None) if msg else None
                    if usage:
                        self.input_tokens += int(usage.get("input_tokens", 0) or 0)
                        self.output_tokens += int(usage.get("output_tokens", 0) or 0)
                        self.n_calls += 1
                        continue
                    # Fallback: response.llm_output dict (anthropic + openai both populate)
                    info = getattr(gen, "generation_info", None) or {}
                    if "usage" in info:
                        u = info["usage"]
                        self.input_tokens += int(u.get("input_tokens", u.get("prompt_tokens", 0)) or 0)
                        self.output_tokens += int(u.get("output_tokens", u.get("completion_tokens", 0)) or 0)
                        self.n_calls += 1
        except Exception:
            pass

    # Required no-op hooks (BaseCallbackHandler abstract)
    def on_llm_start(self, *_a, **_k): pass
    def on_chain_start(self, *_a, **_k): pass
    def on_chain_end(self, *_a, **_k): pass
    def on_chain_error(self, *_a, **_k): pass
    def on_tool_start(self, *_a, **_k): pass
    def on_tool_end(self, *_a, **_k): pass
    def on_tool_error(self, *_a, **_k): pass
    def on_text(self, *_a, **_k): pass
    def on_agent_action(self, *_a, **_k): pass
    def on_agent_finish(self, *_a, **_k): pass
    def on_llm_new_token(self, *_a, **_k): pass
    def on_llm_error(self, *_a, **_k): pass

    def cost_usd(self, provider: str) -> float:
        rates = _PRICES_PER_MTOK.get(provider, _PRICES_PER_MTOK["anthropic"])
        return (self.input_tokens / 1_000_000) * rates["in"] + \
               (self.output_tokens / 1_000_000) * rates["out"]


def _install_tracker(tracker: TokenTracker) -> None:
    """Monkey-patch model_router so every haiku() / sonnet() call returns an
    LLM with the tracker attached. Must run before agents are built."""
    from research.api import model_router as mr
    _orig_haiku = mr.haiku
    _orig_sonnet = mr.sonnet
    _orig_opus = mr.opus

    def _wrap(orig):
        def wrapped(*args, **kwargs):
            llm = orig(*args, **kwargs)
            existing = list(getattr(llm, "callbacks", None) or [])
            llm.callbacks = existing + [tracker]
            return llm
        return wrapped

    mr.haiku = _wrap(_orig_haiku)
    mr.sonnet = _wrap(_orig_sonnet)
    mr.opus = _wrap(_orig_opus)


# ── Fixture loading ────────────────────────────────────────────────────────

def _load_passages_from_fixture(path: Path) -> tuple[list, str]:
    """Reconstruct synthetic Passages from a clustering_test_runs/ run.json.
    Each unique source_url becomes one Passage; raw_texts are concatenated."""
    from research.core.types import Passage, AuthorityTier

    raw = json.loads(path.read_text(encoding="utf-8"))
    topic = raw.get("topic") or path.stem

    by_url: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"title": "", "tier": "blog", "texts": []}
    )
    for est in raw.get("estimates", []):
        for c in est.get("claims") or []:
            url = c.get("source_url") or ""
            if not url:
                continue
            slot = by_url[url]
            slot["title"] = c.get("source_title") or slot["title"]
            slot["tier"] = c.get("source_tier") or slot["tier"]
            text = (c.get("raw_text") or "").strip()
            if text and text not in slot["texts"]:
                slot["texts"].append(text)

    passages: list[Passage] = []
    for url, info in by_url.items():
        full_text = " ".join(info["texts"])
        try:
            tier = AuthorityTier(info["tier"]) if info["tier"] else AuthorityTier.BLOG
        except ValueError:
            tier = AuthorityTier.BLOG
        passages.append(Passage(
            url=url,
            title=info["title"] or "(untitled)",
            text=full_text,
            authority_tier=tier,
        ))
    return passages, topic


def _load_baseline_claims_from_fixture(path: Path):
    """Reconstruct the ORIGINAL pipeline's NumericClaims directly from the
    fixture's RawClaim entries. Used for a side-by-side baseline comparison
    with the new hybrid pipeline."""
    from research.core.types import NumericClaim, Citation, AuthorityTier
    raw = json.loads(path.read_text(encoding="utf-8"))
    claims = []
    for est in raw.get("estimates", []):
        for c in est.get("claims") or []:
            try:
                tier = AuthorityTier(c.get("source_tier", "blog"))
            except ValueError:
                tier = AuthorityTier.BLOG
            claims.append(NumericClaim(
                metric=est.get("dimension", {}).get("descriptor", "")[:120] or "(metric)",
                value=float(c.get("value", 0.0) or 0.0),
                unit=c.get("unit_raw", "") or "",
                as_of=str(c.get("published_at", "")) or None,
                scope=None,
                raw_excerpt=c.get("raw_text", "") or "",
                citation=Citation(
                    url=c.get("source_url", ""),
                    title=c.get("source_title"),
                    authority_tier=tier,
                ),
                qualifiers=c.get("qualifiers") or {},
            ))
    return claims


# ── Main ────────────────────────────────────────────────────────────────────

async def _amain(args) -> int:
    provider = _select_provider(args.provider)
    print(f"[harness] provider: {provider}")

    tracker = TokenTracker()
    _install_tracker(tracker)

    # Imports AFTER provider + tracker setup so they pick up the env override.
    from research.crews.a3_topic_researcher.numeric_prefilter import find_numeric_candidates
    from research.crews.a3_topic_researcher.crew import _structure_claims_batched
    from research.crews.a3_topic_researcher.agents import build_agents
    from research.clustering import cluster_numeric_claims

    fixture_path = Path(args.fixture)
    if not fixture_path.exists():
        print(f"[harness] ERROR: fixture not found: {fixture_path}")
        return 1
    print(f"[harness] fixture: {fixture_path}")

    passages, topic = _load_passages_from_fixture(fixture_path)
    print(f"[harness] topic:   {topic[:90]}")
    print(f"[harness] {len(passages)} passages reconstructed "
          f"(total {sum(len(p.text) for p in passages)} chars)")

    # ── Stage 1: prefilter ─────────────────────────────────────────────────
    t0 = time.perf_counter()
    candidates = find_numeric_candidates(passages)
    t_prefilter = time.perf_counter() - t0
    print(f"\n[stage 1] prefilter: {len(candidates)} candidates in {t_prefilter:.2f}s")

    if not candidates:
        print("[harness] no candidates — nothing to structure")
        return 1

    # ── Stage 2: LLM structurer ────────────────────────────────────────────
    _, claim_extractor, _ = build_agents()
    passage_map_for_llm = {
        str(i): {
            "url": p.url,
            "title": p.title,
            "publisher": p.publisher,
            "published": p.published,
            "accessed": p.accessed,
            "authority_tier": p.authority_tier.value if p.authority_tier else "blog",
        }
        for i, p in enumerate(passages)
    }
    t0 = time.perf_counter()
    usage: dict = {}
    structured = await _structure_claims_batched(
        extractor=claim_extractor,
        chosen_query=topic,
        candidates=candidates,
        passage_map_for_llm=passage_map_for_llm,
        topic_profile_block="TOPIC PROFILE: (none provided)",
        usage_acc=usage,
    )
    t_structure = time.perf_counter() - t0

    # CrewAI's UsageMetrics keys: prompt_tokens / completion_tokens / total_tokens.
    # Map onto our tracker for unified reporting.
    tracker.input_tokens  = int(usage.get("prompt_tokens", 0) or 0)
    tracker.output_tokens = int(usage.get("completion_tokens", 0) or 0)
    tracker.n_calls       = int(usage.get("successful_requests", 0) or 0)

    print(f"[stage 2] structurer: {len(structured.claims)} claims in {t_structure:.2f}s "
          f"({tracker.n_calls} LLM calls, "
          f"{tracker.input_tokens} in / {tracker.output_tokens} out tokens)")

    # ── Stage 2b: validators (verbatim + citation) ─────────────────────────
    from research.crews.a3_topic_researcher.extractor_validators import (
        assert_excerpts_in_passages, assert_citation_complete
    )
    valid = assert_excerpts_in_passages(structured.claims, passages)
    valid = assert_citation_complete(valid)
    n_dropped = len(structured.claims) - len(valid)
    print(f"[stage 2b] verbatim/citation validation: {len(valid)} kept, "
          f"{n_dropped} dropped ({100 * (n_dropped/len(structured.claims)) if structured.claims else 0:.1f}%)")

    # ── Stage 3: clustering ────────────────────────────────────────────────
    t0 = time.perf_counter()
    estimates = cluster_numeric_claims(
        valid,
        on_progress=lambda msg: print(f"  {msg}"),
    )
    t_cluster = time.perf_counter() - t0

    sizes = sorted([e.n_claims for e in estimates], reverse=True)
    multi_source = sum(1 for e in estimates if e.n_unique_sources >= 2)
    five_plus = sum(1 for s in sizes if s >= 5)
    median_size = sizes[len(sizes)//2] if sizes else 0
    print(f"\n[stage 3] clustering: {len(estimates)} clusters in {t_cluster:.2f}s")
    print(f"          multi-source: {multi_source}/{len(estimates)}")
    print(f"          5+ claims:    {five_plus}/{len(estimates)}  (target: most clusters here)")
    print(f"          top sizes:    {sizes[:10]}")
    print(f"          median size:  {median_size}")

    # ── Cluster size distribution ──────────────────────────────────────────
    size_dist = Counter(sizes)
    print(f"\n[cluster size distribution]")
    print(f"  size  count  cumulative")
    cumul = 0
    for size in sorted(size_dist.keys(), reverse=True):
        count = size_dist[size]
        cumul += count
        print(f"    {size:3d}    {count:3d}      {cumul:3d}")

    # ── Top 5 clusters by size ─────────────────────────────────────────────
    print(f"\n[top 5 clusters by size]")
    for est in sorted(estimates, key=lambda e: -e.n_claims)[:5]:
        print(f"  • {est.n_claims} claims, "
              f"{est.n_unique_sources} sources, "
              f"consensus={est.consensus_level}")
        print(f"    descriptor: {est.dimension.descriptor[:90]}")
        print(f"    weighted_mean: {est.weighted_mean:.4g} {est.dimension.unit_family}")

    # ── Baseline: cluster the fixture's original claims for comparison ─────
    baseline_claims = _load_baseline_claims_from_fixture(fixture_path)
    baseline_estimates = cluster_numeric_claims(baseline_claims)
    base_sizes = sorted([e.n_claims for e in baseline_estimates], reverse=True)
    base_multi = sum(1 for e in baseline_estimates if e.n_unique_sources >= 2)
    base_5plus = sum(1 for s in base_sizes if s >= 5)
    base_med   = base_sizes[len(base_sizes)//2] if base_sizes else 0

    print(f"\n[baseline vs new — same fixture]")
    print(f"  metric             baseline (LLM-only)   new (hybrid)")
    print(f"  claims                  {len(baseline_claims):3d}              {len(valid):3d}")
    print(f"  clusters                {len(baseline_estimates):3d}              {len(estimates):3d}")
    print(f"  multi-source            {base_multi:3d}              {multi_source:3d}")
    print(f"  ≥5 claims               {base_5plus:3d}              {five_plus:3d}")
    print(f"  median size             {base_med:3d}              {median_size:3d}")
    print(f"  top size                {base_sizes[0] if base_sizes else 0:3d}              {sizes[0] if sizes else 0:3d}")

    # ── Cost + time totals ─────────────────────────────────────────────────
    cost = tracker.cost_usd(provider)
    total_time = t_prefilter + t_structure + t_cluster
    print(f"\n[totals]")
    print(f"  wall time:   {total_time:.2f}s "
          f"(prefilter {t_prefilter:.2f}s + structure {t_structure:.2f}s + cluster {t_cluster:.2f}s)")
    print(f"  llm calls:   {tracker.n_calls}")
    print(f"  llm tokens:  {tracker.input_tokens} in / {tracker.output_tokens} out "
          f"(total {tracker.input_tokens + tracker.output_tokens:,})")
    rates = _PRICES_PER_MTOK.get(provider, _PRICES_PER_MTOK["anthropic"])
    print(f"  llm cost:    ${cost:.4f}  "
          f"(@ ${rates['in']:.2f}/MTok in, ${rates['out']:.2f}/MTok out — {provider})")

    print(f"\n[note] This fixture has {len(passages)} passages with only "
          f"{sum(len(p.text) for p in passages)} total chars — too sparse for")
    print(f"       cross-source consensus clusters (≥5). Real research runs fetch")
    print(f"       8K-char passages; expect 5-10× more candidates and bigger clusters.")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--fixture",
        default="clustering_test_runs/india-semiconductor-manufacturing-push-fab-investm/run.json",
        help="Path to a clustering_test_runs/<slug>/run.json fixture",
    )
    ap.add_argument(
        "--provider",
        choices=["anthropic", "openai"],
        default=None,
        help="Force LLM provider for this run (overrides .env)",
    )
    args = ap.parse_args()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
