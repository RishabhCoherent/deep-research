"""
Phase 4 — WRITE: Produce the final report from structured knowledge.

The LLM receives:
- Section structure from Phase 1
- Verified facts grouped by section from Phase 2+3
- Analytical insights and contrarian risks from Phase 3

It writes ONLY from provided data — no training data filler.
A review pass checks for fabricated claims and quality.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

from config import get_llm
from research_agent.models import ResearchPlan, KnowledgeBase, ResearchResult, Source
from research_agent.prompts import PHASE4_WRITE_PROMPT, PHASE4_REVIEW_PROMPT, get_quality_rules
from research_agent.cost import track
from research_agent.utils import extract_json, get_content, strip_preamble

logger = logging.getLogger(__name__)


async def run(
    plan: ResearchPlan,
    kb: KnowledgeBase,
    insights: list[str],
    contrarian_risks: list[str],
    section_impacts: list[dict],
    progress_callback=None,
) -> ResearchResult:
    """
    Write the final report from structured knowledge.

    Returns:
        ResearchResult (layer=3) with the polished report as content.
    """
    start = time.time()

    def notify(status: str, msg: str):
        if progress_callback:
            progress_callback(3, status, msg)
        logger.info(f"[Phase 4] {status}: {msg}")

    notify("start", "Writing final report from verified knowledge...")

    llm_writer = get_llm("writer")
    llm_reviewer = get_llm("reviewer")

    # ── Build section data for the writer ─────────────────────────────────
    section_data_parts = []
    for section in plan.sections:
        facts_text = kb.format_for_section(section, max_facts=25)
        section_data_parts.append(f"### {section}\n{facts_text}")
    section_data = "\n\n".join(section_data_parts)

    insights_text = "\n".join(f"- {i}" for i in insights) if insights else "No insights generated."
    risks_text = "\n".join(f"- {r}" for r in contrarian_risks) if contrarian_risks else "No contrarian risks identified."

    # ── Write the report ──────────────────────────────────────────────────
    notify("drafted", "Generating first draft...")

    try:
        write_messages = [
            {"role": "system", "content": (
                "You are a senior market research writer. Write publication-ready reports. "
                "Use ONLY the data provided — never add facts from your training data."
            )},
            {"role": "user", "content": PHASE4_WRITE_PROMPT.format(
                topic=plan.topic,
                report_type=plan.report_type,
                section_data=section_data[:14000],
                insights=insights_text,
                contrarian_risks=risks_text,
                current_year=datetime.now().year,
                last_year=datetime.now().year - 1,
                topic_rules=get_quality_rules(plan.report_type),
            )},
        ]
        response = await llm_writer.ainvoke(write_messages)
        track("P4 write", response)
        draft = get_content(response).strip()
    except Exception as e:
        logger.error(f"[Phase 4] Writing failed: {e}")
        draft = _fallback_report(plan, kb)

    draft = strip_preamble(draft)

    word_count = len(draft.split())
    notify("drafted", f"First draft: {word_count} words")

    # ── Review the draft ──────────────────────────────────────────────────
    notify("evaluating", "Quality review: checking fact grounding...")

    # Build available facts summary for reviewer
    available_facts = []
    for section in plan.sections:
        facts = kb.facts_for_section(section)
        for f in facts[:25]:
            available_facts.append(f"[{section}] {f.claim}")

    if insights:
        for ins in insights:
            available_facts.append(f"[Insight] {ins}")
    if contrarian_risks:
        for risk in contrarian_risks:
            available_facts.append(f"[Risk] {risk}")

    facts_summary = "\n".join(available_facts)

    review_score = 0.0
    review_weaknesses = []
    fabricated = []

    try:
        review_messages = [
            {"role": "system", "content": "You are a research editor. Return ONLY valid JSON."},
            {"role": "user", "content": PHASE4_REVIEW_PROMPT.format(
                topic=plan.topic,
                draft=draft[:10000],
                available_facts=facts_summary[:12000],
            )},
        ]
        response = await llm_reviewer.ainvoke(review_messages)
        track("P4 review", response)
        review = extract_json(get_content(response).strip())

        if isinstance(review, dict):
            review_score = float(review.get("overall", 5.0))
            review_weaknesses = review.get("weaknesses", [])
            if not isinstance(review_weaknesses, list):
                review_weaknesses = []
            fabricated = review.get("fabricated_claims", [])
            if not isinstance(fabricated, list):
                fabricated = []
    except Exception as e:
        logger.warning(f"[Phase 4] Review failed: {e}")
        review_score = 5.0

    # ── Refine if review found issues ─────────────────────────────────────
    refinement_ran = False
    pre_refinement_score = review_score
    issues_fixed = 0

    if review_score < 7.0 and review_weaknesses:
        notify("evaluating", f"Score {review_score:.1f}/10 — refining...")

        refine_instruction = (
            f"Your draft scored {review_score:.1f}/10. A reviewer flagged these specific issues:\n"
            + "\n".join(f"- {w}" for w in review_weaknesses)
        )
        if fabricated:
            refine_instruction += "\n\nThese claims are NOT supported by the provided facts — rewrite them using ONLY the provided data:\n"
            refine_instruction += "\n".join(f"- {c}" for c in fabricated)
        refine_instruction += (
            "\n\nIMPORTANT: Make SURGICAL fixes only. Keep everything that is already good. "
            "Do NOT rewrite sections that weren't flagged. "
            "For flagged claims: NEVER just delete a sentence — always REPLACE it with a "
            "fact-grounded alternative that preserves the paragraph's flow and coherence. "
            "Surrounding sentences may depend on the flagged one for context, so ensure "
            "the replacement maintains logical continuity. "
            "Do NOT add new claims or analysis beyond the provided data. "
            "Output the complete revised report starting with ## headings."
        )

        try:
            write_messages.append({"role": "assistant", "content": draft})
            write_messages.append({"role": "user", "content": refine_instruction})

            response = await llm_writer.ainvoke(write_messages)
            track("P4 refine", response)
            refined = get_content(response).strip()
            refined = strip_preamble(refined)

            if len(refined.split()) > 200:
                draft = refined
                word_count = len(draft.split())
                refinement_ran = True
                issues_fixed = len(review_weaknesses) + len(fabricated)
                notify("drafted", f"Refined draft: {word_count} words")

                # Re-score the refined draft
                try:
                    rescore_messages = [
                        {"role": "system", "content": "You are a research editor. Return ONLY valid JSON."},
                        {"role": "user", "content": PHASE4_REVIEW_PROMPT.format(
                            topic=plan.topic,
                            draft=draft[:10000],
                            available_facts=facts_summary[:12000],
                        )},
                    ]
                    rescore_response = await llm_reviewer.ainvoke(rescore_messages)
                    track("P4 re-review", rescore_response)
                    rescore = extract_json(get_content(rescore_response).strip())

                    if isinstance(rescore, dict):
                        new_score = float(rescore.get("overall", review_score))
                        notify("evaluating", f"Re-scored: {pre_refinement_score:.1f} → {new_score:.1f}/10")
                        if new_score > pre_refinement_score:
                            review_score = new_score
                        else:
                            review_score = pre_refinement_score
                            logger.info(f"[Phase 4] Re-score {new_score:.1f} <= original {pre_refinement_score:.1f}, keeping original")
                        new_weaknesses = rescore.get("weaknesses", [])
                        if isinstance(new_weaknesses, list):
                            review_weaknesses = new_weaknesses
                        new_fabricated = rescore.get("fabricated_claims", [])
                        if isinstance(new_fabricated, list):
                            fabricated = new_fabricated
                except Exception as e:
                    logger.warning(f"[Phase 4] Re-scoring failed: {e}")
        except Exception as e:
            logger.warning(f"[Phase 4] Refinement failed: {e}")

    elapsed = time.time() - start

    notify("done", f"Final report: {word_count} words, "
                    f"score {review_score:.1f}/10")

    # ── Build sources list ────────────────────────────────────────────────
    seen_urls = set()
    sources = []
    for fact in kb.facts:
        if fact.source_url and fact.source_url not in seen_urls:
            seen_urls.add(fact.source_url)
            sources.append(Source(
                url=fact.source_url,
                title=fact.source_title,
                snippet=fact.claim[:200],
                tier=fact.source_tier,
            ))

    # ── Build iteration_history for frontend ──────────────────────────────
    iteration_history = [
        {
            "iteration": 0,
            "score": review_score,
            "weaknesses": review_weaknesses[:3],
            "queries": [],
            "stop_reason": "threshold" if review_score >= 7.0 else "plateau",
        },
    ]

    return ResearchResult(
        layer=3,
        topic=plan.topic,
        content=draft,
        sources=sources,
        metadata={
            "method": "knowledge_synthesis",
            "iterations": 1,
            "final_score": review_score,
            "tool_calls": 0,
            "review_score": review_score,
            "refinement_ran": refinement_ran,
            "pre_refinement_score": pre_refinement_score,
            "issues_fixed": issues_fixed,
            "fabricated_claims": fabricated,
            "section_impacts": section_impacts,
            "iteration_history": iteration_history,
            "sources_found": len(sources),
            "sources_scraped": 0,
        },
        elapsed_seconds=elapsed,
    )


def _fallback_report(plan: ResearchPlan, kb: KnowledgeBase) -> str:
    """Generate a minimal report from raw knowledge if LLM fails."""
    parts = []
    for section in plan.sections:
        facts = kb.facts_for_section(section)
        parts.append(f"## {section}\n")
        if facts:
            for f in facts[:8]:
                parts.append(f"{f.claim}\n")
        else:
            parts.append("Limited data available for this section.\n")
        parts.append("")
    return "\n".join(parts)
