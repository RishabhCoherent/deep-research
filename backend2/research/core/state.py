"""RunState management and utilities."""

from typing import TypedDict, Annotated
from operator import add
from research.core.types import (
    RunState, IntentKind, ScoredVariant, NumericClaim,
    Conflict, Causation, SubQuestion, Observation, ConsolidatedReport
)


def create_initial_state(run_id: str, original_query: str) -> RunState:
    """Create the initial RunState for a research run."""
    return RunState(
        run_id=run_id,
        original_query=original_query,
        topic_profile=None,                # set by a0_node before a1 runs
        intent=IntentKind.MARKET_SIZING,   # placeholder, set by a1
        query_variants=[],
        chosen_query="",
        sub_questions=[],
        scratchpad_notes=[],
        topic_claims=[],
        topic_narrative="",
        market_claims=[],
        market_narrative="",
        news_claims=[],
        news_narrative="",
        consolidated=None,
        validated_claims=[],
        conflicts=[],
        dimensional_clusters=[],
        causations=[],
        verification=None,
        cost_usd=0.0,
    )


def merge_parallel_claims(
    *claim_lists: list[NumericClaim]
) -> list[NumericClaim]:
    """Merge claim lists from parallel agents using operator.add reducer."""
    result = []
    for claims in claim_lists:
        result.extend(claims)
    return result
