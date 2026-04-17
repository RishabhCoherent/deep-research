"""Validators for Agent 2 sub-question quality checks."""

from pathlib import Path
from research.core.types import IntentKind, SubQuestionDraft, SubQuestion, QuestionCategory


_COMPOUND_MARKERS = (" and ", " as well as ", " plus ", " & ")

_CHECKLIST_PATH = Path(__file__).parent / "prompts" / "_checklist.md"

_INTENT_MUST_HAVE: dict[IntentKind, list[QuestionCategory]] = {
    IntentKind.MARKET_SIZING: [
        QuestionCategory.SIZE,
        QuestionCategory.SEGMENTATION,
        QuestionCategory.GEOGRAPHY,
        QuestionCategory.OUTLOOK,
    ],
    IntentKind.COMPETITIVE: [
        QuestionCategory.COMPETITIVE,
        QuestionCategory.SEGMENTATION,
        QuestionCategory.GEOGRAPHY,
    ],
    IntentKind.TREND: [
        QuestionCategory.DRIVERS,
        QuestionCategory.CONSTRAINTS,
        QuestionCategory.OUTLOOK,
    ],
    IntentKind.REGULATORY: [
        QuestionCategory.REGULATORY,
        QuestionCategory.CONSTRAINTS,
        QuestionCategory.MACRO,
    ],
    IntentKind.TECHNOLOGY: [
        QuestionCategory.TECHNOLOGY,
        QuestionCategory.COMPETITIVE,
        QuestionCategory.OUTLOOK,
    ],
    IntentKind.GEOGRAPHIC: [
        QuestionCategory.GEOGRAPHY,
        QuestionCategory.DRIVERS,
        QuestionCategory.CONSTRAINTS,
    ],
}

_SHARED_MUST_HAVE: list[QuestionCategory] = [
    QuestionCategory.SIZE,
    QuestionCategory.DRIVERS,
    QuestionCategory.CONSTRAINTS,
]


def _assert_atomic(qs: list) -> None:
    """Reject compound questions (two clauses joined without commas)."""
    for q in qs:
        low = q.text.lower()
        if any(m in low for m in _COMPOUND_MARKERS):
            if low.count(",") == 0:
                raise AssertionError(f"compound question rejected: {q.text!r}")


def assert_checklist_coverage(
    intent: IntentKind,
    questions: list[SubQuestion],
) -> None:
    """Assert that the final question list covers the must-have categories for this intent.

    Raises AssertionError listing which categories are missing.
    """
    covered = {q.category for q in questions}
    must_have = set(_SHARED_MUST_HAVE) | set(_INTENT_MUST_HAVE.get(intent, []))
    missing = must_have - covered
    assert not missing, (
        f"Checklist coverage failed for intent={intent!r}. "
        f"Missing categories: {[c.value for c in missing]}"
    )


def missing_categories(
    intent: IntentKind,
    questions: list[SubQuestionDraft],
) -> list[QuestionCategory]:
    """Return list of must-have categories not yet covered (for retry prompting)."""
    covered = {q.category for q in questions}
    must_have = set(_SHARED_MUST_HAVE) | set(_INTENT_MUST_HAVE.get(intent, []))
    return sorted(must_have - covered, key=lambda c: c.value)
