"""Post-LLM deterministic validators for Agent 5 (no LLM calls)."""

from __future__ import annotations

from datetime import date, timedelta

from research.core.types import NewsEvent, RegulatoryChange, Disruption, NumericClaim


def filter_recent_events(events: list[NewsEvent], days: int = 90) -> list[NewsEvent]:
    """Drop events older than `days` from today."""
    cutoff = date.today() - timedelta(days=days)
    return [e for e in events if e.date >= cutoff]


def filter_disruptions_with_evidence(disruptions: list[Disruption]) -> list[Disruption]:
    """Drop disruptions that have no evidence citations."""
    return [d for d in disruptions if len(d.evidence) >= 1]


def filter_claims_with_citations(claims: list[NumericClaim]) -> list[NumericClaim]:
    """Drop claims missing a citation URL."""
    return [c for c in claims if c.citation and c.citation.url]


def assert_narrative_word_count(narrative: str, lo: int = 400, hi: int = 800) -> None:
    n = len(narrative.split())
    assert lo <= n <= hi, f"narrative word count {n} outside [{lo}, {hi}]"
