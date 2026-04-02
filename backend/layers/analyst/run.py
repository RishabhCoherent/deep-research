"""
Analyst Agent Orchestrator — wires all phases together.

DECOMPOSE → INVESTIGATE → ANALYZE → QUALITY GATE → (retry?) → COMPOSE

Returns ResearchResult compatible with the existing pipeline.
"""

import logging
import time

from models.analyst import ResearchBoard, ResearchTrace, AnalysisResult
from layers.analyst.decomposer import decompose
from layers.analyst.investigator import investigate
from layers.analyst.analyzer import analyze
from layers.analyst.composer import compose
from layers.analyst.quality_gate import score_research
from models.pipeline import ResearchResult, Source

logger = logging.getLogger(__name__)


async def run_analyst(
    topic: str,
    progress_callback=None,
    prior_report: str = "",
    prior_sources: list[Source] | None = None,
    brief: str = "",
) -> ResearchResult:
    """Run the full analyst pipeline.

    Returns a ResearchResult compatible with the existing pipeline contract.
    """
    start_time = time.time()
    sources: list[Source] = list(prior_sources or [])
    phase_timings: dict = {}
    trace = ResearchTrace(topic=topic)

    def notify(phase: str, message: str):
        logger.info(f"[Analyst] {phase}: {message[:120]}")
        if progress_callback:
            progress_callback(2, phase, message)

    # ── Phase 1: DECOMPOSE ────────────────────────────────────────────────

    t0 = time.time()
    notify("decompose", "Breaking down the research problem...")

    try:
        framework = await decompose(topic, brief, notify)
    except Exception as e:
        logger.error(f"[Analyst] Decompose failed: {e}")
        from layers.analyst.decomposer import _fallback_framework
        framework = _fallback_framework(topic)

    decompose_elapsed = round(time.time() - t0, 1)
    phase_timings["decompose"] = {
        "sub_questions": len(framework.sub_questions),
        "p1_count": sum(1 for sq in framework.sub_questions if sq.priority == 1),
        "p2_count": sum(1 for sq in framework.sub_questions if sq.priority == 2),
        "elapsed_s": decompose_elapsed,
    }

    # Record decompose trace
    trace.add("decompose", f"Decomposed into {len(framework.sub_questions)} questions", {
        "core_question": framework.core_question,
        "assumptions": framework.assumptions,
        "scope_in": framework.scope_in,
        "scope_out": framework.scope_out,
        "report_sections": framework.report_sections,
        "sub_questions": [
            {"id": sq.id, "question": sq.question, "answer_type": sq.answer_type,
             "research_strategy": sq.research_strategy, "priority": sq.priority,
             "depends_on": sq.depends_on, "search_queries": sq.search_queries}
            for sq in framework.sub_questions
        ],
    }, elapsed_s=decompose_elapsed)

    # ── Initialize Research Board ─────────────────────────────────────────

    # Budget: ~10 tool calls per question (think + 3 search + 2 scrape + reflect + overhead)
    # + 20 for limited tree expansion (breadth over depth — cover all questions first)
    num_questions = len(framework.sub_questions)
    budget = max(100, num_questions * 10) + 20
    board = ResearchBoard(
        framework=framework,
        tool_calls_budget=budget,
    )

    # Add prior sources to the board's URL tracking
    for s in sources:
        pass  # Sources are shared via the list reference

    # ── Phase 2: INVESTIGATE (with quality gate loop) ─────────────────────

    for iteration in range(board.max_iterations + 1):
        t1 = time.time()
        board.iteration_count = iteration

        if iteration == 0:
            notify("investigate", "Starting structured research...")
        else:
            notify("investigate", f"Remediation pass {iteration}...")

        try:
            await investigate(board, topic, sources, notify, brief, trace=trace)
        except Exception as e:
            logger.error(f"[Analyst] Investigation failed (iter {iteration}): {e}")
            break

        phase_timings[f"investigate_{iteration}"] = {
            "searches": board.searches_done,
            "scrapes_done": board.scrapes_done,
            "scrapes_failed": board.scrapes_failed,
            "evidence": len(board.evidence),
            "coverage": round(board.coverage, 2),
            "tool_calls": board.tool_calls_used,
            "tree_nodes": board.research_tree.total_nodes,
            "tree_max_depth": board.research_tree.max_depth_reached,
            "elapsed_s": round(time.time() - t1, 1),
        }

        # ── Phase 3: ANALYZE ──────────────────────────────────────────────

        t2 = time.time()
        notify("analyze", "Cross-referencing findings...")

        try:
            analysis_result = await analyze(board, topic, notify)
        except Exception as e:
            logger.error(f"[Analyst] Analysis failed: {e}")
            analysis_result = AnalysisResult(
                overall_confidence=0.5,
                narrative_thread="Analysis incomplete.",
            )

        analyze_elapsed = round(time.time() - t2, 1)
        phase_timings[f"analyze_{iteration}"] = {
            "key_findings": len(analysis_result.key_findings),
            "judgments": len(analysis_result.judgments),
            "causal_chains": len(analysis_result.causal_chains),
            "confidence": analysis_result.overall_confidence,
            "elapsed_s": analyze_elapsed,
        }

        # Record analyze trace
        trace.add("analyze", f"Analysis: {len(analysis_result.key_findings)} findings, {len(analysis_result.judgments)} judgments", {
            "key_findings": analysis_result.key_findings,
            "judgments": [
                {"claim": j.claim, "conviction": j.conviction, "reasoning": j.reasoning,
                 "supporting_evidence": j.supporting_evidence, "counter_evidence": j.counter_evidence}
                for j in analysis_result.judgments
            ],
            "causal_chains": analysis_result.causal_chains,
            "narrative_thread": analysis_result.narrative_thread,
            "evidence_gaps": analysis_result.evidence_gaps,
            "overall_confidence": analysis_result.overall_confidence,
        }, elapsed_s=analyze_elapsed)

        # ── Phase 4: QUALITY GATE ─────────────────────────────────────────

        quality = score_research(board, analysis_result)
        board.quality_scores = {
            "coverage": quality.coverage,
            "evidence_strength": quality.evidence_strength,
            "evidence_depth": quality.evidence_depth,
            "contradiction_resolution": quality.contradiction_resolution,
            "judgment_formation": quality.judgment_formation,
            "gap_acknowledgment": quality.gap_acknowledgment,
            "overall": quality.overall,
        }

        notify("quality_gate",
               f"Quality: {quality.overall:.0%} ({'PASS' if quality.passes else 'FAIL'})")

        # Record quality gate trace
        trace.add("quality", f"Quality: {quality.overall:.0%} — {'PASS' if quality.passes else 'FAIL'}", {
            "coverage": quality.coverage,
            "evidence_strength": quality.evidence_strength,
            "contradiction_resolution": quality.contradiction_resolution,
            "judgment_formation": quality.judgment_formation,
            "gap_acknowledgment": quality.gap_acknowledgment,
            "overall": quality.overall,
            "passes": quality.passes,
            "feedback": quality.feedback,
            "remediation_queries": quality.remediation_queries,
            "iteration": iteration,
        })

        if quality.passes or board.budget_remaining < 8:
            break

        # Didn't pass — add remediation queries to pending sub-questions
        if quality.remediation_queries:
            logger.info(f"[Analyst] Quality gate failed, {len(quality.remediation_queries)} remediation queries")
            # Boost budget for remediation (cap total boost at 30)
            total_boosted = board.tool_calls_budget - board.tool_calls_used
            boost = min(15, 30 - max(0, total_boosted))
            if boost > 0:
                board.tool_calls_budget += boost

    # ── Phase 5: COMPOSE ──────────────────────────────────────────────────

    t3 = time.time()
    notify("compose", "Writing final report...")

    try:
        draft = await compose(board, analysis_result, topic, notify)
    except Exception as e:
        logger.error(f"[Analyst] Compose failed: {e}")
        draft = "## Error\n\nAnalyst pipeline composition failed."

    compose_elapsed = round(time.time() - t3, 1)
    phase_timings["compose"] = {
        "word_count": len(draft.split()),
        "elapsed_s": compose_elapsed,
    }

    # Record compose trace
    trace.add("compose", f"Report: {len(draft.split())} words", {
        "word_count": len(draft.split()),
        "sections": board.framework.report_sections,
    }, elapsed_s=compose_elapsed)

    # ── Build Result ──────────────────────────────────────────────────────

    elapsed = time.time() - start_time
    word_count = len(draft.split())

    notify("done",
           f"Analyst complete: {word_count} words, {len(board.evidence)} evidence, "
           f"{board.coverage:.0%} coverage in {elapsed:.0f}s")

    return ResearchResult(
        layer=2,
        topic=topic,
        content=draft,
        sources=sources,
        metadata={
            "method": "analyst_agent",
            "phases": phase_timings,
            "board": board.to_dict(),
            "analysis": {
                "key_findings": analysis_result.key_findings,
                "judgments": [
                    {"claim": j.claim, "conviction": j.conviction, "reasoning": j.reasoning[:200]}
                    for j in analysis_result.judgments
                ],
                "confidence": analysis_result.overall_confidence,
                "narrative": analysis_result.narrative_thread,
            },
            "quality": board.quality_scores,
            "evidence_count": len(board.evidence),
            "searches_count": board.searches_done,
            "scrapes_done": board.scrapes_done,
            "scrapes_failed": board.scrapes_failed,
            "tool_calls": board.tool_calls_used,
            "coverage": board.coverage,
            "research_tree": board.research_tree.to_dict(),
            "trace": trace.to_dict(),
        },
        elapsed_seconds=elapsed,
        trace=trace,
    )
