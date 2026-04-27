"""Pydantic schemas for Agent 6 sub-agent I/O validation."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from research.core.types import (
    NumericClaim, Observation, Theme, Footnote, ConsolidatedReport,
)


class NormalisedClaims(BaseModel):
    """Output of the claim_normaliser sub-agent (6a)."""
    claims: list[NumericClaim] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_shape(cls, data):
        if isinstance(data, list):
            return {"claims": data}
        if not isinstance(data, dict):
            return {"claims": []}
        data.setdefault("claims", [])
        return data


class ThemeBundle(BaseModel):
    """Output of the theme_clusterer sub-agent (6b)."""
    themes: list[Theme] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_shape(cls, data):
        if isinstance(data, list):
            return {"themes": data}
        if not isinstance(data, dict):
            return {"themes": []}
        data.setdefault("themes", [])
        return data

    @field_validator("themes")
    @classmethod
    def _cap_themes(cls, v: list) -> list:
        return v[:8]


class ConsolidatedNarrative(BaseModel):
    """Output of the narrative_builder sub-agent (6c)."""
    narrative: str = ""
    footnotes: list[Footnote] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_shape(cls, data):
        if not isinstance(data, dict):
            return {"narrative": "", "footnotes": []}
        data.setdefault("narrative", "")
        data.setdefault("footnotes", [])
        return data

    @field_validator("footnotes")
    @classmethod
    def _dedup_ids(cls, fns: list) -> list:
        seen: set[int] = set()
        out = []
        for f in fns:
            if f.n not in seen:
                seen.add(f.n)
                out.append(f)
        return out


class A6Output(BaseModel):
    """Final crew output — node writes RunState.consolidated."""
    consolidated: ConsolidatedReport
