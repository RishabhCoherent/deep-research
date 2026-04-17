"""CrewAI crew orchestration for Agent 3 - Topic Researcher."""

from __future__ import annotations

import json
import structlog

from crewai import Crew, Process

from research.core.types import IntentKind, SubQuestion
from research.core.errors import CrewFailure
from research.tools.research_search import reset_node_counter, get_node_call_count
from research.tools.scratchpad_rw import reset_scratchpad, get_all_observations

from .agents import build_agents
from .tasks import build_tasks
from .schemas import (
    SearchPlan, FetchedSources, ExtractedClaims, TopicSummary, A3Output
)
from .extractor_validators import assert_excerpts_in_passages, assert_citation_complete
from .narrative_validators import assert_word_count, assert_footnote_integrity

log = structlog.get_logger(__name__)


def build_a3_crew():
    planner, fetcher, extractor, summarizer = build_agents()
    t_plan, t_fetch, t_extract, t_summarize = build_tasks(
        planner, fetcher, extractor, summarizer
    )
    return Crew(
        agents=[planner, fetcher, extractor, summarizer],
        tasks=[t_plan, t_fetch, t_extract, t_summarize],
        process=Process.sequential,
        verbose=False,
        memory=False,
    )


async def run_a3(
    *,
    chosen_query: str,
    intent: IntentKind,
    sub_questions: list[SubQuestion],
) -> A3Output:
    """Run Agent 3 - Topic Researcher. Fully autonomous.

    Returns A3Output with validated claims, narrative, and scratchpad observations.
    """
    reset_node_counter()
    reset_scratchpad()

    top_k = sub_questions[:8]
    sub_questions_json = json.dumps([q.model_dump() for q in top_k], default=str)

    crew = build_a3_crew()
    result = await crew.kickoff_async(
        inputs={
            "chosen_query":      chosen_query,
            "intent":            intent.value,
            "sub_questions_json": sub_questions_json,
            "plan_json":         "{}",   # filled by CrewAI context
            "passages_json":     "[]",
            "claims_json":       "[]",
            "passage_map_json":  "{}",
        }
    )

    plan: SearchPlan       = result.tasks_output[0].pydantic
    fetched: FetchedSources = result.tasks_output[1].pydantic
    raw_claims: ExtractedClaims = result.tasks_output[2].pydantic
    summary: TopicSummary   = result.tasks_output[3].pydantic

    if any(x is None for x in [plan, fetched, raw_claims, summary]):
        raise CrewFailure("Agent 3 returned one or more unparseable sub-agent outputs.")

    # ── Post-LLM deterministic validation ──────────────────────────────────
    valid_claims = assert_excerpts_in_passages(raw_claims.claims, fetched.passages)
    valid_claims = assert_citation_complete(valid_claims)

    dropped = len(raw_claims.claims) - len(valid_claims)
    if dropped > 0:
        log.warning("a3_topic_researcher.dropped_claims", dropped=dropped,
                    total=len(raw_claims.claims))

    # Narrative validators — one retry if they fail
    try:
        assert_word_count(summary.narrative)
        assert_footnote_integrity(summary.narrative, summary.footnotes)
    except AssertionError as exc:
        log.warning("a3_topic_researcher.narrative_validation_failed", error=str(exc))
        summary = await _retry_summarizer(
            chosen_query=chosen_query,
            valid_claims=valid_claims,
            fetched=fetched,
            error=str(exc),
        )
        assert_word_count(summary.narrative)
        assert_footnote_integrity(summary.narrative, summary.footnotes)

    tavily_calls = get_node_call_count()
    log.info("a3_topic_researcher.done",
             claims=len(valid_claims),
             tavily_calls=tavily_calls,
             narrative_words=len(summary.narrative.split()))

    return A3Output(
        claims=valid_claims,
        narrative=summary.narrative,
        scratchpad_writes=summary.scratchpad_writes,
    )


async def _retry_summarizer(
    *,
    chosen_query: str,
    valid_claims: list,
    fetched: FetchedSources,
    error: str,
) -> TopicSummary:
    """Single retry of the summarizer with explicit error feedback."""
    from research.api.model_router import sonnet
    from langchain_core.messages import HumanMessage

    passage_map = {
        p.url: {"publisher": p.publisher, "title": p.title,
                "authority_tier": p.authority_tier}
        for p in fetched.passages
    }
    claims_json = json.dumps([c.model_dump() for c in valid_claims], default=str)
    passage_map_json = json.dumps(passage_map, default=str)

    retry_prompt = (
        f"Your previous narrative failed validation: {error}\n"
        f"Rewrite to fix the issue. Target 550 words (min 400, max 800). "
        f"Ensure every [N] in the text has a matching footnote and vice versa.\n\n"
        f"Claims:\n{claims_json}\n\nPassage map:\n{passage_map_json}\n\n"
        f"Chosen query: {chosen_query}\n\n"
        f"Return ONLY valid JSON matching TopicSummary."
    )

    llm = sonnet()
    response = llm.invoke([HumanMessage(content=retry_prompt)])
    try:
        return TopicSummary.model_validate_json(response.content)
    except Exception as exc:
        raise CrewFailure(f"Agent 3 summarizer retry also failed: {exc}") from exc
