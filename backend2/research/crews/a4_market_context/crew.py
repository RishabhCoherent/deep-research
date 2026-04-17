"""CrewAI crew orchestration for Agent 4 - Market Context Researcher."""

from __future__ import annotations

import json
import structlog

from crewai import Crew, Process

from research.core.types import IntentKind, SubQuestion
from research.core.errors import CrewFailure
from research.tools.research_search import reset_node_counter, get_node_call_count
from research.tools.scratchpad_rw import get_all_observations

from .agents import build_agents
from .tasks import build_tasks
from .schemas import ParentMarketResult, ValueChainMap, ImpactAnalysis, A4Output
from .validators import (
    assert_impact_evidence,
    assert_claim_citations,
    assert_narrative_word_count,
)

log = structlog.get_logger(__name__)


def build_a4_crew():
    identifier, mapper, analyst = build_agents()
    t_identify, t_map, t_analyse = build_tasks(identifier, mapper, analyst)
    return Crew(
        agents=[identifier, mapper, analyst],
        tasks=[t_identify, t_map, t_analyse],
        process=Process.sequential,
        verbose=False,
        memory=False,
    )


async def run_a4(
    *,
    chosen_query: str,
    intent: IntentKind,
    sub_questions: list[SubQuestion],
) -> A4Output:
    """Run Agent 4 - Market Context Researcher. Fully autonomous.

    Returns A4Output with validated claims, narrative, and scratchpad observations.
    """
    reset_node_counter()

    top_k = sub_questions[:8]
    sub_questions_json = json.dumps([q.model_dump() for q in top_k], default=str)

    crew = build_a4_crew()
    result = await crew.kickoff_async(
        inputs={
            "chosen_query":       chosen_query,
            "intent":             intent.value,
            "sub_questions_json": sub_questions_json,
            "parent_market_json": "{}",
            "value_chain_json":   "{}",
        }
    )

    parent: ParentMarketResult = result.tasks_output[0].pydantic
    chain: ValueChainMap       = result.tasks_output[1].pydantic
    analysis: ImpactAnalysis   = result.tasks_output[2].pydantic

    if any(x is None for x in [parent, chain, analysis]):
        raise CrewFailure("Agent 4 returned one or more unparseable sub-agent outputs.")

    # ── Post-LLM deterministic validation ─────────────────────────────────
    valid_impacts = assert_impact_evidence(analysis.impacts)
    valid_claims  = assert_claim_citations(analysis.claims)

    dropped_impacts = len(analysis.impacts) - len(valid_impacts)
    dropped_claims  = len(analysis.claims) - len(valid_claims)
    if dropped_impacts or dropped_claims:
        log.warning("a4_market_context.dropped",
                    dropped_impacts=dropped_impacts,
                    dropped_claims=dropped_claims)

    try:
        assert_narrative_word_count(analysis.narrative)
    except AssertionError as exc:
        log.warning("a4_market_context.narrative_word_count_failed", error=str(exc))

    log.info("a4_market_context.done",
             claims=len(valid_claims),
             impacts=len(valid_impacts),
             tavily_calls=get_node_call_count(),
             narrative_words=len(analysis.narrative.split()))

    return A4Output(
        claims=valid_claims,
        narrative=analysis.narrative,
        scratchpad_writes=chain.scratchpad_writes,
    )
