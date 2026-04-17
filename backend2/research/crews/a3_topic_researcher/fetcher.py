"""Deterministic helpers for source deduplication and authority×relevance scoring."""

from __future__ import annotations

from research.core.types import Passage, AuthorityTier
from research.pipeline.authority import tier_rank

_TIER_SCORE: dict[AuthorityTier, float] = {
    AuthorityTier.GOVERNMENT:    1.0,
    AuthorityTier.MULTILATERAL:  0.95,
    AuthorityTier.INDUSTRY_BODY: 0.85,
    AuthorityTier.TIER1_MEDIA:   0.80,
    AuthorityTier.ANALYST_FIRM:  0.90,
    AuthorityTier.TRADE_PRESS:   0.65,
    AuthorityTier.BLOG:          0.40,
}


def _relevance_score(passage: Passage, query: str) -> float:
    """Simple token-overlap relevance between passage text and query."""
    q_tokens = set(query.lower().split())
    p_tokens = set(passage.text.lower().split())
    if not q_tokens:
        return 0.0
    overlap = len(q_tokens & p_tokens) / len(q_tokens)
    return min(overlap, 1.0)


def authority_score(passage: Passage) -> float:
    """Return authority score in [0, 1] for the passage's tier."""
    return _TIER_SCORE.get(passage.authority_tier, 0.40)


def composite_score(passage: Passage, query: str) -> float:
    """authority × relevance composite score."""
    return authority_score(passage) * _relevance_score(passage, query)


def dedupe_by_url(passages: list[Passage]) -> list[Passage]:
    """Remove duplicate passages keeping the first occurrence per URL."""
    seen: set[str] = set()
    result: list[Passage] = []
    for p in passages:
        canonical = p.url.rstrip("/").split("?")[0]
        if canonical not in seen:
            seen.add(canonical)
            result.append(p)
    return result


def rank_passages(passages: list[Passage], query: str, top_n: int = 12) -> list[Passage]:
    """Dedupe, score by authority×relevance, return top_n sorted desc."""
    deduped = dedupe_by_url(passages)
    scored = sorted(deduped, key=lambda p: composite_score(p, query), reverse=True)
    return scored[:top_n]
