"""Unit tests for Agent 2 validators."""

import pytest
from research.core.types import IntentKind, QuestionCategory, SubQuestionDraft, SubQuestion
from research.crews.a2_question_generator.validators import (
    _assert_atomic, assert_checklist_coverage, missing_categories
)


def _draft(text, category, source="decomposer"):
    return SubQuestionDraft(text=text, category=category, source=source,
                            geography="global", time_frame="2026")


def _sq(category):
    comp = round(0.6 * 7.0 + 0.4 * 7.0, 2)
    return SubQuestion(
        text=f"What is the {category} 2026 global?",
        category=category, source="decomposer",
        info_value=7.0, answerability=7.0, composite=comp,
        reason="Test question.", geography="global", time_frame="2026"
    )


class TestAssertAtomic:

    def test_clean_question_passes(self):
        drafts = [_draft("What is the 2026 global market size in USD billion?", "size")]
        _assert_atomic(drafts)

    def test_compound_and_rejected(self):
        drafts = [_draft("What is the size and share of the EV battery market?", "size")]
        with pytest.raises(AssertionError, match="compound question rejected"):
            _assert_atomic(drafts)

    def test_list_with_commas_allowed(self):
        # "NMC, LFP, and solid-state" has commas so is NOT a compound clause
        drafts = [_draft("What is the market share of NMC, LFP, and solid-state chemistries?", "segmentation")]
        _assert_atomic(drafts)  # should not raise

    def test_plus_marker_rejected(self):
        drafts = [_draft("What is the size plus the growth rate?", "size")]
        with pytest.raises(AssertionError, match="compound question rejected"):
            _assert_atomic(drafts)


class TestChecklistCoverage:

    def _questions_for(self, *categories):
        return [_sq(c) for c in categories]

    def test_market_sizing_full_coverage(self):
        qs = self._questions_for(
            QuestionCategory.SIZE, QuestionCategory.SEGMENTATION,
            QuestionCategory.GEOGRAPHY, QuestionCategory.OUTLOOK,
            QuestionCategory.DRIVERS, QuestionCategory.CONSTRAINTS,
        )
        assert_checklist_coverage(IntentKind.MARKET_SIZING, qs)

    def test_market_sizing_missing_segmentation(self):
        qs = self._questions_for(
            QuestionCategory.SIZE, QuestionCategory.GEOGRAPHY,
            QuestionCategory.OUTLOOK, QuestionCategory.DRIVERS,
            QuestionCategory.CONSTRAINTS,
        )
        with pytest.raises(AssertionError, match="segmentation"):
            assert_checklist_coverage(IntentKind.MARKET_SIZING, qs)

    def test_regulatory_full_coverage(self):
        qs = self._questions_for(
            QuestionCategory.REGULATORY, QuestionCategory.CONSTRAINTS,
            QuestionCategory.MACRO, QuestionCategory.SIZE,
            QuestionCategory.DRIVERS,
        )
        assert_checklist_coverage(IntentKind.REGULATORY, qs)

    def test_competitive_full_coverage(self):
        qs = self._questions_for(
            QuestionCategory.COMPETITIVE, QuestionCategory.SEGMENTATION,
            QuestionCategory.GEOGRAPHY, QuestionCategory.SIZE,
            QuestionCategory.DRIVERS, QuestionCategory.CONSTRAINTS,
        )
        assert_checklist_coverage(IntentKind.COMPETITIVE, qs)

    def test_technology_full_coverage(self):
        qs = self._questions_for(
            QuestionCategory.TECHNOLOGY, QuestionCategory.COMPETITIVE,
            QuestionCategory.OUTLOOK, QuestionCategory.SIZE,
            QuestionCategory.DRIVERS, QuestionCategory.CONSTRAINTS,
        )
        assert_checklist_coverage(IntentKind.TECHNOLOGY, qs)

    def test_missing_categories_returns_list(self):
        qs = self._questions_for(QuestionCategory.SIZE)
        missing = missing_categories(IntentKind.MARKET_SIZING, qs)
        assert QuestionCategory.SEGMENTATION in missing
        assert QuestionCategory.GEOGRAPHY in missing
