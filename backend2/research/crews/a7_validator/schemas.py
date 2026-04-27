"""Pydantic schemas for Agent 7 sub-agent I/O validation."""

from __future__ import annotations

from pydantic import BaseModel, field_validator, model_validator

from research.core.types import NumericClaim, Conflict, ConflictCandidate


class RankedClaims(BaseModel):
    """Output of the authority_ranker sub-agent (7a)."""
    claims: list[NumericClaim] = []

    @model_validator(mode="before")
    @classmethod
    def _coerce_shape(cls, data):
        if isinstance(data, list):
            return {"claims": data}
        return data


class CrossCheckResult(BaseModel):
    """Output of the numeric_cross_checker sub-agent (7b)."""
    unanimous: list[NumericClaim] = []
    conflicted: list[ConflictCandidate] = []

    @field_validator("conflicted")
    @classmethod
    def _candidates_min_2(cls, v: list) -> list:
        # Silently drop malformed candidates instead of crashing
        return [c for c in v if len(c.claims) >= 2]


class RecencyResult(BaseModel):
    """Output of the recency_judge sub-agent (7c)."""
    candidates: list[ConflictCandidate] = []


class ValidationResult(BaseModel):
    """Output of the conflict_resolver sub-agent (7d)."""
    validated_claims: list[NumericClaim] = []
    conflicts: list[Conflict] = []

    @model_validator(mode="before")
    @classmethod
    def _coerce_shape(cls, data):
        if isinstance(data, list):
            return {"validated_claims": data, "conflicts": []}
        return data


class A7Output(BaseModel):
    """Final crew output — node patches RunState."""
    validated_claims: list[NumericClaim]
    conflicts: list[Conflict]
