"""A/B compare clustering modes on a SINGLE shared claim set.

Runs search + extract ONCE (the expensive part), then runs all 4 combinations
of (describer × clusterer) on the same claims:

    1. template + hash      (cheap, deterministic, no LLM/embeddings)
    2. template + cosine    (free descriptor + LLM judge in gray zone)
    3. llm      + hash      (gpt-4o descriptor + deterministic clustering)
    4. llm      + cosine    (current default — LLM both sides)

For each combo it produces:
    - clusters_<combo>.html   - the dark-themed viewer
    - run_<combo>.json        - full ClusteringRun

Plus one ab_summary.md in the run dir comparing all four:
    - cluster counts
    - multi-source counts
    - cost per stage
    - wall time
    - top-10 cluster overlap (Jaccard)

Usage:
    python -m claim_clustering.ab_compare "GPU market size 2024" --scale standard
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .aggregator import build_estimates
from .clusterer import cluster_claims, cluster_claims_hash
from .describer import describe_claims_template, _price_for_model
from .embedder import embed_claims
from .extractor import extract_from_sources
from .models import ClusteringRun, RawClaim
from .query_expander import expand_topic
from .pipeline import (
    SCALE_PRESETS, _trim_sources_to_budget, _estimate_extract_cost,
)
from .search import search_topic, search_multiple_queries, SourceDocument
from .validator import validate_and_split
from .visualise import write_html, write_json


# ── Combo definitions ───────────────────────────────────────────────────────

COMBOS = [
    ("template", "hash"),     # cheapest, fully deterministic
    ("template", "cosine"),
    # LLM describer combos were removed in Phase 3a — empirically the template
    # describer produced equivalent or better clusters at zero cost. Kept the
    # variable name `describer_mode` only as a no-op for back-compat.
]


def _label(describer: str, clusterer: str) -> str:
    return f"D-{describer}_C-{clusterer}"


# ── Run one combo over already-extracted claims ─────────────────────────────

def _run_combo(
    raw_claims_input: list[RawClaim],
    *,
    describer_mode: str,
    clusterer_mode: str,
    describer_model: str,
    judge_model: str,
    validate_clusters: bool,
    log,
) -> tuple[list, dict, dict]:
    """Returns (estimates, costs_dict, stats_dict)."""
    # Deep-copy claims so each combo gets a fresh starting state
    claims = [c.model_copy(deep=True) for c in raw_claims_input]
    costs: dict = {"describe": 0.0, "embed": 0.0, "judge": 0.0, "validate": 0.0}
    t_start = time.time()

    # Describe (template-only since Phase 3a)
    claims, costs["describe"] = describe_claims_template(claims, on_progress=log)

    # Embed (only for cosine)
    if clusterer_mode == "cosine":
        claims, costs["embed"] = embed_claims(claims, on_progress=log)

    # Cluster
    if clusterer_mode == "hash":
        protos, cstats = cluster_claims_hash(claims, on_progress=log)
    else:
        protos, cstats = cluster_claims(claims, judge_model=judge_model, on_progress=log)
    costs["judge"] = float(cstats.get("judge_cost_usd", 0.0))

    # Validate
    if validate_clusters:
        before = len(protos)
        protos = validate_and_split(protos, model=judge_model, on_progress=log)
        n_added = max(0, len(protos) - before)
        in_per_m, out_per_m = _price_for_model(judge_model)
        costs["validate"] = (n_added * 2500 / 1_000_000 * in_per_m
                             + n_added * 600 / 1_000_000 * out_per_m)

    # Aggregate
    estimates = build_estimates(protos, link_trends=True)

    elapsed = time.time() - t_start
    return estimates, costs, {**cstats, "elapsed_s": elapsed, "n_claims": len(claims)}


def _build_run_artefact(
    topic: str, started_at: str, sources: list[SourceDocument],
    raw_claims: list[RawClaim], estimates: list, costs: dict,
    cost_extract: float, cost_expand: float,
) -> ClusteringRun:
    cost_total = (cost_expand + cost_extract + costs["describe"] + costs["embed"]
                  + costs["judge"] + costs["validate"])
    return ClusteringRun(
        topic=topic,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc).isoformat(),
        n_sources_searched=len(sources),
        n_sources_with_claims=len({c.source_domain for c in raw_claims}),
        n_raw_claims=len(raw_claims),
        n_dimensions=len(estimates),
        estimates=estimates,
        cost_extract_usd=round(cost_extract, 5),
        cost_describe_usd=round(costs["describe"], 5),
        cost_embed_usd=round(costs["embed"], 5),
        cost_judge_usd=round(costs["judge"], 5),
        cost_validate_usd=round(costs["validate"], 5),
        cost_total_usd=round(cost_total, 5),
        search_calls=len(sources),
        scrape_bytes=sum(len(s.full_text) for s in sources),
        n_judge_calls=0,
    )


# ── Comparison metrics ──────────────────────────────────────────────────────

def _claim_id(c: RawClaim) -> str:
    """Stable id for a claim within one extraction (used for cluster Jaccard)."""
    return f"{c.source_url}::{(c.raw_text or '')[:80]}"


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / max(1, len(a | b))


def _cluster_signature(estimate, claim_id_fn=_claim_id) -> frozenset:
    return frozenset(claim_id_fn(c) for c in estimate.claims)


def _cluster_overlap_score(ests_a: list, ests_b: list, top_n: int = 20) -> float:
    """Average Jaccard across top-N matched cluster pairs (greedy match)."""
    sig_a = sorted([_cluster_signature(e) for e in ests_a],
                   key=lambda s: -len(s))[:top_n]
    sig_b = sorted([_cluster_signature(e) for e in ests_b],
                   key=lambda s: -len(s))[:top_n]
    if not sig_a or not sig_b:
        return 0.0
    used_b: set[int] = set()
    total = 0.0
    matched = 0
    for sa in sig_a:
        best_j = -1
        best_v = 0.0
        for j, sb in enumerate(sig_b):
            if j in used_b:
                continue
            v = _jaccard(sa, sb)
            if v > best_v:
                best_v = v
                best_j = j
        if best_j >= 0:
            used_b.add(best_j)
            total += best_v
            matched += 1
    return total / matched if matched else 0.0


# ── Main entry ──────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claim_clustering.ab_compare",
        description="A/B compare describer × clusterer combinations on the SAME claims.",
    )
    parser.add_argument("topic")
    parser.add_argument("--scale", choices=list(SCALE_PRESETS.keys()), default="standard")
    parser.add_argument("--sources", type=int, default=None)
    parser.add_argument("--max-per-query", type=int, default=None)
    parser.add_argument("--max-cost", type=float, default=None)
    parser.add_argument("--no-auto-expand", action="store_true", default=False)
    parser.add_argument("--no-validate", action="store_true", default=False)
    parser.add_argument("--describer-model", default="gpt-4o")
    parser.add_argument("--judge-model", default="gpt-4o-mini")
    parser.add_argument("--extractor-model", default="gpt-4o-mini")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--combos", default="all",
                        help="Comma-separated combo labels to run (default: all). "
                             "e.g. 'D-template_C-hash,D-llm_C-cosine'")
    args = parser.parse_args(argv)

    preset = SCALE_PRESETS[args.scale]
    max_sources = args.sources or preset["max_sources"]
    max_per_query = args.max_per_query or preset["max_per_query"]
    max_cost = args.max_cost if args.max_cost is not None else preset["max_cost"]

    # Output dir
    if args.out:
        out_dir = args.out
    else:
        slug = "".join(c if c.isalnum() or c in "-_ " else "" for c in args.topic).strip()
        slug = slug.replace(" ", "_")[:40] or "run"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path("claim_clustering") / "ab_runs" / f"{stamp}_{slug}"
    out_dir.mkdir(parents=True, exist_ok=True)

    selected_combos = COMBOS if args.combos == "all" else [
        tuple(c.replace("D-", "").split("_C-")) for c in args.combos.split(",")
    ]

    print(f"[ab] output dir: {out_dir}")
    print(f"[ab] running {len(selected_combos)} combos at scale={args.scale} "
          f"(max_sources={max_sources}, max_per_query={max_per_query}, "
          f"max_cost=${max_cost:.2f})")

    def log(msg: str) -> None:
        print(msg)

    # ── 1. Auto-expand ───────────────────────────────────────────────────────
    started_at = datetime.now(timezone.utc).isoformat()
    cost_expand = 0.0
    expanded: list[str] = []
    if not args.no_auto_expand:
        log("[ab/expand] auto-expanding topic...")
        expanded, cost_expand = expand_topic(args.topic, on_progress=log)

    # ── 2. Search ────────────────────────────────────────────────────────────
    log(f"[ab/search] querying {len(expanded) or 1} angles in parallel...")
    if expanded:
        sources = search_multiple_queries(expanded, max_per_query=max_per_query)
    else:
        sources = search_topic(args.topic, max_sources=max_sources)
    if len(sources) > max_sources:
        sources = sources[:max_sources]
    sources = _trim_sources_to_budget(sources, max_cost, log)
    log(f"[ab/search] {len(sources)} sources after trim, "
        f"{sum(1 for s in sources if s.has_content)} with content")

    # ── 3. Extract (once, shared by all combos) ──────────────────────────────
    log(f"[ab/extract] extracting claims via {args.extractor_model}...")
    raw_claims = extract_from_sources(sources, model=args.extractor_model)
    cost_extract = _estimate_extract_cost(sources, args.extractor_model)
    log(f"[ab/extract] {len(raw_claims)} raw claims (est. ${cost_extract:.4f})")

    # Persist raw claims + sources once
    (out_dir / "raw_claims.json").write_text(
        json.dumps([c.model_dump(mode="json") for c in raw_claims], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "sources.json").write_text(
        json.dumps([{"url": s.url, "title": s.title, "domain": s.domain,
                     "tier": s.tier, "rank": s.rank, "full_text_len": len(s.full_text)}
                    for s in sources], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # ── 4. Run each combo ────────────────────────────────────────────────────
    combo_results: list[dict] = []
    for describer_mode, clusterer_mode in selected_combos:
        label = _label(describer_mode, clusterer_mode)
        log(f"\n[ab/{label}] running...")
        estimates, costs, stats = _run_combo(
            raw_claims,
            describer_mode=describer_mode,
            clusterer_mode=clusterer_mode,
            describer_model=args.describer_model,
            judge_model=args.judge_model,
            validate_clusters=not args.no_validate,
            log=log,
        )
        artefact = _build_run_artefact(
            args.topic, started_at, sources, raw_claims, estimates,
            costs, cost_extract, cost_expand,
        )
        write_html(artefact, out_dir / f"clusters_{label}.html")
        write_json(artefact, out_dir / f"run_{label}.json")
        combo_results.append({
            "label": label,
            "describer_mode": describer_mode,
            "clusterer_mode": clusterer_mode,
            "estimates": estimates,
            "costs": costs,
            "n_clusters": len(estimates),
            "n_multi_source": sum(1 for e in estimates if e.n_unique_sources >= 2),
            "n_high_consensus": sum(1 for e in estimates if e.consensus_level == "high"),
            "n_contested": sum(1 for e in estimates if e.consensus_level == "contested"),
            "n_singletons": sum(1 for e in estimates if e.n_claims == 1),
            "elapsed_s": stats["elapsed_s"],
            "stats": stats,
        })
        log(f"[ab/{label}] DONE  clusters={len(estimates)}  "
            f"multi_src={combo_results[-1]['n_multi_source']}  "
            f"cost=${sum(costs.values()):.4f}  time={stats['elapsed_s']:.1f}s")

    # ── 5. Comparison report ────────────────────────────────────────────────
    summary_path = out_dir / "ab_summary.md"
    _write_summary(summary_path, args.topic, raw_claims, sources, cost_extract,
                   cost_expand, combo_results)

    print(f"\n[ab] wrote:")
    print(f"     {summary_path}  <- comparison table")
    for r in combo_results:
        print(f"     clusters_{r['label']}.html")
    print(f"     raw_claims.json (shared across all combos)")
    return 0


def _write_summary(path: Path, topic: str, raw_claims: list[RawClaim],
                   sources: list[SourceDocument], cost_extract: float,
                   cost_expand: float, combos: list[dict]) -> None:
    lines = [
        f"# A/B Comparison — {topic}",
        "",
        f"**Topic:** {topic}",
        f"**Run at:** {datetime.now().isoformat()}",
        f"**Sources:** {len(sources)} ({sum(1 for s in sources if s.has_content)} with content)",
        f"**Raw claims (shared across all combos):** {len(raw_claims)}",
        f"**Shared cost (search+expand+extract):** ${cost_extract + cost_expand:.4f}",
        "",
        "## Per-combo results",
        "",
        "| combo | clusters | multi-src | high-consensus | contested | singletons | "
        "describe $ | embed $ | judge $ | validate $ | combo total $ | elapsed |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in combos:
        cb_total = sum(r["costs"].values())
        lines.append(
            f"| **{r['label']}** | {r['n_clusters']} | "
            f"**{r['n_multi_source']}** | "
            f"{r['n_high_consensus']} | {r['n_contested']} | "
            f"{r['n_singletons']} | "
            f"${r['costs']['describe']:.4f} | ${r['costs']['embed']:.5f} | "
            f"${r['costs']['judge']:.4f} | ${r['costs']['validate']:.4f} | "
            f"**${cb_total:.4f}** | {r['elapsed_s']:.1f} s |"
        )

    # Total run cost (shared + per combo, summed)
    grand_total = (cost_extract + cost_expand
                   + sum(sum(r["costs"].values()) for r in combos))
    lines += [
        "",
        f"**Grand total (all combos run):** ${grand_total:.4f}",
        "",
        "## Cluster overlap (Jaccard on top-20 clusters per combo)",
        "",
        "How much do the 4 strategies AGREE on what should cluster together?",
        "1.0 = identical clusters, 0.0 = no overlap.",
        "",
        "| | " + " | ".join(c["label"] for c in combos) + " |",
        "|---|" + "---|" * len(combos),
    ]
    for ra in combos:
        row = [f"**{ra['label']}**"]
        for rb in combos:
            if ra["label"] == rb["label"]:
                row.append("—")
            else:
                row.append(f"{_cluster_overlap_score(ra['estimates'], rb['estimates']):.2f}")
        lines.append("| " + " | ".join(row) + " |")

    lines += [
        "",
        "## Top multi-source clusters per combo",
        "",
    ]
    for r in combos:
        lines.append(f"### {r['label']}")
        lines.append("")
        ms = sorted(
            [e for e in r["estimates"] if e.n_unique_sources >= 2],
            key=lambda e: (-e.n_unique_sources, -e.n_claims),
        )[:8]
        if not ms:
            lines.append("_(no multi-source clusters)_")
            lines.append("")
            continue
        for e in ms:
            lines.append(
                f"- **{e.dimension.descriptor[:90]}** — {e.n_claims}c/"
                f"{e.n_unique_sources}s, {e.consensus_level}, "
                f"weighted_mean={e.weighted_mean:.3g} {e.canonical_unit}"
            )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
