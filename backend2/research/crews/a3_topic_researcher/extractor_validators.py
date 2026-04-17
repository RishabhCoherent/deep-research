"""Post-LLM validators for claim extraction (deterministic, no LLM)."""

from __future__ import annotations

import re
from research.core.types import NumericClaim, Passage


def _norm(s: str) -> str:
    """Normalise whitespace and lowercase for substring matching."""
    return re.sub(r"\s+", " ", s).strip().lower()


def assert_excerpts_in_passages(
    claims: list[NumericClaim],
    passages: list[Passage],
) -> list[NumericClaim]:
    """Keep only claims whose raw_excerpt appears in its source passage.

    Silently drops violators; caller should log the drop count.
    Returns the filtered list.
    """
    by_url: dict[str, str] = {p.url: _norm(p.text) for p in passages}
    valid: list[NumericClaim] = []
    for claim in claims:
        passage_text = by_url.get(claim.citation.url)
        if passage_text is None:
            continue
        if _norm(claim.raw_excerpt) in passage_text:
            valid.append(claim)
    return valid


def assert_citation_complete(claims: list[NumericClaim]) -> list[NumericClaim]:
    """Drop claims missing a citation URL."""
    return [c for c in claims if c.citation and c.citation.url]
