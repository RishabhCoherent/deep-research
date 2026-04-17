"""LangGraph nodes for the research system."""

from typing import Dict, Any
from research.crews.a1_query_refiner.crew import run_a1
from research.crews.a2_question_generator.crew import run_a2
from research.crews.a3_topic_researcher.crew import run_a3
from research.crews.a4_market_context.crew import run_a4
from research.crews.a5_news_events.crew import run_a5
from research.tools.ask_user import ask_user
from research.core.state import RunState
from research.core.types import IntentKind


async def a1_node(state: RunState, *, config: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 1 - Query Refiner node.
    
    Takes the user's raw query, converts it into four sharp analyst-grade variants,
    scores them, shows the user a ranked multiple-choice, and writes the chosen 
    query + intent back to RunState.
    """
    # Run the Agent 1 crew
    a1_result = await run_a1(state["original_query"])
    
    # Handle user selection (interactive or automatic)
    if config.get("configurable", {}).get("auto_pick") is not None:
        # Automatic selection for non-interactive mode
        idx = int(config["configurable"]["auto_pick"]) - 1  # 1-based
        if 0 <= idx < len(a1_result.variants_sorted):
            chosen = a1_result.variants_sorted[idx].variant.text
        else:
            raise ValueError(f"auto_pick {idx + 1} out of range (1-{len(a1_result.variants_sorted)})")
    else:
        # Interactive mode
        chosen = ask_user.ask_sync(
            question="Which refined query should we research?",
            options=[sv.variant.text for sv in a1_result.variants_sorted],
            hints=[f"{sv.composite:.1f} · {sv.reason}" for sv in a1_result.variants_sorted],
        )
    
    return {
        "intent": a1_result.intent,
        "query_variants": a1_result.variants_sorted,
        "chosen_query": chosen,
    }


async def a2_node(state: RunState, **_) -> Dict[str, Any]:
    """Agent 2 - Question Generator node.

    Fully autonomous (no user interaction). Reads chosen_query + intent from
    RunState, decomposes into 8-15 ranked atomic sub-questions, and writes
    them back to state["sub_questions"].
    """
    a2_result = await run_a2(
        chosen_query=state["chosen_query"],
        intent=state["intent"],
        original_query=state["original_query"],
    )
    return {"sub_questions": a2_result.questions}


async def a3_node(state: RunState, **_) -> Dict[str, Any]:
    """Agent 3 - Topic Researcher node (runs in parallel with A4, A5).

    Fetches sources, extracts numeric claims, writes analyst narrative, and
    pushes high-signal observations to the shared scratchpad.
    Reducer-safe: topic_claims and scratchpad_notes use operator.add.
    """
    a3_result = await run_a3(
        chosen_query=state["chosen_query"],
        intent=state["intent"],
        sub_questions=state["sub_questions"],
    )
    return {
        "topic_claims":     a3_result.claims,
        "topic_narrative":  a3_result.narrative,
        "scratchpad_notes": a3_result.scratchpad_writes,
    }


async def a4_node(state: RunState, **_) -> Dict[str, Any]:
    """Agent 4 - Market Context Researcher node (runs in parallel with A3, A5).

    Maps the value chain, quantifies parent-market pass-through, and writes
    supply-chain observations to scratchpad for Agent 5c to consume.
    Reducer-safe: market_claims and scratchpad_notes use operator.add.
    """
    a4_result = await run_a4(
        chosen_query=state["chosen_query"],
        intent=state["intent"],
        sub_questions=state["sub_questions"],
    )
    return {
        "market_claims":     a4_result.claims,
        "market_narrative":  a4_result.narrative,
        "scratchpad_notes":  a4_result.scratchpad_writes,
    }


async def a5_node(state: RunState, **_) -> Dict[str, Any]:
    """Agent 5 - News & Events Researcher node (runs in parallel with A3, A4).

    5a and 5b run concurrently inside the crew; 5c runs after both,
    reading Agent 4b's value chain from the scratchpad for targeted searches.
    Reducer-safe: news_claims and scratchpad_notes use operator.add.
    """
    a5_result = await run_a5(
        chosen_query=state["chosen_query"],
        intent=state["intent"],
        sub_questions=state["sub_questions"],
    )
    return {
        "news_claims":       a5_result.claims,
        "news_narrative":    a5_result.narrative,
        "scratchpad_notes":  a5_result.scratchpad_writes,
    }
