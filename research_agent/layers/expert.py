"""
Layer 2 — EXPERT: Full agentic pipeline (Plan → Research → Verify → Write).

This is the premium layer that runs the complete 4-phase knowledge-driven pipeline:
  Phase 1: UNDERSTAND → Research Plan
  Phase 2: RESEARCH   → Knowledge Base (systematic data collection)
  Phase 3: ANALYZE    → Verified KB + Insights + Contrarian Risks
  Phase 4: WRITE      → Publication-ready report with review loop

Returns a single ResearchResult (layer=2) with the final report.
Internal phase details are captured in metadata for frontend visualization.
"""

from __future__ import annotations

import logging
import time

from config import set_model_tier
from research_agent.models import ResearchResult, Source
from research_agent.phases import understand, research, analyze, write
from research_agent.react_engine import parse_outline_sections, parse_outline_type

logger = logging.getLogger(__name__)

# Model tiers for each internal phase
PHASE_TIERS = {
    1: "standard",   # Planning (gpt-4o — needs to detect report type accurately)
    2: "standard",   # Research + extraction
    3: "premium",    # Verification + insights (gpt-4.1)
    4: "reasoning",  # Writing + review (gpt-5.2 — best model for deep analysis)
}


def _phase_callback(progress_callback, layer=2):
    """Create a callback that maps internal phase progress to layer 2."""
    def callback(_, status, msg):
        if progress_callback:
            progress_callback(layer, status, msg)
    return callback


async def run(
    topic: str,
    progress_callback=None,
    outline: str = "",
) -> ResearchResult:
    """Run the full expert pipeline: Plan → Research → Verify → Write."""
    start = time.time()
    phase_results = []

    def notify(status: str, msg: str):
        if progress_callback:
            progress_callback(2, status, msg)
        logger.info(f"[Expert] {status}: {msg}")

    notify("start", "Starting expert analysis (full pipeline)...")

    # ── Phase 1: UNDERSTAND ─────────────────────────────────────────────
    set_model_tier(PHASE_TIERS[1])
    notify("planning", "Phase 1: Creating research plan...")

    shared_sections = parse_outline_sections(outline) if outline else []
    report_type = parse_outline_type(outline) if outline else ""
    plan, result_p1 = await understand.run(
        topic, progress_callback=None, section_names=shared_sections,
        report_type=report_type,
    )

    questions_by_section = {}
    for q in plan.questions:
        if q.section not in questions_by_section:
            questions_by_section[q.section] = []
        questions_by_section[q.section].append({
            "question": q.question,
            "priority": q.priority,
            "data_type": q.data_type,
            "queries": q.search_queries[:2],
        })

    phase_results.append({
        "phase": "plan",
        "sections": len(plan.sections),
        "questions": len(plan.questions),
        "report_type": plan.report_type,
        "section_names": plan.sections,
        "questions_by_section": questions_by_section,
        "elapsed": round(result_p1.elapsed_seconds, 1),
    })

    notify("planning", f"Plan ready: {plan.report_type}, "
                        f"{len(plan.sections)} sections, {len(plan.questions)} questions")

    # ── Phase 2: RESEARCH ───────────────────────────────────────────────
    set_model_tier(PHASE_TIERS[2])
    notify("researching", "Phase 2: Systematic data collection...")

    kb, result_p2 = await research.run(plan, progress_callback=_phase_callback(progress_callback))

    facts_by_section = {}
    for section in plan.sections:
        section_facts = kb.facts_for_section(section)
        facts_by_section[section] = len(section_facts)

    phase_results.append({
        "phase": "research",
        "facts": len(kb.facts),
        "sources": len(kb.urls_seen),
        "coverage": round(kb.coverage_score(plan), 3),
        "facts_by_section": facts_by_section,
        "questions_answered": len([q for q in plan.questions if q.status == "answered"]),
        "questions_gap": len([q for q in plan.questions if q.status == "gap"]),
        "elapsed": round(result_p2.elapsed_seconds, 1),
    })

    notify("researching", f"Collected {len(kb.facts)} facts from {len(kb.urls_seen)} sources")

    # ── Phase 3: ANALYZE ────────────────────────────────────────────────
    set_model_tier(PHASE_TIERS[3])
    notify("evaluating", "Phase 3: Verifying and analyzing data...")

    kb, insights, contrarian_risks, section_impacts, result_p3 = \
        await analyze.run(plan, kb, progress_callback=_phase_callback(progress_callback))

    verify_by_section = {}
    for section in plan.sections:
        section_facts = kb.facts_for_section(section)
        high_conf = sum(1 for f in section_facts if f.confidence == "high")
        verify_by_section[section] = {
            "total": len(section_facts),
            "high_confidence": high_conf,
        }

    phase_results.append({
        "phase": "verify",
        "verified": result_p3.metadata.get("facts_verified", 0),
        "corrected": result_p3.metadata.get("facts_corrected", 0),
        "insights": len(insights),
        "risks": len(contrarian_risks),
        "insight_texts": insights[:8],
        "risk_texts": contrarian_risks[:6],
        "section_impacts": section_impacts[:10],
        "verify_by_section": verify_by_section,
        "elapsed": round(result_p3.elapsed_seconds, 1),
    })

    notify("evaluating", f"Verified: {result_p3.metadata.get('verifications', 0)} checks, "
                          f"{len(insights)} insights")

    # ── Phase 4: WRITE ──────────────────────────────────────────────────
    set_model_tier(PHASE_TIERS[4])
    notify("drafted", "Phase 4: Writing final report...")

    result_p4 = await write.run(
        plan, kb, insights, contrarian_risks, section_impacts,
        progress_callback=_phase_callback(progress_callback),
    )
    phase_results.append({
        "phase": "write",
        "words": result_p4.word_count,
        "review_score": result_p4.metadata.get("review_score", 0),
        "refinement_ran": result_p4.metadata.get("refinement_ran", False),
        "pre_refinement_score": result_p4.metadata.get("pre_refinement_score", 0),
        "issues_fixed": result_p4.metadata.get("issues_fixed", 0),
        "elapsed": round(result_p4.elapsed_seconds, 1),
    })

    elapsed = time.time() - start

    notify("done", f"Expert complete: {result_p4.word_count} words, "
                    f"score {result_p4.metadata.get('review_score', 0):.1f}/10 in {elapsed:.1f}s")

    # ── Build combined sources from knowledge base ──────────────────────
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

    # ── Build iteration_history for frontend (from internal phases) ─────
    iteration_history = [
        {
            "iteration": 0,
            "score": round(kb.coverage_score(plan) * 10, 1),
            "weaknesses": [f"Gap: {q.question}" for q in plan.questions if q.status == "gap"][:3],
            "queries": result_p2.metadata.get("iteration_history", [{}])[0].get("queries", [])
                       if result_p2.metadata.get("iteration_history") else [],
            "stop_reason": "",
        },
        {
            "iteration": 1,
            "score": result_p4.metadata.get("review_score", 0),
            "weaknesses": result_p4.metadata.get("fabricated_claims", [])[:3],
            "queries": result_p3.metadata.get("iteration_history", [{}])[0].get("queries", [])
                       if result_p3.metadata.get("iteration_history") else [],
            "stop_reason": "threshold",
        },
    ]

    return ResearchResult(
        layer=2,
        topic=topic,
        content=result_p4.content,
        sources=sources,
        metadata={
            "method": "cmi_expert",
            "iterations": 2,
            "final_score": result_p4.metadata.get("review_score", 0),
            "tool_calls": (result_p2.metadata.get("tool_calls", 0)
                          + result_p3.metadata.get("tool_calls", 0)),
            "sources_found": len(sources),
            "sources_scraped": result_p2.metadata.get("sources_scraped", 0),
            "iteration_history": iteration_history,
            "phase_details": phase_results,
            "plan_sections": plan.sections,
            "plan_questions": len(plan.questions),
            "facts_collected": len(kb.facts),
            "facts_verified": result_p3.metadata.get("facts_verified", 0),
            "insights_generated": len(insights),
            "contrarian_risks": len(contrarian_risks),
            "review_score": result_p4.metadata.get("review_score", 0),
        },
        elapsed_seconds=elapsed,
    )
