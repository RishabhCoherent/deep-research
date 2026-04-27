"""Pydantic schemas for Agent 3 sub-agent I/O validation."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator
from research.core.types import (
    PlannedSearch, Passage, NumericClaim, Observation, Footnote
)


class SearchPlan(BaseModel):
    """Output of the search_planner sub-agent (3a)."""
    plans: list[PlannedSearch]

    @field_validator("plans")
    @classmethod
    def _bounds(cls, ps):
        assert 1 <= len(ps) <= 12, f"plans must be 1-12, got {len(ps)}"
        return ps


class FetchedSources(BaseModel):
    """Output of the source_fetcher sub-agent (3b)."""
    passages: list[Passage] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_shape(cls, data):
        """Handle LLM returning a single passage dict or a bare list instead of {passages:[...]}."""
        if isinstance(data, dict):
            if "passages" not in data:
                # LLM returned a bare passage dict — wrap it
                if "url" in data:
                    return {"passages": [data]}
                # LLM returned some other dict — try to extract any list value
                for v in data.values():
                    if isinstance(v, list):
                        return {"passages": v}
                return {"passages": []}
        elif isinstance(data, list):
            return {"passages": data}
        return data

    @field_validator("passages")
    @classmethod
    def _dedupe_and_cap(cls, ps):
        # Dedupe by URL, keep first occurrence
        seen: set[str] = set()
        unique = []
        for p in ps:
            if p.url not in seen:
                seen.add(p.url)
                unique.append(p)
        return unique[:40]


class ExtractedClaims(BaseModel):
    """Output of the claim_extractor sub-agent (3c)."""
    claims: list[NumericClaim] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_shape(cls, data):
        if isinstance(data, dict) and "claims" not in data:
            # LLM returned a single claim dict or bare list
            if isinstance(data.get("metric"), str):
                return {"claims": [data]}
        elif isinstance(data, list):
            return {"claims": data}
        return data


class TopicSummary(BaseModel):
    """Output of the topic_summarizer sub-agent (3d)."""
    narrative: str = ""
    footnotes: list[Footnote] = Field(default_factory=list)
    scratchpad_writes: list[Observation] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_shape(cls, data):
        """Handle LLM returning a partial or malformed dict (e.g. observation_json)."""
        if isinstance(data, dict):
            if "narrative" not in data and "footnotes" not in data and "scratchpad_writes" not in data:
                # LLM returned something completely wrong — return empty shell; fallback handles it
                return {"narrative": "", "footnotes": [], "scratchpad_writes": []}
        return data

    @field_validator("scratchpad_writes")
    @classmethod
    def _topic_section(cls, ws):
        # Silently drop any writes with wrong section rather than crashing
        valid = [w for w in ws if w.section == "topic"]
        return valid[:7]


class A3Output(BaseModel):
    """Final crew output — node fans into RunState patch."""
    claims: list[NumericClaim]
    narrative: str
    scratchpad_writes: list[Observation]
