"""Pydantic schemas for Agent 1 sub-agent I/O validation."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from research.core.types import IntentKind, AngleKind, Variant, ScoredVariant


class IntentClassification(BaseModel):
    """Output of the intent classifier sub-agent."""
    intent: IntentKind
    confidence: float = Field(..., ge=0, le=1)
    reasoning: str = Field(..., max_length=400)


class VariantBundle(BaseModel):
    """Output of the variant generator sub-agent."""
    variants: list[Variant]
    
    @field_validator("variants")
    @classmethod
    def _four_unique_angles(cls, vs):
        """Validate exactly 4 variants with unique angles."""
        assert len(vs) == 4, "must produce exactly 4 variants"
        angles = {v.angle for v in vs}
        assert len(angles) == 4, "all four angles must be distinct"
        texts = {v.text.lower().strip() for v in vs}
        assert len(texts) == 4, "variants must be unique"
        return vs


class ScoredBundle(BaseModel):
    """Output of the clarity scorer sub-agent."""
    scored: list[ScoredVariant]
    
    @field_validator("scored")
    @classmethod
    def _sorted_desc(cls, s):
        """Validate exactly 4 variants sorted by composite score."""
        assert len(s) == 4, "must have exactly 4 scored variants"
        comps = [x.composite for x in s]
        assert comps == sorted(comps, reverse=True), "must be sorted desc by composite"
        return s


class A1Output(BaseModel):
    """Final output of the whole crew (what a1_node writes to RunState)."""
    intent: IntentKind
    variants_sorted: list[ScoredVariant]  # len 4, desc
    chosen_query: Optional[str] = None  # filled after ask_user
