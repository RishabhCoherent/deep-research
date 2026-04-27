"""Validators for Agent 2 sub-question quality checks."""

from pathlib import Path
from research.core.types import IntentKind, SubQuestionDraft, SubQuestion, QuestionCategory
from research.core.topic_profile import TopicProfile


# Two-clause / run-on patterns (second question or clause stitched with "and").
_SECOND_CLAUSE_PATTERNS = (
    " and what ",
    " and how ",
    " and why ",
    " and when ",
    " and which ",
    " and who ",
    " and where ",
    " as well as ",
    " plus ",
    " & ",
)

# If many bare " and " joins appear, likely a stitched brief; require commas for clarity.
# (Allow two, e.g. "supply chain and value chain ... SME and enterprise".)
_MULTI_AND_THRESHOLD = 3


def _bare_and_count(low: str) -> int:
    return low.count(" and ")

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
        QuestionCategory.TECHNOLOGY,
        QuestionCategory.GEOGRAPHY,
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
        QuestionCategory.SIZE,
        QuestionCategory.SUBSTITUTION,
    ],
    IntentKind.GEOGRAPHIC: [
        QuestionCategory.GEOGRAPHY,
        QuestionCategory.DRIVERS,
        QuestionCategory.CONSTRAINTS,
        QuestionCategory.REGULATORY,
        QuestionCategory.VALUE_CHAIN,
        QuestionCategory.COMPETITIVE,
    ],
}

_SHARED_MUST_HAVE: list[QuestionCategory] = [
    QuestionCategory.SIZE,
    QuestionCategory.DRIVERS,
    QuestionCategory.CONSTRAINTS,
    QuestionCategory.MACRO,
]


def _assert_atomic(qs: list) -> None:
    """Reject run-on questions (two clauses or multiple bare 'and' joins without commas)."""
    for q in qs:
        low = q.text.lower()
        if any(p in low for p in _SECOND_CLAUSE_PATTERNS):
            if low.count(",") == 0:
                raise AssertionError(f"compound question rejected: {q.text!r}")
        if _bare_and_count(low) >= _MULTI_AND_THRESHOLD and low.count(",") == 0:
            raise AssertionError(f"compound question rejected: {q.text!r}")


def _checklist_applies(topic_profile: TopicProfile | None) -> bool:
    """The hardcoded _INTENT_MUST_HAVE map encodes market-research expectations
    (SIZE/SEGMENTATION/GEOGRAPHY/OUTLOOK for market_sizing intent, etc.). Those
    requirements only make sense when the topic IS a market-research topic.

    For clinical / policy / social-science / engineering topics, forcing the
    market-research category checklist is wrong — it generates fallback
    questions about market size that pollute the research and have nothing to
    do with the user's actual question.

    Returns True iff the strict market-research checklist should apply:
      - profile is None (legacy callers — preserve old behaviour), OR
      - profile says topic_domain looks like market research.
    Otherwise the question generator's own LLM-driven must-haves are trusted.
    """
    if topic_profile is None:
        return True
    return topic_profile.is_market_research()


def assert_checklist_coverage(
    intent: IntentKind,
    questions: list[SubQuestion],
    *,
    topic_profile: TopicProfile | None = None,
) -> None:
    """Assert that the final question list covers the must-have categories for this intent.

    For non-market-research topics (per topic_profile), the strict market-
    category checklist is skipped — the LLM-driven question generator is
    trusted to produce domain-appropriate questions on its own.

    Raises AssertionError listing which categories are missing (market topics only).
    """
    if not _checklist_applies(topic_profile):
        return
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
    *,
    topic_profile: TopicProfile | None = None,
) -> list[QuestionCategory]:
    """Return list of must-have categories not yet covered (for retry prompting).

    For non-market-research topics, returns [] so no market-research fallback
    questions get injected.
    """
    if not _checklist_applies(topic_profile):
        return []
    covered = {q.category for q in questions}
    must_have = set(_SHARED_MUST_HAVE) | set(_INTENT_MUST_HAVE.get(intent, []))
    return sorted(must_have - covered, key=lambda c: c.value)
