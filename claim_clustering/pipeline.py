"""End-to-end orchestrator: topic -> ClusteringRun (descriptor-based v2).

Stages:
  1. search    : SmartCrawler/SearXNG -> ~15 SourceDocuments
  2. extract   : per-source LLM (gpt-4o-mini default) -> list[RawClaim]
  3. describe  : per-claim LLM (gpt-4o default) -> claim.descriptor
  4. embed     : OpenAI text-embedding-3-small -> claim.descriptor_embedding
  5. cluster   : cosine similarity + LLM judge (gray zone) -> proto-clusters
  6. validate  : optional safety-net split of contested clusters
  7. aggregate : per-cluster stats + time-series linking -> list[ClusteredEstimate]

Cost is tracked per stage and surfaced in ClusteringRun.cost_*_usd.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable, Optional

from .aggregator import build_estimates
from .clusterer import cluster_claims, cluster_claims_hash
from .describer import describe_claims_template, _price_for_model
from .embedder import embed_claims
from .extractor import extract_from_sources
from .models import ClusteringRun, RawClaim, TopicProfile
from .query_expander import expand_topic
from .relevance import score_claim_relevance, score_source_relevance
from .search import search_topic, search_multiple_queries, SourceDocument
from .topic_profiler import generate_topic_profile, render_profile_for_console
from .validator import validate_and_split


ProgressFn = Callable[[str], None]


def _noop(_msg: str) -> None:
    pass


def _estimate_extract_cost(sources: list[SourceDocument], model: str,
                           per_source_in_tokens: int = 12_000,
                           per_source_out_tokens: int = 1_500) -> float:
    """Crude estimate of extraction cost based on source count + per-call token avg.

    The extractor runs one LLM call per source. Real cost is tracked in
    extractor.py via response.usage if needed; this rough estimate is used when
    we don't have telemetry.
    """
    in_per_m, out_per_m = _price_for_model(model)
    n = sum(1 for s in sources if s.has_content)
    return (n * per_source_in_tokens / 1_000_000 * in_per_m +
            n * per_source_out_tokens / 1_000_000 * out_per_m)


# All-in cost per source (extract + describe + embed + judge share + validate
# share), used for cost-ceiling source trimming. Empirical from the v7 GPU run:
# 92 claims / 15 sources = 6.1 claims/source, total cost $0.10 -> $0.0067/source.
# Round up to $0.007 to give headroom for variance.
_COST_PER_SOURCE_ESTIMATE = 0.007


# Scale presets: turn a single CLI flag into the knobs that matter.
# scrape_workers + playwright_budget scale with max_sources so wall-time stays
# in the 1-3 min range across all preset levels (cap-before-scrape architecture
# means we only scrape what we keep).
SCALE_PRESETS: dict[str, dict] = {
    "compact": {
        "max_sources": 25,
        "max_per_query": 12,
        "max_cost": 0.20,
        "scrape_workers": 8,
        "playwright_budget": 30,
        "label": "compact (~$0.18, ~25 sources, ~1.5 min)",
    },
    "standard": {
        "max_sources": 70,
        "max_per_query": 25,
        "max_cost": 0.50,
        "scrape_workers": 16,
        "playwright_budget": 60,
        "label": "standard (~$0.47, ~70 sources, ~2-3 min)",
    },
    "deep": {
        "max_sources": 150,
        "max_per_query": 30,
        "max_cost": 1.00,
        "scrape_workers": 32,
        "playwright_budget": 100,
        "label": "deep (~$1.00, ~150 sources, ~2-3 min)",
    },
    "exhaustive": {
        "max_sources": 500,
        "max_per_query": 40,
        "max_cost": 3.50,
        "scrape_workers": 48,
        "playwright_budget": 150,
        "label": "exhaustive (~$3.40, ~500 sources, ~5-8 min)",
    },
}


# Source-tier ranking for cost-ceiling-driven trimming. We keep highest-tier
# sources first, then by search rank.
_TIER_KEEP_ORDER = {
    "government": 0, "multilateral": 1, "industry_body": 2, "tier1_media": 3,
    "analyst_firm": 4, "trade_press": 5, "blog": 6, "unknown": 7,
}


def _trim_sources_to_budget(
    sources: list[SourceDocument], max_cost: float, log: ProgressFn,
) -> list[SourceDocument]:
    """If estimated total cost exceeds max_cost, drop the lowest-priority
    sources (lowest tier first, then highest rank) until estimate is within
    the ceiling. Returns the trimmed list.
    """
    if max_cost <= 0:
        return sources
    estimated = len(sources) * _COST_PER_SOURCE_ESTIMATE
    if estimated <= max_cost:
        return sources

    keep_n = max(1, int(max_cost / _COST_PER_SOURCE_ESTIMATE))
    if keep_n >= len(sources):
        return sources

    # Sort by (tier-priority asc, rank asc) - keep best sources first
    ordered = sorted(
        sources,
        key=lambda s: (_TIER_KEEP_ORDER.get(s.tier, 9), s.rank),
    )
    trimmed = ordered[:keep_n]
    log(f"[pipeline] estimated ${estimated:.2f} > ceiling ${max_cost:.2f}, "
        f"trimmed to top {keep_n} sources (kept by tier+rank)")
    return trimmed


def run(
    topic: str,
    *,
    max_sources: int = 70,
    extra_queries: Optional[list[str]] = None,
    extractor_model: str = "gpt-4o-mini",
    describer_model: str = "gpt-4o",   # kept for back-compat; ignored (template-only now)
    judge_model: str = "gpt-4o-mini",
    auto_merge: float = 0.92,
    auto_separate: float = 0.70,
    validate_clusters: bool = False,   # default OFF in Phase 3a (cluster quality is good enough w/o)
    max_per_query: int = 25,
    max_cost: float = 0.50,
    auto_expand_queries: bool = True,
    expand_target_min: int = 25,
    expand_target_max: int = 40,
    describer_mode: str = "template",   # kept for back-compat; ignored (template-only now)
    clusterer_mode: str = "hash",       # "cosine" | "hash"
    scrape_workers: int = 16,
    playwright_budget: int = 60,
    relevance_threshold: float = 0.30,
    show_profile: bool = False,
    on_progress: Optional[ProgressFn] = None,
) -> tuple[ClusteringRun, list[SourceDocument], list[RawClaim]]:
    """Run the full pipeline. Returns (ClusteringRun, sources, raw_claims).

    `relevance_threshold` is the cosine cutoff below which a claim is flagged
    `is_topic_relevant=False` (surfaced separately, not deleted). Default 0.30
    is empirically the boundary where domain-irrelevant claims (e.g. GPU SKU
    retail prices for a "GPU as a Service market" topic) score below most
    on-topic claims.

    `show_profile` prints the generated TopicProfile to the progress log so
    the user can audit what the run is optimising for.
    """
    log = on_progress or _noop
    t0 = time.time()
    started_at = datetime.now(timezone.utc).isoformat()

    # 0. Topic profile ────────────────────────────────────────────────────────
    log(f"[0/7] Generating topic profile for {topic!r}...")
    topic_profile, cost_profile = generate_topic_profile(topic, on_progress=log)
    if show_profile:
        for line in render_profile_for_console(topic_profile).splitlines():
            log(line)

    # 1. Auto-expand queries ──────────────────────────────────────────────────
    cost_expand = 0.0
    expanded_queries: list[str] = []
    if auto_expand_queries:
        log(f"[1/7] Auto-expanding {topic!r} into 25-40 sub-queries...")
        expanded_queries, cost_expand = expand_topic(
            topic,
            target_min=expand_target_min,
            target_max=expand_target_max,
            topic_profile=topic_profile,
            on_progress=log,
        )

    # 2. Search ───────────────────────────────────────────────────────────────
    log(f"[2/7] Searching for {topic!r} (max_sources={max_sources}, "
        f"max_per_query={max_per_query}, scrape_workers={scrape_workers}, "
        f"pw_budget={playwright_budget}, max_cost=${max_cost:.2f})...")

    queries: list[str] = []
    if expanded_queries:
        queries.extend(expanded_queries)
    if extra_queries:
        queries.extend(extra_queries)
    # Dedupe preserving order
    seen_q: set[str] = set()
    queries = [q for q in queries if q.lower() not in seen_q and not seen_q.add(q.lower())]

    if queries:
        log(f"      running {len(queries)} queries in parallel (max_per_query={max_per_query})")
        sources = search_multiple_queries(
            queries,
            max_per_query=max_per_query,
            max_sources=max_sources,
            scrape_workers=scrape_workers,
            playwright_budget=playwright_budget,
        )
    else:
        sources = search_topic(topic, max_sources=max_sources)
    log(f"      {len(sources)} sources retrieved, "
        f"{sum(1 for s in sources if s.has_content)} with substantive text")

    # Cost-ceiling trim: drop lowest-tier sources if estimate exceeds budget
    sources = _trim_sources_to_budget(sources, max_cost, log)

    # 2.5. Source-level relevance gate (BEFORE extract — cheapest cost cut) ──
    # Embed each source's title + snippet + first-500-chars + schema.org
    # metadata and drop those below the relevance threshold. Saves ~80% of
    # extract cost on irrelevant sources.
    log(f"[2.5/7] Source-level relevance gate (threshold={relevance_threshold})...")
    sources_kept, sources_dropped, cost_source_relevance = score_source_relevance(
        sources, topic_profile,
        threshold=relevance_threshold, on_progress=log,
    )
    if sources_dropped:
        log(f"      dropped {len(sources_dropped)} off-topic sources "
            f"(would have cost ~${len(sources_dropped) * _COST_PER_SOURCE_ESTIMATE:.3f} "
            f"in extract); proceeding with {len(sources_kept)} sources")

    # 3. Extract ──────────────────────────────────────────────────────────────
    log(f"[3/7] Extracting claims via {extractor_model} (1 call per source)...")
    raw_claims = extract_from_sources(
        sources_kept, model=extractor_model, topic_profile=topic_profile,
    )
    cost_extract = _estimate_extract_cost(sources, extractor_model)
    log(f"      {len(raw_claims)} raw claims from "
        f"{len({c.source_domain for c in raw_claims})} domains "
        f"(est. extract cost ${cost_extract:.4f})")

    # 4. Describe ─────────────────────────────────────────────────────────────
    log("[4/7] Generating descriptors via TEMPLATE (Python, free)...")
    raw_claims, cost_describe = describe_claims_template(raw_claims, on_progress=log)

    # 4.5. Topic-relevance gate ──────────────────────────────────────────────
    log(f"[5/7] Scoring claim relevance against topic profile "
        f"(threshold={relevance_threshold})...")
    raw_claims, cost_relevance = score_claim_relevance(
        raw_claims, topic_profile,
        threshold=relevance_threshold, on_progress=log,
    )

    # Embed (only needed for cosine clusterer) ────────────────────────────────
    cost_embed = 0.0
    if clusterer_mode == "cosine":
        log("      Embedding descriptors for cosine clusterer...")
        raw_claims, cost_embed = embed_claims(raw_claims, on_progress=log)

    # 5. Cluster ──────────────────────────────────────────────────────────────
    # Cluster only the on-topic claims; off-topic ones are kept aside for the
    # "Out-of-scope findings" section in the visualiser.
    on_topic_claims = [c for c in raw_claims if c.is_topic_relevant]
    off_topic_claims = [c for c in raw_claims if not c.is_topic_relevant]
    if off_topic_claims:
        log(f"      holding back {len(off_topic_claims)} off-topic claims "
            f"from clustering (will surface in 'out-of-scope' section)")

    if clusterer_mode == "hash":
        log("[6/7] Clustering by qualifier-HASH + Jaro-Winkler fuzzy merge "
            "(no LLM, no embeddings)...")
        protos, cluster_stats = cluster_claims_hash(
            on_topic_claims, on_progress=log,
        )
    else:
        log(f"[6/7] Clustering by descriptor COSINE + LLM judge "
            f"(auto_merge={auto_merge}, auto_separate={auto_separate})...")
        protos, cluster_stats = cluster_claims(
            on_topic_claims,
            auto_merge=auto_merge,
            auto_separate=auto_separate,
            judge_model=judge_model,
            on_progress=log,
        )
    cost_judge = float(cluster_stats.get("judge_cost_usd", 0.0))
    n_judge_calls = int(cluster_stats.get("n_judge_calls", 0))

    # 7. Validate (optional safety net) ──────────────────────────────────────
    cost_validate = 0.0
    if validate_clusters:
        log("[7/7] LLM-validating remaining suspicious clusters...")
        before = len(protos)
        # Note: validator uses the same gpt-4o-mini and doesn't return cost yet,
        # so we approximate from typical usage (~3k toks per check)
        protos = validate_and_split(protos, model=judge_model, on_progress=log)
        n_checked = max(0, len(protos) - before)
        in_per_m, out_per_m = _price_for_model(judge_model)
        cost_validate = (n_checked * 2500 / 1_000_000 * in_per_m +
                          n_checked * 600 / 1_000_000 * out_per_m)
    else:
        log("[7/7] Skipping post-cluster validation (--no-validate)")

    # Aggregate ───────────────────────────────────────────────────────────────
    log("Computing per-cluster statistics + linking time-series...")
    estimates = build_estimates(protos, link_trends=True)
    multi_src = sum(1 for e in estimates if e.n_unique_sources >= 2)
    n_trends = sum(1 for e in estimates if e.trend_slope_pct_per_year is not None)
    log(f"      {len(estimates)} clusters; {multi_src} multi-source; "
        f"{n_trends} time-series linked")

    cost_total = (cost_profile + cost_expand + cost_extract + cost_describe
                  + cost_embed + cost_source_relevance + cost_relevance
                  + cost_judge + cost_validate)

    run_artefact = ClusteringRun(
        topic=topic,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc).isoformat(),
        n_sources_searched=len(sources),
        n_sources_with_claims=len({c.source_domain for c in raw_claims}),
        n_raw_claims=len(raw_claims),
        n_dimensions=len(estimates),
        estimates=estimates,
        cost_extract_usd=round(cost_extract, 5),
        cost_describe_usd=round(cost_describe, 5),
        cost_embed_usd=round(cost_embed, 5),
        cost_judge_usd=round(cost_judge, 5),
        cost_validate_usd=round(cost_validate, 5),
        cost_total_usd=round(cost_total, 5),
        search_calls=len(sources),
        scrape_bytes=sum(len(s.full_text) for s in sources),
        n_judge_calls=n_judge_calls,
        topic_profile=topic_profile,
        off_topic_claims=off_topic_claims,
    )

    elapsed = time.time() - t0
    log(f"[done] {elapsed:.1f}s   cost=${cost_total:.4f}  "
        f"(profile=${cost_profile:.5f} expand=${cost_expand:.5f} "
        f"src_relev=${cost_source_relevance:.5f} extract=${cost_extract:.4f} "
        f"describe=${cost_describe:.4f} embed=${cost_embed:.5f} "
        f"relevance=${cost_relevance:.5f} judge=${cost_judge:.4f} "
        f"validate=${cost_validate:.4f})")
    return run_artefact, sources, raw_claims
