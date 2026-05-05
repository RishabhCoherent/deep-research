"""Backend2 dimensional clustering library.

Public API:

    cluster_numeric_claims(claims) -> list[ClusteredEstimate]

Takes a list of `research.core.types.NumericClaim` and returns a list of
dimensional clusters (each cluster groups claims that measure the same
quantity along the same qualifier dimensions; see `ClusteredEstimate` for
the full output shape — descriptor, weighted_mean, n_unique_sources,
consensus_level, etc.).

Pure-Python: no LLM calls, no embeddings, no I/O. Runs in milliseconds for
hundreds of claims. Use this in a graph node downstream of agents that
populate `RunState.*_claims` lists (a3, a5, a6).
"""
from __future__ import annotations

from typing import Iterable

from research.core.types import NumericClaim

from .adapter import numeric_claims_to_raw
from .aggregator import build_estimates
from .clusterer import cluster_claims_hash
from .describer import describe_claims_template
from .models import ClaimDimension, ClusteredEstimate, RawClaim


__all__ = [
    "cluster_numeric_claims",
    "ClusteredEstimate",
    "ClaimDimension",
]


def cluster_numeric_claims(
    claims: Iterable[NumericClaim],
    *,
    fuzzy_threshold: float = 0.88,
    link_trends: bool = True,
    today_year: int | None = None,
    on_progress=None,
) -> list[ClusteredEstimate]:
    """Cluster a flat list of NumericClaims into dimensional clusters.

    Pipeline:
      1. adapter: NumericClaim -> RawClaim (Wikidata-style qualifier shape)
      2. describer: pure-Python deterministic descriptor sentence per claim
      3. clusterer: qualifier-hash + Jaro-Winkler fuzzy merge (no LLM)
      4. aggregator: per-cluster stats + cross-cluster time-series linking

    `fuzzy_threshold` (default 0.88): minimum Jaro-Winkler similarity for
    near-identical subject/segment strings to merge into one cluster.

    `link_trends` (default True): attach trend_slope_pct_per_year to clusters
    that have a time-series sibling family.
    """
    log = on_progress or (lambda _msg: None)
    raw_list = numeric_claims_to_raw(claims)
    if not raw_list:
        return []

    # 1. Describe (free, deterministic)
    describe_claims_template(raw_list)

    # 2. Cluster (hash + fuzzy)
    protos, stats = cluster_claims_hash(
        raw_list, fuzzy_threshold=fuzzy_threshold, on_progress=log,
    )

    # 3. Aggregate
    estimates = build_estimates(
        protos, link_trends=link_trends, today_year=today_year,
    )
    log(f"[clustering] {len(raw_list)} claims -> {len(estimates)} clusters "
        f"({sum(1 for e in estimates if e.n_unique_sources >= 2)} multi-source)")
    return estimates
