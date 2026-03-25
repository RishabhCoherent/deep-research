"""
Pipeline orchestrator — runs 3 research layers.

    Layer 0: BASELINE       — Best model prompt, no tools → initial report
    Layer 1: ENHANCEMENT    — LangGraph agent + web search → enriched report
    Layer 2: DEEP DIVE      — LangGraph agent + web search → definitive analysis

L0 and L1 run in PARALLEL to save time. L2 receives L1's output.
All 3 results are visible in the frontend to show improvement progression.

Produces a ComparisonReport compatible with the frontend/API.
"""

from __future__ import annotations

import asyncio
import logging
import time

from config import get_llm, set_model_tier
from research_agent.models import ResearchResult, ComparisonReport
from research_agent.layers import baseline, enhanced, expert
from research_agent.evaluator import evaluate_all_layers, compare_layers
from research_agent.cost import reset_tracker
from research_agent.utils import generate_topic_scope, interpret_topic

logger = logging.getLogger(__name__)


async def run_pipeline(
    topic: str,
    brief: str = "",
    progress_callback=None,
) -> ComparisonReport:
    """
    Run all 3 research layers, then evaluate and compare.

    L0 and L1 run in parallel. L2 receives L1's output.
    Returns a ComparisonReport with 3 layer results.
    """
    reset_tracker()
    total_start = time.time()

    def notify(layer: int, status: str, msg: str):
        if progress_callback:
            progress_callback(layer, status, msg)
        logger.info(f"[Pipeline] L{layer}: {status} — {msg}")

    notify(-1, "start", "Starting pipeline: L0+L1 parallel → L2 deep dive...")

    # ── Interpret topic (disambiguate colloquial/ambiguous briefs) ──────
    notify(-1, "interpreting", "Interpreting research brief...")
    try:
        set_model_tier("budget")
        interpret_llm = get_llm("planner")
        topic = await interpret_topic(topic, interpret_llm, brief=brief)
        logger.info(f"[Pipeline] Using topic: {topic}")
    except Exception as e:
        logger.warning(f"[Pipeline] Topic interpretation failed (non-fatal): {e}")

    # ── Auto-generate scope boundaries ───────────────────────────────────
    notify(-1, "scoping", "Defining topic scope boundaries...")
    try:
        set_model_tier("budget")
        scope_llm = get_llm("planner")
        scope = await generate_topic_scope(topic, scope_llm)
        if scope:
            brief = f"TOPIC SCOPE (auto-generated — stay within these boundaries):\n\n{scope}\n\n{brief}" if brief else f"TOPIC SCOPE (auto-generated — stay within these boundaries):\n\n{scope}"
            logger.info(f"[Pipeline] Scope generated and prepended to brief")
    except Exception as e:
        logger.warning(f"[Pipeline] Scope generation failed (non-fatal): {e}")

    results: list[ResearchResult] = []

    # ── L0 + L1 in PARALLEL ───────────────────────────────────────────────
    # L1 doesn't need L0's output — it can search independently.
    # This saves ~30-60s by overlapping baseline generation with web research.
    notify(0, "start", "Layer 0: Generating baseline report...")
    notify(1, "start", "Layer 1: Web research (parallel with L0)...")

    async def _run_l0():
        try:
            return await baseline.run(topic, progress_callback, brief=brief)
        except Exception as e:
            logger.error(f"[Pipeline] Baseline failed: {e}")
            return ResearchResult(
                layer=0, topic=topic, content=f"## Error\n\nBaseline failed: {e}",
                metadata={"method": "single_prompt", "error": str(e)},
            )

    async def _run_l1():
        try:
            return await enhanced.run(
                topic, progress_callback,
                prior_report="",  # L1 searches independently
                prior_sources=None,
                brief=brief,
            )
        except Exception as e:
            logger.error(f"[Pipeline] Enhanced failed: {e}")
            return ResearchResult(
                layer=1, topic=topic, content=f"## Error\n\nEnhanced research failed: {e}",
                metadata={"method": "langgraph_enhancement", "error": str(e)},
            )

    result_l0, result_l1 = await asyncio.gather(_run_l0(), _run_l1())
    results.append(result_l0)
    results.append(result_l1)

    # ── L2: Deep Dive Agent (receives L1 report, or L0 as fallback) ───────
    prior_for_l2 = result_l1 if "error" not in result_l1.metadata else result_l0

    notify(2, "start", "Layer 2: Deep-dive analysis...")
    try:
        result_l2 = await expert.run(
            topic, progress_callback,
            prior_report=prior_for_l2.content,
            prior_sources=prior_for_l2.sources,
            brief=brief,
        )
    except Exception as e:
        logger.error(f"[Pipeline] Expert failed: {e}")
        result_l2 = ResearchResult(
            layer=2, topic=topic, content=f"## Error\n\nDeep-dive analysis failed: {e}",
            metadata={"method": "langgraph_deepdive", "error": str(e)},
        )
    results.append(result_l2)

    # ── Evaluate & Compare ────────────────────────────────────────────────
    # Evaluation temporarily disabled to reduce cost while iterating on L2 quality.
    # To re-enable: uncomment the two lines below and remove the skip block.
    # notify(-1, "evaluating", "Evaluating and comparing all 3 layers...")
    # evaluations = await evaluate_all_layers(results)
    # report = await compare_layers(results, evaluations)

    # Skip evaluation — build a minimal ComparisonReport with empty evals
    notify(-1, "evaluating", "Evaluation skipped (disabled for L2 iteration)")
    from research_agent.models import LayerEvaluation
    evaluations = [
        LayerEvaluation(
            layer=r.layer,
            source_diversity=len(r.sources),
            word_count=len(r.content.split()),
        )
        for r in results
    ]
    report = ComparisonReport(
        topic=topic,
        results=results,
        evaluations=evaluations,
        summary="Evaluation skipped — focusing on L2 quality iteration.",
    )

    total_elapsed = time.time() - total_start
    notify(-1, "complete", f"Pipeline complete in {total_elapsed:.1f}s")

    return report
