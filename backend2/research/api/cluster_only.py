"""Clustering-only research pipeline (no a4/a5/a6/a7/a8/verifier).

Runs the minimum subset needed to produce + cluster numeric claims:
    a0 (topic_profile) -> a1 (refine query) -> a2 (sub-questions) ->
    a3 (fetch + extract claims via hybrid prefilter+LLM) -> cluster.

Then renders an HTML report using claim_clustering's existing visualiser.

This is a developer iteration path — fast feedback on extraction +
clustering changes without paying for the consolidator/verifier stack.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from research.clustering import cluster_numeric_claims
from research.core.topic_profile import generate_topic_profile
from research.core.types import IntentKind
from research.crews.a1_query_refiner.crew import run_a1
from research.crews.a2_question_generator.crew import run_a2
from research.crews.a3_topic_researcher.crew import run_a3


_log = structlog.get_logger(__name__)

# Make sibling claim_clustering importable for visualiser
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


_PRICES_PER_MTOK = {
    "anthropic": {"in": 1.00, "out": 5.00},
    "openai":    {"in": 0.15, "out": 0.60},
}


def _slug(s: str, maxlen: int = 60) -> str:
    out = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in s.lower())
    out = "-".join(filter(None, out.split("-")))
    return (out[:maxlen]).strip("-") or "run"


# ── claim_clustering bridge (mirrors test_clustering.py) ────────────────────

_CC_UNIT_FAMILY_VALUES = {
    "USD", "EUR", "GBP", "INR", "CNY", "JPY",
    "percent", "units", "usd_per_unit", "ratio", "unknown",
}


def _coerce_unit_family(family: str) -> str:
    return family if family in _CC_UNIT_FAMILY_VALUES else "unknown"


def _b2_to_cc_estimate(b2_dict: dict[str, Any]):
    from claim_clustering.models import (
        ClaimDimension as CCDimension,
        ClusteredEstimate as CCEstimate,
        RawClaim as CCRawClaim,
    )
    dim_in = b2_dict.get("dimension") or {}
    fam = _coerce_unit_family(dim_in.get("unit_family", "unknown"))
    dim = CCDimension(
        descriptor=dim_in.get("descriptor", "(no descriptor)"),
        unit_family=fam,
        qualifier_summary=dim_in.get("qualifier_summary", {}),
    )
    cc_claims = []
    for c in b2_dict.get("claims") or []:
        cc_claims.append(CCRawClaim(
            source_url=c.get("source_url", ""),
            source_domain=c.get("source_domain", ""),
            source_title=c.get("source_title"),
            source_tier=c.get("source_tier", "unknown"),
            published_at=c.get("published_at"),
            raw_text=(c.get("raw_text") or "")[:600],
            value_raw=str(c.get("value_raw", "")),
            value=float(c.get("value", 0.0) or 0.0),
            unit_raw=c.get("unit_raw", ""),
            unit_family=_coerce_unit_family(c.get("unit_family", "unknown")),
            unit_magnitude_hint=c.get("unit_magnitude_hint"),
            qualifiers=c.get("qualifiers") or {},
            rank=c.get("rank", "normal"),
            descriptor=c.get("descriptor", ""),
            extractor_confidence=float(c.get("extractor_confidence", 0.7) or 0.7),
        ))
    return CCEstimate(
        dimension=dim,
        claims=cc_claims,
        n_claims=int(b2_dict.get("n_claims", 0)),
        n_unique_sources=int(b2_dict.get("n_unique_sources", 0)),
        values=list(b2_dict.get("values") or []),
        mean=float(b2_dict.get("mean", 0.0) or 0.0),
        weighted_mean=float(b2_dict.get("weighted_mean", 0.0) or 0.0),
        median=float(b2_dict.get("median", 0.0) or 0.0),
        stddev=float(b2_dict.get("stddev", 0.0) or 0.0),
        min_value=float(b2_dict.get("min_value", 0.0) or 0.0),
        max_value=float(b2_dict.get("max_value", 0.0) or 0.0),
        pct_spread=float(b2_dict.get("pct_spread", 0.0) or 0.0),
        consensus_level=b2_dict.get("consensus_level", "single_source"),
        outlier_claim_indices=list(b2_dict.get("outlier_claim_indices") or []),
        trend_slope_pct_per_year=b2_dict.get("trend_slope_pct_per_year"),
        family_id=b2_dict.get("family_id"),
    )


def _render_html(topic: str, claims, estimates, started_at: str, finished_at: str,
                 out_dir: Path, profile_dict: dict | None) -> tuple[Path, Path]:
    from claim_clustering.models import ClusteringRun as CCRun, TopicProfile as CCTopicProfile
    from claim_clustering.visualise import write_html, write_json

    cc_estimates = [_b2_to_cc_estimate(e.model_dump(mode="json")) for e in estimates]
    cc_profile = None
    if profile_dict:
        try:
            cc_profile = CCTopicProfile(
                topic_subject=profile_dict.get("topic_subject", ""),
                topic_domain=profile_dict.get("topic_domain", "unknown"),
                expected_metric_kinds=profile_dict.get("expected_metric_kinds") or [],
                key_dimensions=profile_dict.get("key_dimensions") or [],
                positive_signals=profile_dict.get("positive_signals") or [],
                negative_signals=profile_dict.get("negative_signals") or [],
                expected_unit_families=profile_dict.get("expected_unit_families") or [],
                profile_reasoning=profile_dict.get("profile_reasoning", ""),
            )
        except Exception:
            cc_profile = None

    run = CCRun(
        topic=topic,
        started_at=started_at,
        finished_at=finished_at,
        n_sources_searched=len({c.citation.url for c in claims if c.citation}),
        n_sources_with_claims=len({c.citation.url for c in claims if c.citation}),
        n_raw_claims=len(claims),
        n_dimensions=len(cc_estimates),
        estimates=cc_estimates,
        topic_profile=cc_profile,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / "run.html"
    json_path = out_dir / "run.json"
    write_html(run, html_path)
    write_json(run, json_path)
    return html_path, json_path


# ── Orchestrator ────────────────────────────────────────────────────────────


async def run_clustering_only(
    topic: str,
    *,
    brief: str = "",
    out_root: Path | None = None,
    skip_a1_a2: bool = False,
) -> dict[str, Any]:
    """Run a0 -> a1 -> a2 -> a3 -> cluster and emit HTML/JSON.

    `skip_a1_a2`: skip query refinement + sub-question decomposition. Uses
    the raw topic as chosen_query and a default IntentKind.GENERAL with
    empty sub_questions (a3 falls back to its legacy single-pass fetch).
    Faster but less search coverage — useful for very rapid iteration.

    Returns a dict with keys:
      topic, html_path, json_path, claims, clusters, multi_source,
      five_plus_clusters, top_size, median_size, prefilter_seconds,
      a1_seconds, a2_seconds, a3_seconds, cluster_seconds,
      total_seconds, llm_tokens_in, llm_tokens_out, llm_cost_usd, provider.
    """
    import os
    from research.crews.a3_topic_researcher.crew import _structure_claims_batched  # noqa: F401

    provider = os.environ.get("LLM_PROVIDER", "anthropic")
    started_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out_root = out_root or Path(__file__).resolve().parent.parent.parent / "clustering_test_runs"

    timings: dict[str, float] = {}
    a3_usage: dict[str, int] = {}

    # Token tracking — three-pronged because the pipeline mixes:
    #   1. CrewAI crews (a1, a2, a3 internals) — read CrewOutput.token_usage
    #      via a Crew.kickoff_async patch.
    #   2. Direct LangChain calls (a0 topic_profile) — langchain callback.
    #   3. Other litellm-only paths — litellm CustomLogger.
    extra_tokens: dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "n_calls": 0}

    # Prong 1: patch CrewAI Crew.kickoff_async
    from crewai import Crew as _CrewClass
    _orig_kickoff_async = _CrewClass.kickoff_async

    async def _patched_kickoff_async(self, *args, **kwargs):
        result = await _orig_kickoff_async(self, *args, **kwargs)
        try:
            tu = getattr(result, "token_usage", None)
            if tu is not None:
                d = tu.model_dump() if hasattr(tu, "model_dump") else dict(tu)
                extra_tokens["input_tokens"]  += int(d.get("prompt_tokens", 0) or 0)
                extra_tokens["output_tokens"] += int(d.get("completion_tokens", 0) or 0)
                extra_tokens["n_calls"]       += int(d.get("successful_requests", 0) or 0)
        except Exception:
            pass
        return result
    _CrewClass.kickoff_async = _patched_kickoff_async

    # Prong 2: langchain callback (for a0's direct generate_topic_profile path
    # and a3's _decompose_subquestion). Must inherit from BaseCallbackHandler
    # so langchain's dispatcher finds the expected attributes (run_inline,
    # ignore_*, etc.) — a duck-typed class trips an AttributeError that
    # cascades into ALL decompose calls failing silently.
    from langchain_core.callbacks import BaseCallbackHandler as _BaseCB

    class _LCTracker(_BaseCB):
        def on_llm_end(self, response, **_kw):
            try:
                for gens in response.generations:
                    for g in gens:
                        msg = getattr(g, "message", None)
                        u = getattr(msg, "usage_metadata", None) if msg else None
                        if u:
                            extra_tokens["input_tokens"]  += int(u.get("input_tokens", 0) or 0)
                            extra_tokens["output_tokens"] += int(u.get("output_tokens", 0) or 0)
                            extra_tokens["n_calls"]       += 1
            except Exception:
                pass

    lc_tracker = _LCTracker()
    from research.api import model_router as mr
    _orig_factories = (mr.haiku, mr.sonnet, mr.opus)

    def _wrap(orig):
        def wrapped(*args, **kwargs):
            llm = orig(*args, **kwargs)
            llm.callbacks = list(getattr(llm, "callbacks", None) or []) + [lc_tracker]
            return llm
        return wrapped
    mr.haiku  = _wrap(_orig_factories[0])
    mr.sonnet = _wrap(_orig_factories[1])
    mr.opus   = _wrap(_orig_factories[2])

    try:
        # ── a0: topic profile ─────────────────────────────────────────────
        t0 = time.perf_counter()
        profile, _profile_cost = generate_topic_profile(topic)
        timings["a0"] = time.perf_counter() - t0
        _log.info("cluster_only.a0_done",
                  domain=profile.topic_domain,
                  metric_kinds=profile.expected_metric_kinds[:5])

        if skip_a1_a2:
            chosen_query = topic
            intent = IntentKind.GENERAL
            sub_questions = []
            timings["a1"] = 0.0
            timings["a2"] = 0.0
        else:
            # ── a1: query refinement (auto-pick top variant) ─────────────
            t0 = time.perf_counter()
            a1_result = await run_a1(topic)
            timings["a1"] = time.perf_counter() - t0
            if a1_result and a1_result.variants_sorted:
                chosen_query = a1_result.variants_sorted[0].variant.text
                intent = a1_result.intent
            else:
                chosen_query = topic
                intent = IntentKind.GENERAL
            _log.info("cluster_only.a1_done",
                      chosen_query=chosen_query[:80], intent=intent.value)

            # ── a2: sub-questions ──────────────────────────────────────────
            t0 = time.perf_counter()
            a2_result = await run_a2(
                chosen_query=chosen_query,
                intent=intent,
                original_query=topic,
                topic_profile=profile,
            )
            timings["a2"] = time.perf_counter() - t0
            sub_questions = (a2_result.questions if a2_result else []) or []
            _log.info("cluster_only.a2_done", n_subqs=len(sub_questions))

        # ── a3: fetch + extract (the heavy step) ─────────────────────────
        # narrative_off=True skips the Sonnet topic_summariser since
        # clustering doesn't read the narrative — saves the largest single
        # LLM call in the pipeline.
        t0 = time.perf_counter()
        a3_result = await run_a3(
            chosen_query=chosen_query,
            intent=intent,
            sub_questions=sub_questions,
            topic_profile=profile,
            narrative_off=True,
        )
        timings["a3"] = time.perf_counter() - t0
        claims = list(a3_result.claims) if a3_result else []
        _log.info("cluster_only.a3_done", n_claims=len(claims))

        # ── cluster ───────────────────────────────────────────────────────
        t0 = time.perf_counter()
        estimates = cluster_numeric_claims(
            claims,
            on_progress=lambda msg: _log.info("cluster_only.cluster_progress", text=msg),
        )
        timings["cluster"] = time.perf_counter() - t0

        # ── render HTML ───────────────────────────────────────────────────
        finished_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        out_dir = out_root / _slug(topic)
        html_path, json_path = _render_html(
            topic=topic,
            claims=claims,
            estimates=estimates,
            started_at=started_iso,
            finished_at=finished_iso,
            out_dir=out_dir,
            profile_dict=profile.model_dump(),
        )
    finally:
        # Restore patches
        mr.haiku, mr.sonnet, mr.opus = _orig_factories
        _CrewClass.kickoff_async = _orig_kickoff_async

    sizes = sorted([e.n_claims for e in estimates], reverse=True)
    multi_source = sum(1 for e in estimates if e.n_unique_sources >= 2)
    five_plus = sum(1 for s in sizes if s >= 5)
    median_size = sizes[len(sizes)//2] if sizes else 0
    top_size = sizes[0] if sizes else 0

    rates = _PRICES_PER_MTOK.get(provider, _PRICES_PER_MTOK["anthropic"])
    cost = (extra_tokens["input_tokens"] / 1_000_000) * rates["in"] + \
           (extra_tokens["output_tokens"] / 1_000_000) * rates["out"]

    total_seconds = sum(timings.values())

    return {
        "topic": topic,
        "chosen_query": chosen_query,
        "html_path": str(html_path),
        "json_path": str(json_path),
        "html_url": f"/api/cluster/runs/{_slug(topic)}/run.html",
        "claims": len(claims),
        "clusters": len(estimates),
        "multi_source": multi_source,
        "five_plus_clusters": five_plus,
        "top_size": top_size,
        "median_size": median_size,
        "cluster_size_distribution": dict(sorted(
            {s: sizes.count(s) for s in set(sizes)}.items(), reverse=True
        )),
        "a0_seconds":      round(timings.get("a0", 0.0), 2),
        "a1_seconds":      round(timings.get("a1", 0.0), 2),
        "a2_seconds":      round(timings.get("a2", 0.0), 2),
        "a3_seconds":      round(timings.get("a3", 0.0), 2),
        "cluster_seconds": round(timings.get("cluster", 0.0), 2),
        "total_seconds":   round(total_seconds, 2),
        "llm_calls":       extra_tokens["n_calls"],
        "llm_tokens_in":   extra_tokens["input_tokens"],
        "llm_tokens_out":  extra_tokens["output_tokens"],
        "llm_cost_usd":    round(cost, 4),
        "provider":        provider,
    }
