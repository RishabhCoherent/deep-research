"""Compute aggregate statistics for each proto-cluster.

Per cluster:
  - simple and tier-weighted mean
  - median, stddev, min, max
  - percent spread (max - min) / mean
  - consensus_level label
  - outlier indices (IQR rule)

Across clusters:
  - time-series linking: clusters whose descriptors are identical EXCEPT for
    the year token form a "family"; we compute a CAGR across the family and
    write it to every member.
"""
from __future__ import annotations

import re
import statistics
from collections import defaultdict
from typing import Iterable

from .clusterer import _ProtoCluster
from .models import ClusteredEstimate, RawClaim, SourceTier


# Authority-tier weights used by weighted mean. Higher = more trustworthy.
_TIER_WEIGHT: dict[SourceTier, float] = {
    "government":   1.00,
    "multilateral": 0.95,
    "industry_body": 0.90,
    "tier1_media":  0.80,
    "analyst_firm": 0.75,
    "trade_press":  0.50,
    "blog":         0.25,
    "unknown":      0.20,
}


def _tier_weight(tier: SourceTier) -> float:
    return _TIER_WEIGHT.get(tier, 0.20)


# ── Per-cluster aggregation ─────────────────────────────────────────────────

def _pct_spread(values: list[float], mean: float) -> float:
    if len(values) < 2 or mean == 0:
        return 0.0
    return (max(values) - min(values)) / abs(mean)


def _consensus_level(n_sources: int, pct_spread: float) -> str:
    if n_sources < 2:
        return "single_source"
    if pct_spread < 0.10:
        return "high"
    if pct_spread < 0.25:
        return "medium"
    if pct_spread < 0.50:
        return "low"
    return "contested"


def _outlier_indices(values: list[float]) -> list[int]:
    """IQR-based outlier flag. Needs >= 4 values to fire."""
    if len(values) < 4:
        return []
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    q1 = sorted_vals[n // 4]
    q3 = sorted_vals[3 * n // 4]
    iqr = q3 - q1
    lo = q1 - 1.5 * iqr
    hi = q3 + 1.5 * iqr
    return [i for i, v in enumerate(values) if v < lo or v > hi]


def _weighted_mean(values: list[float], claims: list[RawClaim]) -> float:
    weights = [_tier_weight(c.source_tier) for c in claims]
    total_w = sum(weights) or 1.0
    return sum(v * w for v, w in zip(values, weights)) / total_w


def aggregate_cluster(proto: _ProtoCluster) -> ClusteredEstimate:
    """Build a ClusteredEstimate from a proto-cluster."""
    claims = proto.claims
    values = [c.value for c in claims]
    unique_domains = {c.source_domain for c in claims}
    n_sources = len(unique_domains)

    mean = statistics.fmean(values) if values else 0.0
    wmean = _weighted_mean(values, claims) if values else 0.0
    median = statistics.median(values) if values else 0.0
    stddev = statistics.pstdev(values) if len(values) > 1 else 0.0
    spread = _pct_spread(values, mean)
    consensus = _consensus_level(n_sources, spread)
    outliers = _outlier_indices(values)

    return ClusteredEstimate(
        dimension=proto.dimension,
        claims=claims,
        n_claims=len(claims),
        n_unique_sources=n_sources,
        values=values,
        mean=mean,
        weighted_mean=wmean,
        median=median,
        stddev=stddev,
        min_value=min(values) if values else 0.0,
        max_value=max(values) if values else 0.0,
        pct_spread=spread,
        consensus_level=consensus,  # type: ignore[arg-type]
        outlier_claim_indices=outliers,
    )


# ── Time-series linking ─────────────────────────────────────────────────────

# Qualifier keys that distinguish TIME SLICES — two clusters are siblings in a
# time-series family iff they share the same qualifier_summary MODULO these
# keys. The `as_of` difference is what makes them siblings; differences in
# subject, metric_kind, segment, scope, etc. keep them in different families.
_TIME_VARYING_KEYS = {"as_of", "published_at", "reporting_date"}

_YEAR_IN_VALUE = re.compile(r"\b(19|20)\d{2}\b")


def _family_key(est: ClusteredEstimate) -> str:
    """Qualifier-set-based family key: everything about the cluster's identity
    EXCEPT the time-varying qualifiers. Two clusters land in the same family
    iff they measure the same quantity at different time slices.
    """
    summary = est.dimension.qualifier_summary or {}
    parts: list[str] = [est.dimension.unit_family]
    for k in sorted(summary.keys()):
        if k in _TIME_VARYING_KEYS:
            continue
        vals = "|".join(sorted(summary[k]))
        parts.append(f"{k}={vals}")
    return "::".join(parts)


def _representative_year(est: ClusteredEstimate) -> int | None:
    """Parse the latest 4-digit year from the cluster's `as_of` qualifier
    values. Returns None if no usable year is present.
    """
    summary = est.dimension.qualifier_summary or {}
    as_of_values = summary.get("as_of") or []
    if not as_of_values:
        return None
    years: list[int] = []
    for v in as_of_values:
        m = _YEAR_IN_VALUE.search(str(v))
        if m:
            try:
                y = int(m.group(0))
                if 1990 <= y <= 2100:
                    years.append(y)
            except ValueError:
                continue
    return max(years) if years else None


def link_time_series(estimates: list[ClusteredEstimate]) -> None:
    """Mutates `estimates` in place: for each family with >= 2 distinct years,
    fit an average per-year growth rate and write it to every member.
    """
    by_family: dict[str, list[ClusteredEstimate]] = defaultdict(list)
    for est in estimates:
        if _representative_year(est) is not None:
            key = _family_key(est)
            by_family[key].append(est)
            est.family_id = key

    for siblings in by_family.values():
        if len(siblings) < 2:
            continue
        # Build (year, weighted_mean) pairs
        pairs: list[tuple[int, float]] = []
        for s in siblings:
            y = _representative_year(s)
            if y is None or s.weighted_mean == 0:
                continue
            pairs.append((y, s.weighted_mean))
        if len(pairs) < 2:
            continue
        pairs.sort()
        rates: list[float] = []
        for (y0, v0), (y1, v1) in zip(pairs, pairs[1:]):
            if y0 == y1 or v0 == 0:
                continue
            years = y1 - y0
            if years <= 0:
                continue
            try:
                cagr = (pow(v1 / v0, 1.0 / years) - 1.0) * 100.0
            except (ValueError, ZeroDivisionError):
                continue
            rates.append(cagr)
        if not rates:
            continue
        avg_rate = round(statistics.fmean(rates), 2)
        for s in siblings:
            s.trend_slope_pct_per_year = avg_rate


# ── Public API ──────────────────────────────────────────────────────────────

def build_estimates(
    protos: Iterable[_ProtoCluster],
    *,
    link_trends: bool = True,
) -> list[ClusteredEstimate]:
    """Run per-cluster aggregation + optional time-series linking."""
    estimates = [aggregate_cluster(p) for p in protos]
    if link_trends:
        link_time_series(estimates)
    _consensus_order = {"high": 0, "medium": 1, "low": 2, "contested": 3, "single_source": 4}
    estimates.sort(
        key=lambda e: (-e.n_claims,
                       _consensus_order.get(e.consensus_level, 5),
                       -abs(e.weighted_mean)),
    )
    return estimates
