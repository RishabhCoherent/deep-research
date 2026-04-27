"""Smoke tests for structured LLM output — all 8 agents.

Each test calls the real LLM with minimal inputs and asserts that
tasks_output[N].pydantic is not None and key fields are valid types.
Tests are independent: A6/A7/A8 use synthetic data so they don't require
A1-A5 to have run first.

Run:
    cd backend2
    pytest tests/integration/test_structured_output_smoke.py -v -s

Skip individual agents:
    pytest tests/integration/test_structured_output_smoke.py -v -s -k "not a3 and not a4"
"""

from __future__ import annotations

import asyncio
import os

import pytest
from dotenv import load_dotenv

load_dotenv()

_HAS_KEY = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"))
pytestmark = pytest.mark.skipif(
    not _HAS_KEY, reason="No LLM API key (ANTHROPIC_API_KEY or OPENAI_API_KEY) configured"
)

from research.core.types import (
    AuthorityTier,
    Causation,
    Citation,
    ConsolidatedReport,
    Footnote,
    IntentKind,
    NumericClaim,
    Observation,
    QuestionCategory,
    SubQuestion,
    Theme,
)


# ── Shared fixtures ────────────────────────────────────────────────────────────

TOPIC = "global lithium-ion battery market"
QUERY = "Global lithium-ion battery market size, growth drivers, and competitive landscape 2024"
INTENT = IntentKind.MARKET_SIZING


def _citation(url: str = "https://energy.gov/battery-report") -> Citation:
    return Citation(
        url=url,
        title="Battery Market Report 2024",
        publisher="US Dept of Energy",
        published="2024-01-15",
        authority_tier=AuthorityTier.GOVERNMENT,
    )


def _claim(metric: str, value: float, unit: str, as_of: str = "2024") -> NumericClaim:
    return NumericClaim(
        metric=metric,
        value=value,
        unit=unit,
        as_of=as_of,
        scope="global",
        raw_excerpt=f"The {metric} was {value} {unit} in {as_of} according to DOE.",
        citation=_citation(),
    )


FAKE_QUESTIONS = [
    SubQuestion(
        text="What is the current global market size of lithium-ion batteries in USD?",
        category=QuestionCategory.SIZE,
        source="smoke_test",
        info_value=9.0, answerability=9.0, composite=9.0,
        reason="Core sizing question",
    ),
    SubQuestion(
        text="What are the primary demand drivers for lithium-ion battery growth?",
        category=QuestionCategory.DRIVERS,
        source="smoke_test",
        info_value=8.5, answerability=8.5, composite=8.5,
        reason="Demand driver analysis",
    ),
    SubQuestion(
        text="Which companies hold the largest share in the lithium-ion battery market?",
        category=QuestionCategory.COMPETITIVE,
        source="smoke_test",
        info_value=8.0, answerability=8.0, composite=8.0,
        reason="Competitive landscape",
    ),
]

FAKE_CLAIMS = [
    _claim("global lithium-ion battery market size", 150.0, "USD billion", "2024"),
    _claim("global lithium-ion battery market size", 128.0, "USD billion", "2023"),
    _claim("CAGR 2024-2030", 15.2, "%"),
    _claim("EV segment share of battery demand", 68.0, "%"),
]

FAKE_OBSERVATION = Observation(
    section="topic",
    key="market_growth_rate",
    value="Battery market growing at 15% CAGR driven by EV adoption and grid storage",
    written_by="smoke_test",
)

FAKE_CONSOLIDATED = ConsolidatedReport(
    claims=FAKE_CLAIMS,
    themes=[
        Theme(
            name="Market Size & Growth",
            summary="Rapid growth from $128bn (2023) to $150bn (2024), 15.2% CAGR projected to 2030.",
            claims=FAKE_CLAIMS[:2],
            observations=[FAKE_OBSERVATION],
        )
    ],
    narrative=(
        "The global lithium-ion battery market reached $150 billion in 2024, up from "
        "$128 billion in 2023 — a year-on-year gain of 17% [1]. The EV segment accounts "
        "for 68% of total demand [1]. Analysts project a 15.2% CAGR through 2030 [1].\n\n"
        "Key drivers include accelerating EV adoption, grid-scale energy storage buildout, "
        "and declining cell costs. CATL and LG Energy Solution remain the dominant suppliers.\n\n"
        "## Footnotes\n"
        "[1] US Dept of Energy — https://energy.gov/battery-report"
    ),
    footnotes=[Footnote(n=1, citation=_citation())],
)


# ── Pytest fixture: reset global scratchpad between tests ─────────────────────

@pytest.fixture(autouse=True)
def _reset_scratchpad():
    """Reset global scratchpad state before each test to avoid cross-test contamination."""
    try:
        from research.tools.scratchpad_rw import reset_scratchpad
        from research.tools.research_search import reset_node_counter
        reset_scratchpad()
        reset_node_counter()
    except Exception:
        pass
    yield


# ── Helper ─────────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.run(coro)


def _banner(label: str, **kv) -> None:
    pairs = "  ".join(f"{k}={v}" for k, v in kv.items())
    print(f"\n  {label} ✓  {pairs}")


# ── A1 ─────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_a1_structured_output():
    """A1: intent classification + 4 scored query variants parse correctly."""
    from research.crews.a1_query_refiner.crew import run_a1
    from research.core.types import AngleKind

    result = _run(run_a1(TOPIC))

    assert result.intent in IntentKind, f"Invalid intent: {result.intent}"
    assert len(result.variants_sorted) == 4, (
        f"Expected 4 variants, got {len(result.variants_sorted)}"
    )
    angles = {sv.variant.angle for sv in result.variants_sorted}
    assert angles == {
        AngleKind.SIZE_SEGMENTATION,
        AngleKind.DRIVERS_CONSTRAINTS,
        AngleKind.COMPETITIVE_SHARE,
        AngleKind.OUTLOOK_SCENARIOS,
    }, f"Missing angles: {angles}"
    for sv in result.variants_sorted:
        assert 0 <= sv.composite <= 10, f"composite out of range: {sv.composite}"
        assert sv.variant.text, "Variant text must be non-empty"
        assert len(sv.variant.text.split()) <= 35, f"Variant too long: {sv.variant.text}"

    composites = [sv.composite for sv in result.variants_sorted]
    assert composites == sorted(composites, reverse=True), "Variants must be sorted desc"

    _banner("A1", intent=result.intent, variants=len(result.variants_sorted))


# ── A2 ─────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_a2_structured_output():
    """A2: decomposes query into 8-15 typed, atomic sub-questions."""
    from research.crews.a2_question_generator.crew import run_a2

    result = _run(run_a2(
        chosen_query=QUERY,
        intent=INTENT,
        original_query=TOPIC,
    ))

    assert 8 <= len(result.questions) <= 15, (
        f"Expected 8-15 questions, got {len(result.questions)}"
    )
    categories = {q.category for q in result.questions}
    assert len(categories) >= 4, f"Expected ≥4 distinct categories, got {categories}"
    for q in result.questions:
        assert q.category in QuestionCategory, f"Invalid category: {q.category}"
        assert 0 <= q.composite <= 10, f"composite out of range: {q.composite}"
        assert q.text.strip().endswith("?"), f"Question must end with '?': {q.text!r}"
        assert len(q.text.split()) <= 40, f"Question too long: {q.text!r}"

    _banner("A2", questions=len(result.questions),
            categories=sorted(c.value for c in categories))


# ── A3 ─────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_a3_structured_output():
    """A3: returns a claims list and non-empty narrative (0 claims OK if search fails)."""
    from research.crews.a3_topic_researcher.crew import run_a3

    result = _run(run_a3(
        chosen_query=QUERY,
        intent=INTENT,
        sub_questions=FAKE_QUESTIONS,
    ))

    assert isinstance(result.claims, list), "claims must be a list"
    assert isinstance(result.narrative, str), "narrative must be a string"
    assert len(result.narrative) > 50, (
        f"narrative too short ({len(result.narrative)} chars)"
    )
    assert isinstance(result.scratchpad_writes, list), "scratchpad_writes must be a list"
    for claim in result.claims:
        assert claim.metric, "claim.metric must be non-empty"
        assert claim.citation.url, "claim.citation.url must be non-empty"
        assert isinstance(claim.value, (int, float, str)), (
            f"claim.value must be numeric or str, got {type(claim.value)}"
        )

    _banner("A3", claims=len(result.claims),
            narrative_words=len(result.narrative.split()),
            scratchpad=len(result.scratchpad_writes))


# ── A4 ─────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_a4_structured_output():
    """A4: returns market claims and narrative from value-chain analysis."""
    from research.crews.a4_market_context.crew import run_a4

    result = _run(run_a4(
        chosen_query=QUERY,
        intent=INTENT,
        sub_questions=FAKE_QUESTIONS,
    ))

    assert isinstance(result.claims, list), "claims must be a list"
    assert isinstance(result.narrative, str), "narrative must be a string"
    assert len(result.narrative) > 50, (
        f"narrative too short ({len(result.narrative)} chars)"
    )
    for claim in result.claims:
        assert claim.metric, "claim.metric must be non-empty"
        assert claim.citation.url, "claim.citation.url must be non-empty"

    _banner("A4", claims=len(result.claims),
            narrative_words=len(result.narrative.split()))


# ── A5 ─────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_a5_structured_output():
    """A5: returns news/event claims and event narrative (accepts empty claims)."""
    from research.crews.a5_news_events.crew import run_a5

    result = _run(run_a5(
        chosen_query=QUERY,
        intent=INTENT,
        sub_questions=FAKE_QUESTIONS,
    ))

    assert isinstance(result.claims, list), "claims must be a list"
    assert isinstance(result.narrative, str), "narrative must be a string"
    assert isinstance(result.scratchpad_writes, list), "scratchpad_writes must be a list"
    for claim in result.claims:
        assert claim.metric, "claim.metric must be non-empty"
        assert claim.citation.url, "claim.citation.url must be non-empty"

    _banner("A5", claims=len(result.claims),
            narrative_words=len(result.narrative.split()),
            scratchpad=len(result.scratchpad_writes))


# ── A6 ─────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_a6_structured_output():
    """A6: consolidates synthetic claims into themed narrative (no web calls)."""
    from research.crews.a6_consolidator.crew import run_a6

    result = _run(run_a6(
        chosen_query=QUERY,
        intent=INTENT,
        topic_claims=FAKE_CLAIMS,
        market_claims=FAKE_CLAIMS[:2],
        news_claims=[],
        topic_narrative="Battery market at $150bn growing 15% CAGR.",
        market_narrative="Parent EV market exceeds $500bn globally.",
        news_narrative="CATL and LG announce new gigafactory partnerships.",
        scratchpad_notes=[FAKE_OBSERVATION],
    ))

    assert result.consolidated is not None, "consolidated must not be None"
    assert isinstance(result.consolidated.claims, list), "consolidated.claims must be a list"
    assert isinstance(result.consolidated.themes, list), "consolidated.themes must be a list"
    assert isinstance(result.consolidated.narrative, str), "narrative must be a string"
    assert len(result.consolidated.narrative) > 100, (
        f"narrative too short ({len(result.consolidated.narrative)} chars)"
    )
    assert len(result.consolidated.claims) >= 1, "Must retain ≥1 claim after normalisation"

    _banner("A6",
            claims=len(result.consolidated.claims),
            themes=len(result.consolidated.themes),
            narrative_words=len(result.consolidated.narrative.split()))


# ── A7 ─────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_a7_structured_output():
    """A7: validates synthetic claims; deterministic authority ranking always fires."""
    from research.crews.a7_validator.crew import run_a7

    result = _run(run_a7(consolidated=FAKE_CONSOLIDATED))

    assert isinstance(result.validated_claims, list), "validated_claims must be a list"
    assert isinstance(result.conflicts, list), "conflicts must be a list"
    assert len(result.validated_claims) >= 1, (
        f"Expected ≥1 validated claim after dedup, got 0"
    )
    for claim in result.validated_claims:
        assert claim.metric, "validated claim.metric must be non-empty"
        assert claim.citation.url, "validated claim must have a citation URL"

    _banner("A7",
            validated=len(result.validated_claims),
            conflicts=len(result.conflicts))


# ── A8 ─────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_a8_structured_output():
    """A8: detects year-on-year delta in FAKE_CLAIMS; causations list always returned."""
    from research.crews.a8_causation.crew import run_a8

    result = _run(run_a8(
        validated_claims=FAKE_CLAIMS,
        news_narrative="CATL announced a 20 GWh capacity expansion in Q1 2024.",
        scratchpad_notes=[FAKE_OBSERVATION],
        chosen_query=QUERY,
    ))

    assert isinstance(result.causations, list), "causations must be a list"
    for causation in result.causations:
        assert causation.metric, "causation.metric must be non-empty"
        assert causation.confidence in ("high", "medium", "low"), (
            f"Invalid confidence: {causation.confidence}"
        )
        assert isinstance(causation.delta_pct, float), "delta_pct must be a float"
        for driver in causation.drivers:
            assert len(driver.evidence) >= 2, (
                f"Driver '{driver.name}' has {len(driver.evidence)} citations — need ≥2"
            )
            domains = {c.url.split("/")[2] for c in driver.evidence if "://" in c.url}
            assert len(domains) >= 2, (
                f"Driver '{driver.name}' citations must span ≥2 domains, got {domains}"
            )

    _banner("A8", causations=len(result.causations))
