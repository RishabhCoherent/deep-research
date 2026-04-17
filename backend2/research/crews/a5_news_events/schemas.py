"""Pydantic schemas for Agent 5 sub-agent I/O validation."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from research.core.types import (
    Citation, NumericClaim, Observation,
    NewsEvent, RegulatoryChange, Disruption,
)


class EventBundle(BaseModel):
    """Output of the event_hunter sub-agent (5a)."""
    events: list[NewsEvent]

    @field_validator("events")
    @classmethod
    def _at_least_one(cls, v: list) -> list:
        assert len(v) >= 1, "event_hunter must return at least 1 news event"
        return v


class RegulatoryBundle(BaseModel):
    """Output of the regulatory_tracker sub-agent (5b)."""
    changes: list[RegulatoryChange]

    @field_validator("changes")
    @classmethod
    def _at_least_one(cls, v: list) -> list:
        assert len(v) >= 1, "regulatory_tracker must return at least 1 regulatory change"
        return v


class GeopoliticalBundle(BaseModel):
    """Output of the geopolitical_scanner sub-agent (5c)."""
    disruptions: list[Disruption]
    scratchpad_writes: list[Observation]

    @field_validator("disruptions")
    @classmethod
    def _each_has_evidence(cls, items: list) -> list:
        for d in items:
            assert len(d.evidence) >= 1, (
                f"Disruption '{d.upstream_node}' must have at least one evidence citation"
            )
        return items

    @field_validator("scratchpad_writes")
    @classmethod
    def _news_section(cls, ws: list) -> list:
        for w in ws:
            assert w.section == "news", (
                f"scratchpad_writes must use section='news', got {w.section!r}"
            )
        return ws


class A5Output(BaseModel):
    """Final crew output — node patches RunState."""
    claims: list[NumericClaim]
    narrative: str
    scratchpad_writes: list[Observation]
