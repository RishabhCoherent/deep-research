"""Live integration tests for Agent 1 - Query Refiner.

Runs the actual A1 crew against the real LLM (Haiku) on a variety
of topics to verify intent classification and query generation quality.

Usage:
    cd backend2
    python -m pytest tests/integration/test_a1_live.py -v -s
"""

import asyncio
import pytest
from dotenv import load_dotenv

load_dotenv()

from research.crews.a1_query_refiner.crew import run_a1
from research.core.types import IntentKind, AngleKind


TEST_QUERIES = [
    {
        "query": "Tell me about the EV battery market",
        "expected_intent": IntentKind.MARKET_SIZING,
        "description": "Classic market-sizing query",
    },
    {
        "query": "How does Tesla compare to BYD in global EV sales?",
        "expected_intent": IntentKind.COMPETITIVE,
        "description": "Competitive landscape query",
    },
    {
        "query": "Impact of US tariffs on Chinese EV imports",
        "expected_intent": IntentKind.REGULATORY,
        "description": "Regulatory/policy query",
    },
    {
        "query": "What were the main causes of World War 1?",
        "expected_intent": IntentKind.GENERAL,
        "description": "Non-market / general knowledge query (new fallback)",
    },
    {
        "query": "AI adoption trends in Southeast Asia vs Europe",
        "expected_intent": IntentKind.GEOGRAPHIC,
        "description": "Geographic comparison query",
    },
]


def _print_result(query: str, result) -> None:
    """Pretty-print the A1 result to stdout."""
    print(f"\n{'='*70}")
    print(f"  INPUT : {query}")
    print(f"  INTENT: {result.intent}  (expected: varies)")
    print(f"{'='*70}")
    for i, sv in enumerate(result.variants_sorted, 1):
        print(
            f"  #{i}  [{sv.variant.angle:<22}]  score={sv.composite:.1f}"
            f"  ->  {sv.variant.text}"
        )
        print(f"       reason: {sv.reason}")
    print()


@pytest.mark.parametrize("case", TEST_QUERIES, ids=[c["description"] for c in TEST_QUERIES])
def test_a1_live(case):
    """Run A1 on a real query and assert structural correctness + intent."""
    result = asyncio.run(run_a1(case["query"]))

    _print_result(case["query"], result)

    # --- Structural assertions (always required) ---
    assert result.intent in IntentKind, f"intent '{result.intent}' not a valid IntentKind"
    assert len(result.variants_sorted) == 4, "must return exactly 4 variants"

    angles = {sv.variant.angle for sv in result.variants_sorted}
    assert angles == {
        AngleKind.SIZE_SEGMENTATION,
        AngleKind.DRIVERS_CONSTRAINTS,
        AngleKind.COMPETITIVE_SHARE,
        AngleKind.OUTLOOK_SCENARIOS,
    }, f"missing angles: {angles}"

    composites = [sv.composite for sv in result.variants_sorted]
    assert composites == sorted(composites, reverse=True), "variants must be sorted desc by composite"

    for sv in result.variants_sorted:
        assert len(sv.variant.text.split()) <= 35, f"variant too long: {sv.variant.text}"
        assert 0 <= sv.composite <= 10

    # --- Intent assertion ---
    assert result.intent == case["expected_intent"], (
        f"Expected intent '{case['expected_intent']}' but got '{result.intent}'"
    )
