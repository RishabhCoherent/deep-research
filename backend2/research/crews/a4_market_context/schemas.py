"""Pydantic schemas for Agent 4 sub-agent I/O validation."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from research.core.types import (
    Citation, NumericClaim, Observation,
    ChainNode, SubstituteEntry, ImpactItem,
)


class ParentMarketResult(BaseModel):
    """Output of the parent_market_identifier sub-agent (4a)."""
    child: str = Field(default="", max_length=200)
    parent: str = Field(default="", max_length=200)
    grandparent: str = Field(default="", max_length=200)
    justification: str = Field(default="")
    citations: list[Citation] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_shape(cls, data):
        if not isinstance(data, dict):
            return {"child": "", "parent": "", "grandparent": "", "justification": "", "citations": []}
        data.setdefault("child", "")
        data.setdefault("parent", "")
        data.setdefault("grandparent", "")
        data.setdefault("justification", "")
        data.setdefault("citations", [])
        return data


class ValueChainMap(BaseModel):
    """Output of the value_chain_mapper sub-agent (4b)."""
    upstream: list[ChainNode] = Field(default_factory=list)
    midstream: list[ChainNode] = Field(default_factory=list)
    downstream: list[ChainNode] = Field(default_factory=list)
    substitutes: list[SubstituteEntry] = Field(default_factory=list)
    scratchpad_writes: list[Observation] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_shape(cls, data):
        if not isinstance(data, dict):
            return {"upstream": [], "midstream": [], "downstream": [], "substitutes": [], "scratchpad_writes": []}
        data.setdefault("upstream", [])
        data.setdefault("midstream", [])
        data.setdefault("downstream", [])
        data.setdefault("substitutes", [])
        data.setdefault("scratchpad_writes", [])
        return data

    @field_validator("scratchpad_writes")
    @classmethod
    def _market_context_section(cls, ws: list) -> list:
        # Silently drop wrong-section writes instead of crashing
        valid = [w for w in ws if w.section == "market_context"]
        return valid[:10]


class ImpactAnalysis(BaseModel):
    """Output of the impact_analyst sub-agent (4c)."""
    impacts: list[ImpactItem] = Field(default_factory=list)
    claims: list[NumericClaim] = Field(default_factory=list)
    narrative: str = ""

    @model_validator(mode="before")
    @classmethod
    def _coerce_shape(cls, data):
        if not isinstance(data, dict):
            return {"impacts": [], "claims": [], "narrative": ""}
        data.setdefault("impacts", [])
        data.setdefault("claims", [])
        data.setdefault("narrative", "")
        return data


class A4Output(BaseModel):
    """Final crew output — node patches RunState."""
    claims: list[NumericClaim]
    narrative: str
    scratchpad_writes: list[Observation]
