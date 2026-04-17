"""Pydantic schemas for Agent 3 sub-agent I/O validation."""

from __future__ import annotations

from pydantic import BaseModel, field_validator
from research.core.types import (
    PlannedSearch, Passage, NumericClaim, Observation, Footnote
)


class SearchPlan(BaseModel):
    """Output of the search_planner sub-agent (3a)."""
    plans: list[PlannedSearch]

    @field_validator("plans")
    @classmethod
    def _bounds(cls, ps):
        assert 1 <= len(ps) <= 8, f"plans must be 1-8, got {len(ps)}"
        total_q = sum(len(p.queries) for p in ps)
        assert total_q <= 12, f"total planned queries {total_q} > 12 (hard cap)"
        return ps


class FetchedSources(BaseModel):
    """Output of the source_fetcher sub-agent (3b)."""
    passages: list[Passage]

    @field_validator("passages")
    @classmethod
    def _dedupe_and_cap(cls, ps):
        urls = [p.url for p in ps]
        assert len(set(urls)) == len(urls), "duplicate URLs in passages"
        assert len(ps) <= 12, f"too many passages kept: {len(ps)} > 12"
        return ps


class ExtractedClaims(BaseModel):
    """Output of the claim_extractor sub-agent (3c)."""
    claims: list[NumericClaim]


class TopicSummary(BaseModel):
    """Output of the topic_summarizer sub-agent (3d)."""
    narrative: str
    footnotes: list[Footnote]
    scratchpad_writes: list[Observation]

    @field_validator("scratchpad_writes")
    @classmethod
    def _topic_section(cls, ws):
        for w in ws:
            assert w.section == "topic", f"section must be 'topic', got {w.section!r}"
        assert 0 <= len(ws) <= 7, f"expected 0-7 scratchpad writes, got {len(ws)}"
        return ws


class A3Output(BaseModel):
    """Final crew output — node fans into RunState patch."""
    claims: list[NumericClaim]
    narrative: str
    scratchpad_writes: list[Observation]
