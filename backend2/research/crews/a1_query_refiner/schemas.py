"""Pydantic schemas for Agent 1 sub-agent I/O validation."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from research.core.types import IntentKind, AngleKind, Variant, ScoredVariant


_INTENT_FALLBACK_MAP: dict[str, IntentKind] = {
    "supply_chain":  IntentKind.MARKET_SIZING,
    "market":        IntentKind.MARKET_SIZING,
    "forecast":      IntentKind.MARKET_SIZING,
    "sizing":        IntentKind.MARKET_SIZING,
    "competition":   IntentKind.COMPETITIVE,
    "landscape":     IntentKind.COMPETITIVE,
    "policy":        IntentKind.REGULATORY,
    "regulation":    IntentKind.REGULATORY,
    "geo":           IntentKind.GEOGRAPHIC,
    "region":        IntentKind.GEOGRAPHIC,
    "tech":          IntentKind.TECHNOLOGY,
    "innovation":    IntentKind.TECHNOLOGY,
    "trend":         IntentKind.TREND,
}


class IntentClassification(BaseModel):
    """Output of the intent classifier sub-agent."""
    intent: IntentKind
    confidence: float = Field(..., ge=0, le=1)
    reasoning: str = Field(..., max_length=600)

    @field_validator("intent", mode="before")
    @classmethod
    def _coerce_intent(cls, v: str) -> str:
        """Map LLM-invented intent strings to the nearest valid IntentKind."""
        if isinstance(v, str) and v not in IntentKind._value2member_map_:
            v_lower = v.lower().replace("-", "_")
            # exact match after normalisation
            if v_lower in IntentKind._value2member_map_:
                return v_lower
            # keyword fallback
            for keyword, mapped in _INTENT_FALLBACK_MAP.items():
                if keyword in v_lower:
                    return mapped.value
            return IntentKind.GENERAL.value
        return v


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
        """Validate exactly 4 variants — auto-sort desc by composite so LLM order doesn't matter."""
        assert len(s) == 4, "must have exactly 4 scored variants"
        return sorted(s, key=lambda x: x.composite, reverse=True)


class A1Output(BaseModel):
    """Final output of the whole crew (what a1_node writes to RunState)."""
    intent: IntentKind
    variants_sorted: list[ScoredVariant]  # len 4, desc
    chosen_query: Optional[str] = None  # filled after ask_user
