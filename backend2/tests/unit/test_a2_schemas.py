"""Unit tests for Agent 2 schemas."""

import pytest
from pydantic import ValidationError
from research.core.types import QuestionCategory, SubQuestionDraft, SubQuestion
from research.crews.a2_question_generator.schemas import (
    DecomposedQuestions, GappedQuestions, PrioritizedQuestions, A2Output
)


def _make_draft(text="What is the 2026 global market size in USD billion?",
                category="size", source="decomposer") -> SubQuestionDraft:
    return SubQuestionDraft(text=text, category=category, source=source,
                            geography="global", time_frame="2026")


def _make_scored(text="What is the 2026 global market size?",
                 category="size", iv=8.0, av=7.0, source="decomposer") -> SubQuestion:
    comp = round(0.6 * iv + 0.4 * av, 2)
    return SubQuestion(text=text, category=category, source=source,
                       info_value=iv, answerability=av, composite=comp,
                       reason="Core metric, easily sourced.", geography="global",
                       time_frame="2026")


class TestDecomposedQuestions:

    def test_valid_decomposed(self):
        drafts = [_make_draft(f"Question {i} 2026 global?") for i in range(10)]
        dq = DecomposedQuestions(questions=drafts)
        assert len(dq.questions) == 10

    def test_too_few_items(self):
        drafts = [_make_draft(f"Q {i}") for i in range(9)]
        with pytest.raises(ValidationError, match="10-18"):
            DecomposedQuestions(questions=drafts)

    def test_too_many_items(self):
        drafts = [_make_draft(f"Q {i} global 2026?") for i in range(19)]
        with pytest.raises(ValidationError, match="10-18"):
            DecomposedQuestions(questions=drafts)

    def test_wrong_source(self):
        drafts = [_make_draft(f"Q {i}", source="gap_fill") for i in range(10)]
        with pytest.raises(ValidationError, match="source must be 'decomposer'"):
            DecomposedQuestions(questions=drafts)

    def test_compound_question_rejected(self):
        drafts = [_make_draft(f"Q {i} global 2026?") for i in range(9)]
        drafts.append(_make_draft("What is the size and share of the market 2026?"))
        with pytest.raises(ValidationError, match="compound question rejected"):
            DecomposedQuestions(questions=drafts)


class TestGappedQuestions:

    def test_valid_gapped(self):
        drafts = [_make_draft(f"Q {i} 2026 global?") for i in range(5)]
        gap = _make_draft("What is the regulatory outlook 2026?", source="gap_fill")
        gq = GappedQuestions(questions=drafts + [gap])
        assert any(q.source == "gap_fill" for q in gq.questions)

    def test_no_decomposer_items_rejected(self):
        only_gap = [_make_draft(f"Q {i}", source="gap_fill") for i in range(5)]
        with pytest.raises(ValidationError, match="preserve original decomposer items"):
            GappedQuestions(questions=only_gap)


class TestPrioritizedQuestions:

    def _valid_scored_list(self, n=8):
        items = []
        for i in range(n):
            iv = 9.0 - i * 0.1
            av = 8.0 - i * 0.1
            items.append(_make_scored(
                text=f"Question {i} global 2026?",
                category="size",
                iv=iv, av=av,
            ))
        return items

    def test_valid_prioritized(self):
        pq = PrioritizedQuestions(questions=self._valid_scored_list(8))
        assert len(pq.questions) == 8

    def test_too_few(self):
        with pytest.raises(ValidationError, match="8-15"):
            PrioritizedQuestions(questions=self._valid_scored_list(7))

    def test_too_many(self):
        with pytest.raises(ValidationError, match="8-15"):
            PrioritizedQuestions(questions=self._valid_scored_list(16))

    def test_unsorted_rejected(self):
        items = self._valid_scored_list(8)
        items[0], items[-1] = items[-1], items[0]  # swap best and worst
        with pytest.raises(ValidationError, match="sorted desc"):
            PrioritizedQuestions(questions=items)

    def test_composite_mismatch_rejected(self):
        items = self._valid_scored_list(8)
        # nudge composite by +0.5 on every item so sort order is preserved
        # but the formula check (0.6*iv + 0.4*av) will not match
        fixed = [q.model_copy(update={"composite": round(q.composite + 0.5, 2)})
                 for q in items]
        with pytest.raises(ValidationError, match="composite mismatch"):
            PrioritizedQuestions(questions=fixed)

    def test_composite_formula_correct(self):
        item = _make_scored(iv=8.0, av=6.0)
        expected = round(0.6 * 8.0 + 0.4 * 6.0, 2)
        assert abs(item.composite - expected) < 0.01
