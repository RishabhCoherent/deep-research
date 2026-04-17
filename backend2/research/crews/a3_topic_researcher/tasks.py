"""CrewAI tasks for Agent 3 - Topic Researcher."""

import json
from crewai import Task
from .schemas import SearchPlan, FetchedSources, ExtractedClaims, TopicSummary


def build_tasks(planner, fetcher, extractor, summarizer):
    """Build four sequential tasks for Agent 3."""

    t_plan = Task(
        description=(
            "Build a search plan for the top sub-questions. "
            "intent={intent}, chosen_query={chosen_query}, "
            "sub_questions_json={sub_questions_json}"
        ),
        expected_output="JSON matching SearchPlan (1-8 plans, total queries ≤ 12).",
        agent=planner,
        output_pydantic=SearchPlan,
    )

    t_fetch = Task(
        description=(
            "Execute the search plan, fetch passages, deduplicate, keep best 12. "
            "chosen_query={chosen_query}, plan_json={plan_json}"
        ),
        expected_output="JSON matching FetchedSources (≤ 12 unique passages).",
        agent=fetcher,
        context=[t_plan],
        output_pydantic=FetchedSources,
    )

    t_extract = Task(
        description=(
            "Extract NumericClaims from the fetched passages. "
            "Copy raw_excerpt verbatim from source text. "
            "chosen_query={chosen_query}, passages_json={passages_json}"
        ),
        expected_output="JSON matching ExtractedClaims (all raw_excerpts verbatim).",
        agent=extractor,
        context=[t_fetch],
        output_pydantic=ExtractedClaims,
    )

    t_summarize = Task(
        description=(
            "Write a 400-800 word analyst narrative using the validated claims. "
            "Push 3-7 observations to scratchpad section='topic'. "
            "chosen_query={chosen_query}, "
            "claims_json={claims_json}, passage_map_json={passage_map_json}"
        ),
        expected_output="JSON matching TopicSummary (narrative + footnotes + scratchpad_writes).",
        agent=summarizer,
        context=[t_extract],
        output_pydantic=TopicSummary,
    )

    return t_plan, t_fetch, t_extract, t_summarize
