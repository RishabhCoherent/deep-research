"""Pydantic schemas for Agent 2 sub-agent I/O validation."""

from pydantic import BaseModel, field_validator
from research.core.types import SubQuestionDraft, SubQuestion
from .validators import _assert_atomic


class DecomposedQuestions(BaseModel):
    """Output of the decomposer sub-agent (2a)."""
    questions: list[SubQuestionDraft]

    @field_validator("questions")
    @classmethod
    def _size_and_source(cls, qs):
        assert 10 <= len(qs) <= 18, f"decomposer must output 10-18, got {len(qs)}"
        for q in qs:
            assert q.source == "decomposer", (
                f"source must be 'decomposer', got {q.source!r} for: {q.text!r}"
            )
        _assert_atomic(qs)
        return qs


class GappedQuestions(BaseModel):
    """Output of the gap analyzer sub-agent (2b)."""
    questions: list[SubQuestionDraft]

    @field_validator("questions")
    @classmethod
    def _has_decomposer_items(cls, qs):
        assert any(q.source == "decomposer" for q in qs), (
            "gap_analyzer must preserve original decomposer items"
        )
        _assert_atomic(qs)
        return qs


class PrioritizedQuestions(BaseModel):
    """Output of the prioritizer sub-agent (2c)."""
    questions: list[SubQuestion]

    @field_validator("questions")
    @classmethod
    def _final_rules(cls, qs):
        assert 8 <= len(qs) <= 15, f"final must be 8-15, got {len(qs)}"
        comps = [q.composite for q in qs]
        assert comps == sorted(comps, reverse=True), "must be sorted desc by composite"
        for q in qs:
            expected = round(0.6 * q.info_value + 0.4 * q.answerability, 2)
            assert abs(q.composite - expected) < 0.05, (
                f"composite mismatch for {q.text!r}: "
                f"expected {expected}, got {q.composite}"
            )
        _assert_atomic(qs)
        return qs


class A2Output(BaseModel):
    """Final output of the whole crew — written to RunState.sub_questions."""
    questions: list[SubQuestion]
