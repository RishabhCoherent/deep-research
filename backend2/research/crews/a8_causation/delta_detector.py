"""Deterministic delta detection. No LLM calls.

Groups validated_claims by normalised metric string, pairs prior+current by as_of date,
computes delta_pct.  The LLM (8a) handles semantic/fuzzy matching edge cases.
"""

from __future__ import annotations

from datetime import date

from research.core.types import NumericClaim, Delta


def _parse_date(s: str | None) -> date | None:
    """Parse an ISO-like date string (full or partial). Returns None on failure."""
    if not s:
        return None
    try:
        return date.fromisoformat(s.strip()[:10])
    except Exception:
        pass
    # Try year-month "2026-02"
    try:
        parts = s.strip().split("-")
        if len(parts) == 2:
            return date(int(parts[0]), int(parts[1]), 1)
        if len(parts) == 1:
            return date(int(parts[0]), 1, 1)
    except Exception:
        return None
    return None


def _to_float(v: float | str) -> float | None:
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _normalise(s: str) -> str:
    return s.lower().strip()


def detect_deltas(claims: list[NumericClaim]) -> list[Delta]:
    """Find (prior, current) pairs for the same metric using as_of dates.

    Rules:
    - Group by (normalised metric, normalised scope, normalised unit).
    - Within a group, only consider claims that have parseable as_of dates.
    - For each group with ≥2 dated claims, pick the earliest as prior and
      the latest as current.
    - Compute delta_pct = (current_val - prior_val) / |prior_val| * 100.
    - Skip if either value is non-numeric.
    """
    groups: dict[tuple, list[NumericClaim]] = {}
    for c in claims:
        key = (
            _normalise(c.metric),
            _normalise(c.scope or ""),
            _normalise(c.unit),
        )
        groups.setdefault(key, []).append(c)

    deltas: list[Delta] = []
    for (metric, scope, unit), group in groups.items():
        # Filter to claims with parseable dates
        dated = [(c, _parse_date(c.as_of)) for c in group]
        dated = [(c, d) for c, d in dated if d is not None]
        if len(dated) < 2:
            continue

        # Sort by date
        dated.sort(key=lambda x: x[1])
        prior_claim, prior_date = dated[0]
        current_claim, current_date = dated[-1]

        pv = _to_float(prior_claim.value)
        cv = _to_float(current_claim.value)
        if pv is None or cv is None or pv == 0:
            continue

        delta_pct = (cv - pv) / abs(pv) * 100.0

        deltas.append(Delta(
            metric=prior_claim.metric,
            prior=prior_claim,
            current=current_claim,
            delta_pct=round(delta_pct, 2),
            window_start=prior_date,
            window_end=current_date,
        ))

    # Sort by abs(delta_pct) descending — most significant changes first
    deltas.sort(key=lambda d: abs(d.delta_pct), reverse=True)
    return deltas
