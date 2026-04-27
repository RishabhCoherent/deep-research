"""Deterministic authority-tier ranking. No LLM calls.

Hierarchy (lower rank = higher authority):
  0 = government
  1 = multilateral
  2 = industry_body
  3 = tier1_media
  4 = analyst_firm
  5 = trade_press
  6 = blog
  7 = unknown
"""

from __future__ import annotations

from research.core.types import AuthorityTier, NumericClaim

_TIER_RANK: dict[AuthorityTier, int] = {
    AuthorityTier.GOVERNMENT:    0,
    AuthorityTier.MULTILATERAL:  1,
    AuthorityTier.INDUSTRY_BODY: 2,
    AuthorityTier.TIER1_MEDIA:   3,
    AuthorityTier.ANALYST_FIRM:  4,
    AuthorityTier.TRADE_PRESS:   5,
    AuthorityTier.BLOG:          6,
    AuthorityTier.UNKNOWN:       7,
}


def tier_rank(tier: AuthorityTier | str | None) -> int:
    """Return numeric rank for a tier (lower = higher authority)."""
    if tier is None:
        return 7
    try:
        return _TIER_RANK.get(AuthorityTier(tier), 7)
    except ValueError:
        return 7


def compare_authority(a: AuthorityTier | str, b: AuthorityTier | str) -> int:
    """Return -1 if a has higher authority than b, 0 if equal, +1 if lower."""
    ra, rb = tier_rank(a), tier_rank(b)
    if ra < rb:
        return -1
    if ra > rb:
        return 1
    return 0


def _date_ord(date_str: str | None) -> int:
    """Parse an ISO-like date string to a sortable ordinal. Returns 0 on failure."""
    if not date_str:
        return 0
    try:
        from datetime import date
        trimmed = date_str.strip()[:10]
        return date.fromisoformat(trimmed).toordinal()
    except Exception:
        return 0


def _claim_sort_key(claim: NumericClaim) -> tuple[int, int]:
    """Lower tuple = higher priority (higher authority, more recent)."""
    tier = claim.citation.authority_tier if claim.citation else AuthorityTier.UNKNOWN
    rank = tier_rank(tier)
    recency = _date_ord(claim.as_of) or _date_ord(
        claim.citation.published if claim.citation else None
    )
    return (rank, -recency)


def pick_winner(claims: list[NumericClaim]) -> NumericClaim:
    """Pick the best claim: highest authority, recency as tiebreak."""
    return sorted(claims, key=_claim_sort_key)[0]


def rank_reason(winner: NumericClaim, loser: NumericClaim) -> str:
    """Generate a human-readable rejection reason for `loser`."""
    wt = winner.citation.authority_tier if winner.citation else AuthorityTier.UNKNOWN
    lt = loser.citation.authority_tier if loser.citation else AuthorityTier.UNKNOWN
    cmp = compare_authority(wt, lt)
    if cmp < 0:
        return (
            f"lower authority tier ({lt}) vs winner's {wt}"
        )
    if cmp == 0:
        w_date = winner.as_of or (winner.citation.published if winner.citation else "?")
        l_date = loser.as_of or (loser.citation.published if loser.citation else "?")
        return f"same tier ({lt}) but older source ({l_date} vs {w_date})"
    return f"lower authority ({lt})"
