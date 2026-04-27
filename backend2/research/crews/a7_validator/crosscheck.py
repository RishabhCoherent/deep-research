"""Deterministic grouping, % diff, range rule, and conflict resolution. No LLM calls."""

from __future__ import annotations

from research.core.types import NumericClaim, ConflictCandidate, Conflict, RangeValue
from .authority import pick_winner, rank_reason, tier_rank

RANGE_THRESHOLD_PCT: float = 5.0


# ── Value helpers ──────────────────────────────────────────────────────────

def _to_float(v: float | str) -> float | None:
    """Coerce value to float, return None if non-numeric."""
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def pct_diff(a: float, b: float) -> float:
    """Symmetric percentage difference between two numbers."""
    avg = (abs(a) + abs(b)) / 2.0
    if avg == 0:
        return 0.0
    return abs(a - b) / avg * 100.0


def should_emit_range(v1: float, v2: float) -> bool:
    """True when two finalist claims are within RANGE_THRESHOLD_PCT of each other."""
    return pct_diff(v1, v2) <= RANGE_THRESHOLD_PCT


def max_pct_diff_group(claims: list[NumericClaim]) -> float:
    """Maximum pairwise % difference among numeric values in a group."""
    values = [_to_float(c.value) for c in claims]
    values = [v for v in values if v is not None]
    if len(values) < 2:
        return 0.0
    max_d = 0.0
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            max_d = max(max_d, pct_diff(values[i], values[j]))
    return round(max_d, 2)


# ── Grouping ───────────────────────────────────────────────────────────────

def _normalise_key(s: str | None) -> str:
    return (s or "").lower().strip()


def group_claims(
    claims: list[NumericClaim],
) -> tuple[list[NumericClaim], list[ConflictCandidate]]:
    """Group claims by (normalised_metric, scope).

    Returns:
        unanimous: claims whose group has exactly one member (no conflict).
        candidates: ConflictCandidates for groups with ≥2 members.
    """
    groups: dict[tuple[str, str], list[NumericClaim]] = {}
    for c in claims:
        key = (_normalise_key(c.metric), _normalise_key(c.scope))
        groups.setdefault(key, []).append(c)

    unanimous: list[NumericClaim] = []
    candidates: list[ConflictCandidate] = []

    for (metric, scope), group_claims in groups.items():
        if len(group_claims) == 1:
            unanimous.append(group_claims[0])
        else:
            candidates.append(ConflictCandidate(
                metric=metric,
                scope=scope or None,
                claims=group_claims,
                max_diff_pct=max_pct_diff_group(group_claims),
            ))

    return unanimous, candidates


# ── Conflict resolution ────────────────────────────────────────────────────

def resolve_candidate(
    candidate: ConflictCandidate,
) -> tuple[NumericClaim | RangeValue, list[tuple[NumericClaim, str]]]:
    """Deterministically resolve a conflict candidate.

    Returns:
        winner: the best NumericClaim, or a RangeValue if two finalists are within 5%.
        rejected: list of (claim, reason) pairs for the audit trail.
    """
    claims = candidate.claims
    winner = pick_winner(claims)
    losers = [c for c in claims if c is not winner]

    # Check if winner and best loser are within 5% — if so, emit range
    if losers:
        second = pick_winner(losers)
        wv = _to_float(winner.value)
        sv = _to_float(second.value)
        if wv is not None and sv is not None and should_emit_range(wv, sv):
            low, high = min(wv, sv), max(wv, sv)
            unit = winner.unit
            range_val = RangeValue(low=low, high=high, unit=unit)
            # Build rejected trail for ALL non-winners
            rejected = [(c, rank_reason(winner, c)) for c in losers]
            return range_val, rejected

    rejected = [(loser, rank_reason(winner, loser)) for loser in losers]
    return winner, rejected


def resolve_all(
    unanimous: list[NumericClaim],
    candidates: list[ConflictCandidate],
) -> tuple[list[NumericClaim], list[Conflict]]:
    """Resolve all conflict candidates. Return validated claims and Conflict audit trail.

    RangeValue winners are stored as a NumericClaim with value = "low–high"
    and a note in raw_excerpt.
    """
    validated: list[NumericClaim] = list(unanimous)
    conflicts: list[Conflict] = []

    for candidate in candidates:
        winner_or_range, rejected_pairs = resolve_candidate(candidate)

        if isinstance(winner_or_range, RangeValue):
            rv = winner_or_range
            # Synthesise a range claim from the winning claim
            base_claim = pick_winner(candidate.claims)
            range_claim = base_claim.model_copy(update={
                "value": f"{rv.low}–{rv.high}",
                "unit": rv.unit,
                "raw_excerpt": (
                    f"[Range: two highest-authority sources within 5%: "
                    f"{rv.low}–{rv.high} {rv.unit}] " + base_claim.raw_excerpt
                ),
            })
            validated.append(range_claim)
            conflicts.append(Conflict(
                chosen=range_claim,
                rejected=list(rejected_pairs),
            ))
        else:
            validated.append(winner_or_range)
            if rejected_pairs:
                conflicts.append(Conflict(
                    chosen=winner_or_range,
                    rejected=list(rejected_pairs),
                ))

    return validated, conflicts
