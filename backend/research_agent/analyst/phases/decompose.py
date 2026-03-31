"""
Phase 1: DECOMPOSE — Break the topic into structured sub-questions.

This is where the analyst thinks BEFORE researching.
Single LLM call, ~15 seconds.
"""

import json
import logging

from config import get_llm, set_model_tier
from research_agent.analyst.models import AnalysisFramework, SubQuestion
from research_agent.analyst.prompts import DECOMPOSE_PROMPT
from research_agent.cost import track
from research_agent.utils import get_content, extract_json, date_vars

logger = logging.getLogger(__name__)


async def decompose(topic: str, brief: str = "", notify=None) -> AnalysisFramework:
    """Decompose a topic into a structured research framework.

    Returns an AnalysisFramework with typed sub-questions, each having
    its own research strategy, priority, and search queries.
    """
    if notify:
        notify("decompose", "Breaking down the research problem...")

    brief_section = f"CLIENT BRIEF:\n{brief}" if brief else ""

    set_model_tier("standard")
    llm = get_llm("planner")

    messages = [
        {"role": "system", "content": "You output only valid JSON. No explanation, no markdown fences."},
        {"role": "user", "content": DECOMPOSE_PROMPT.format(
            topic=topic,
            brief_section=brief_section,
            **date_vars(),
        )},
    ]

    response = await llm.ainvoke(messages)
    track("analyst decompose", response)
    raw = get_content(response)
    data = extract_json(raw)

    if not data or "sub_questions" not in data:
        logger.error(f"[Analyst] Decompose failed to parse: {raw[:200]}")
        # Return a minimal framework so the pipeline doesn't crash
        return _fallback_framework(topic)

    # Parse analytical framework (designed before sub-questions)
    af = data.get("analytical_framework", {})
    if not isinstance(af, dict):
        af = {}

    framework = AnalysisFramework(
        core_question=data.get("core_question", topic),
        assumptions=data.get("assumptions", []),
        scope_in=data.get("scope_in", []),
        scope_out=data.get("scope_out", []),
        report_sections=data.get("report_sections", []),
        comparison_dimensions=af.get("comparison_dimensions", []),
        key_tables=af.get("key_tables", []),
        market_segmentation_hypothesis=af.get("market_segmentation_hypothesis", ""),
        contrarian_hypotheses=af.get("contrarian_hypotheses", []),
    )

    for sq_data in data["sub_questions"]:
        if not isinstance(sq_data, dict):
            continue
        sq = SubQuestion(
            id=sq_data.get("id", f"sq_{len(framework.sub_questions)+1:02d}"),
            question=sq_data.get("question", ""),
            answer_type=sq_data.get("answer_type", "general"),
            research_strategy=sq_data.get("research_strategy", "data_hunt"),
            priority=sq_data.get("priority", 2),
            depends_on=sq_data.get("depends_on", []),
            search_queries=sq_data.get("search_queries", []),
        )
        if sq.question:
            framework.sub_questions.append(sq)

    # Ensure we have at least some sub-questions
    if len(framework.sub_questions) < 3:
        logger.warning("[Analyst] Too few sub-questions, adding fallback queries")
        framework = _enrich_framework(framework, topic)

    logger.info(
        f"[Analyst] Decomposed into {len(framework.sub_questions)} sub-questions "
        f"({sum(1 for sq in framework.sub_questions if sq.priority == 1)} P1, "
        f"{sum(1 for sq in framework.sub_questions if sq.priority == 2)} P2, "
        f"{sum(1 for sq in framework.sub_questions if sq.priority == 3)} P3)"
    )

    if notify:
        notify("decompose", f"Identified {len(framework.sub_questions)} research questions")

    return framework


def _fallback_framework(topic: str) -> AnalysisFramework:
    """Minimal framework when LLM parsing fails."""
    return AnalysisFramework(
        core_question=topic,
        sub_questions=[
            SubQuestion(id="sq_01", question=f"What is the overall market size and growth for {topic}?",
                       answer_type="numeric", research_strategy="data_hunt", priority=1,
                       search_queries=[f"{topic} market size 2025 2026", f"{topic} growth rate CAGR"]),
            SubQuestion(id="sq_02", question=f"Who are the key players and competitors in {topic}?",
                       answer_type="list", research_strategy="company_deep_dive", priority=1,
                       search_queries=[f"{topic} major companies market share", f"{topic} competitive landscape leaders"]),
            SubQuestion(id="sq_03", question=f"What are the main trends and drivers for {topic}?",
                       answer_type="trend", research_strategy="expert_scan", priority=2,
                       search_queries=[f"{topic} trends outlook 2025 2026", f"{topic} key drivers challenges"]),
            SubQuestion(id="sq_04", question=f"What is the regulatory environment for {topic}?",
                       answer_type="list", research_strategy="regulatory_lookup", priority=2,
                       search_queries=[f"{topic} regulations policy government 2025", f"{topic} compliance requirements"]),
            SubQuestion(id="sq_05", question=f"What are the risks and challenges for {topic}?",
                       answer_type="list", research_strategy="expert_scan", priority=2,
                       search_queries=[f"{topic} risks challenges barriers", f"{topic} disruption threats"]),
        ],
        report_sections=["Executive Summary", "Market Overview", "Key Players", "Trends & Drivers",
                         "Regulatory Environment", "Risks & Challenges", "Recommendations"],
    )


def _enrich_framework(framework: AnalysisFramework, topic: str) -> AnalysisFramework:
    """Add basic sub-questions if LLM generated too few."""
    existing_ids = {sq.id for sq in framework.sub_questions}
    idx = len(framework.sub_questions) + 1

    basics = [
        ("What is the market size?", "numeric", "data_hunt", 1, [f"{topic} market size 2025 billion"]),
        ("Who are the key players?", "list", "company_deep_dive", 1, [f"{topic} major companies market share"]),
        ("What are the growth trends?", "trend", "expert_scan", 2, [f"{topic} growth trends outlook"]),
    ]

    for question, atype, strategy, priority, queries in basics:
        sq_id = f"sq_{idx:02d}"
        if sq_id not in existing_ids:
            framework.sub_questions.append(SubQuestion(
                id=sq_id, question=question, answer_type=atype,
                research_strategy=strategy, priority=priority,
                search_queries=queries,
            ))
            idx += 1

    return framework
