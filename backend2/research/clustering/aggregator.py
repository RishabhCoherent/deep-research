"""Compute aggregate statistics for each proto-cluster + link time-series.

Per cluster:
  - simple and tier-weighted mean
  - median, stddev, min, max
  - percent spread, consensus_level, outlier indices

Across clusters:
  - time-series families: clusters whose qualifier set is identical EXCEPT
    `as_of` form a "family"; CAGR is computed and written to every member.
"""
from __future__ import annotations

import re
import statistics
from collections import defaultdict
from typing import Iterable

from .clusterer import _ProtoCluster
from .models import ClusteredEstimate, RawClaim, SourceTier


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


_TIME_VARYING_KEYS = {"as_of", "published_at", "reporting_date"}
_YEAR_IN_VALUE = re.compile(r"\b(19|20)\d{2}\b")


def _family_key(est: ClusteredEstimate) -> str:
    summary = est.dimension.qualifier_summary or {}
    parts: list[str] = [est.dimension.unit_family]
    for k in sorted(summary.keys()):
        if k in _TIME_VARYING_KEYS:
            continue
        vals = "|".join(sorted(summary[k]))
        parts.append(f"{k}={vals}")
    return "::".join(parts)


def _representative_year(est: ClusteredEstimate) -> int | None:
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
    by_family: dict[str, list[ClusteredEstimate]] = defaultdict(list)
    for est in estimates:
        if _representative_year(est) is not None:
            key = _family_key(est)
            by_family[key].append(est)
            est.family_id = key

    for siblings in by_family.values():
        if len(siblings) < 2:
            continue
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


# How old (in years) before a cluster is considered stale and pushed below
# fresh clusters in the default sort. Forecast clusters (as_of in the future)
# are NEVER stale.
_STALE_THRESHOLD_YEARS = 2


def _is_stale(est: ClusteredEstimate, today_year: int) -> bool:
    """A cluster is stale if its newest as_of year is more than
    `_STALE_THRESHOLD_YEARS` behind today and not a forecast (future year).
    Clusters with no parseable year (e.g. only "unknown" / news events) are
    treated as fresh — we don't want to demote them based on missing data.
    """
    y = _representative_year(est)
    if y is None:
        return False
    if y >= today_year:
        return False                                  # current or forecast
    return (today_year - y) > _STALE_THRESHOLD_YEARS


def build_estimates(
    protos: Iterable[_ProtoCluster],
    *,
    link_trends: bool = True,
    today_year: int | None = None,
) -> list[ClusteredEstimate]:
    """Run per-cluster aggregation + optional time-series linking.

    `today_year` defaults to current calendar year; override for reproducible
    tests. Sort order is recency-aware: stale clusters (older than
    `_STALE_THRESHOLD_YEARS` years) sink below fresh ones, regardless of
    claim count. Within each tier the legacy sort applies.
    """
    if today_year is None:
        from datetime import date as _date
        today_year = _date.today().year

    estimates = [aggregate_cluster(p) for p in protos]
    if link_trends:
        link_time_series(estimates)
    _consensus_order = {"high": 0, "medium": 1, "low": 2,
                        "contested": 3, "single_source": 4}

    def _sort_key(e: ClusteredEstimate) -> tuple:
        stale = _is_stale(e, today_year)
        # Stale comes after fresh (False=0 < True=1). Within a freshness tier:
        # most claims first → highest consensus → biggest |weighted_mean|.
        return (
            stale,                                           # 0 fresh, 1 stale
            -e.n_claims,
            _consensus_order.get(e.consensus_level, 5),
            -abs(e.weighted_mean),
        )

    estimates.sort(key=_sort_key)
    return estimates
