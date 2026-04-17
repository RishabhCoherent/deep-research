"""Pydantic schemas for Agent 4 sub-agent I/O validation."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from research.core.types import (
    Citation, NumericClaim, Observation,
    ChainNode, SubstituteEntry, ImpactItem,
)


class ParentMarketResult(BaseModel):
    """Output of the parent_market_identifier sub-agent (4a)."""
    child: str = Field(..., max_length=200)
    parent: str = Field(..., max_length=200)
    grandparent: str = Field(..., max_length=200)
    justification: str = Field(..., max_length=500)
    citations: list[Citation]

    @field_validator("citations")
    @classmethod
    def _at_least_one(cls, c: list) -> list:
        assert len(c) >= 1, "at least one citation is required"
        return c


class ValueChainMap(BaseModel):
    """Output of the value_chain_mapper sub-agent (4b)."""
    upstream: list[ChainNode]
    midstream: list[ChainNode]
    downstream: list[ChainNode]
    substitutes: list[SubstituteEntry]
    scratchpad_writes: list[Observation]

    @field_validator("upstream")
    @classmethod
    def _upstream_nonempty(cls, u: list) -> list:
        assert len(u) >= 2, "need ≥ 2 upstream nodes"
        return u

    @field_validator("midstream")
    @classmethod
    def _midstream_nonempty(cls, m: list) -> list:
        assert len(m) >= 1, "need ≥ 1 midstream node"
        return m

    @field_validator("scratchpad_writes")
    @classmethod
    def _market_context_section(cls, ws: list) -> list:
        for w in ws:
            assert w.section == "market_context", (
                f"scratchpad_writes must use section='market_context', got {w.section!r}"
            )
        assert 1 <= len(ws) <= 10, f"expected 1-10 scratchpad writes, got {len(ws)}"
        return ws


class ImpactAnalysis(BaseModel):
    """Output of the impact_analyst sub-agent (4c)."""
    impacts: list[ImpactItem]
    claims: list[NumericClaim]
    narrative: str

    @field_validator("impacts")
    @classmethod
    def _each_has_evidence(cls, items: list) -> list:
        for item in items:
            assert len(item.evidence) >= 1, (
                f"ImpactItem '{item.force}' must have at least one evidence citation"
            )
        return items

    @field_validator("narrative")
    @classmethod
    def _narrative_nonempty(cls, n: str) -> str:
        assert len(n.split()) >= 50, "narrative must be at least 50 words"
        return n


class A4Output(BaseModel):
    """Final crew output — node patches RunState."""
    claims: list[NumericClaim]
    narrative: str
    scratchpad_writes: list[Observation]
