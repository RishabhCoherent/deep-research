"""Pydantic schemas for Agent 8 sub-agent I/O validation."""

from __future__ import annotations

from pydantic import BaseModel, model_validator

from research.core.types import Delta, CausationDraft, Causation


class DeltaBundle(BaseModel):
    """Output of delta_detector sub-agent (8a)."""
    deltas: list[Delta] = []

    @model_validator(mode="before")
    @classmethod
    def _coerce_shape(cls, data):
        if isinstance(data, list):
            return {"deltas": data}
        return data


class CorrelatedEvents(BaseModel):
    """Output of event_correlator sub-agent (8b)."""
    causations: list[CausationDraft] = []

    @model_validator(mode="before")
    @classmethod
    def _coerce_shape(cls, data):
        if isinstance(data, list):
            return {"causations": data}
        return data


class ValidatedCausations(BaseModel):
    """Output of evidence_validator (8c — pure Python)."""
    causations: list[Causation]


class A8Output(BaseModel):
    """Final node output — patches RunState.causations."""
    causations: list[Causation]
