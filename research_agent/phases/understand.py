"""
Phase 1 — UNDERSTAND: Decompose the topic into a structured research plan.

Single LLM call (cheap model) that produces:
- Report type detection (Porter's, PEST, Market Overview, etc.)
- Ordered section headings
- 15-20 specific research questions with pre-generated search queries
"""

from __future__ import annotations

import logging
import time

from config import get_llm
from research_agent.models import ResearchPlan, ResearchQuestion, ResearchResult
from research_agent.prompts import PHASE1_PLAN_PROMPT, get_question_rules
from research_agent.cost import track
from research_agent.utils import extract_json, get_content

logger = logging.getLogger(__name__)


async def run(
    topic: str,
    progress_callback=None,
    section_names: list[str] | None = None,
    report_type: str = "",
) -> tuple[ResearchPlan, ResearchResult]:
    """
    Decompose topic into a structured research plan.

    Returns:
        (plan, layer_result) — the plan for Phase 2, and a ResearchResult
        for frontend compatibility (layer=0).
    """
    start = time.time()

    def notify(status: str, msg: str):
        if progress_callback:
            progress_callback(0, status, msg)
        logger.info(f"[Phase 1] {status}: {msg}")

    notify("planning", "Analyzing topic and creating research plan...")

    topic_question_rules = get_question_rules(report_type)

    llm = get_llm("planner")
    messages = [
        {"role": "system", "content": "You are a research director. Return ONLY valid JSON."},
        {"role": "user", "content": PHASE1_PLAN_PROMPT.format(
            topic=topic, topic_question_rules=topic_question_rules
        )},
    ]

    try:
        response = await llm.ainvoke(messages)
        track("P1 plan", response)
        result = extract_json(get_content(response).strip())
    except Exception as e:
        logger.error(f"[Phase 1] Planning failed: {e}")
        result = None

    if not isinstance(result, dict):
        logger.warning("[Phase 1] Failed to parse plan, using fallback")
        result = {
            "report_type": "Market Overview",
            "sections": ["Market Size & Growth", "Competitive Landscape",
                         "Key Trends", "Challenges & Risks", "Outlook"],
            "questions": [],
        }

    # Parse the plan — use shared section names if provided for cross-layer consistency
    report_type = result.get("report_type", "Market Overview")
    llm_sections = result.get("sections", [])
    sections = section_names if section_names else llm_sections
    raw_questions = result.get("questions", [])

    # Build a mapping from LLM section names → shared section names
    def _norm(s: str) -> str:
        return s.lower().replace(" ", "").replace("-", "").replace("_", "").replace("&", "")

    section_remap: dict[str, str] = {}
    if section_names and llm_sections:
        # Pass 1: exact and substring matching
        for llm_s in llm_sections:
            n = _norm(llm_s)
            for shared_s in section_names:
                sn = _norm(shared_s)
                if sn == n or n in sn or sn in n:
                    section_remap[llm_s] = shared_s
                    break

        # Pass 2: word-overlap matching for unmatched sections
        unmatched_llm = [s for s in llm_sections if s not in section_remap]
        unmatched_shared = [s for s in section_names if s not in section_remap.values()]
        if unmatched_llm and unmatched_shared:
            for llm_s in unmatched_llm:
                llm_words_set = set(llm_s.lower().split())
                best_score = 0
                best_shared = None
                for shared_s in section_names:
                    shared_words_set = set(shared_s.lower().split())
                    overlap = len(llm_words_set & shared_words_set)
                    if overlap > best_score:
                        best_score = overlap
                        best_shared = shared_s
                if best_shared and best_score > 0:
                    section_remap[llm_s] = best_shared

    # Build ResearchQuestion objects
    questions = []
    for i, q in enumerate(raw_questions):
        if not isinstance(q, dict):
            continue
        q_section = q.get("section", sections[0] if sections else "General")
        # Remap question section to shared section name if needed
        q_section = section_remap.get(q_section, q_section)
        # If section STILL doesn't match any shared section, distribute round-robin
        if section_names and q_section not in sections:
            q_section = sections[i % len(sections)]
        questions.append(ResearchQuestion(
            id=q.get("id", f"q{i:02d}"),
            section=q_section,
            question=q.get("question", ""),
            data_type=q.get("data_type", "general"),
            priority=int(q.get("priority", 2)),
            search_queries=q.get("search_queries", []),
        ))

    plan = ResearchPlan(
        topic=topic,
        report_type=report_type,
        sections=sections,
        questions=questions,
    )

    elapsed = time.time() - start

    # Summary for frontend content
    content_lines = [
        f"## Research Plan: {report_type}",
        f"**Topic:** {topic}",
        "",
        f"### Sections ({len(sections)})",
    ]
    for i, s in enumerate(sections, 1):
        section_qs = [q for q in questions if q.section == s]
        content_lines.append(f"{i}. **{s}** — {len(section_qs)} research questions")

    content_lines.extend([
        "",
        f"### Research Questions ({len(questions)})",
        f"- Priority 1 (critical): {len([q for q in questions if q.priority == 1])}",
        f"- Priority 2 (important): {len([q for q in questions if q.priority == 2])}",
        f"- Priority 3 (nice-to-have): {len([q for q in questions if q.priority == 3])}",
        "",
        f"### Total search queries: {sum(len(q.search_queries) for q in questions)}",
    ])

    notify("done", f"Plan ready: {report_type}, {len(sections)} sections, "
                    f"{len(questions)} questions")

    layer_result = ResearchResult(
        layer=0,
        topic=topic,
        content="\n".join(content_lines),
        sources=[],
        metadata={
            "method": "research_plan",
            "report_type": report_type,
            "sections": sections,
            "question_count": len(questions),
            "search_query_count": sum(len(q.search_queries) for q in questions),
        },
        elapsed_seconds=elapsed,
    )

    return plan, layer_result
