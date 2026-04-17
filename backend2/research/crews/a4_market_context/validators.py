"""Post-LLM deterministic validators for Agent 4 (no LLM calls)."""

from __future__ import annotations

import re
from research.core.types import NumericClaim, Passage, ImpactItem


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def assert_impact_evidence(impacts: list[ImpactItem]) -> list[ImpactItem]:
    """Drop ImpactItems with no evidence citations."""
    return [item for item in impacts if len(item.evidence) >= 1]


def assert_claim_citations(claims: list[NumericClaim]) -> list[NumericClaim]:
    """Drop claims without a URL in their citation."""
    return [c for c in claims if c.citation and c.citation.url]


def assert_narrative_word_count(narrative: str, lo: int = 400, hi: int = 800) -> None:
    n = len(narrative.split())
    assert lo <= n <= hi, f"narrative word count {n} outside [{lo}, {hi}]"
