"""
Pipeline orchestrator — runs 3 research layers IN PARALLEL.

    Layer 0: BASELINE   — Single LLM prompt, no tools
    Layer 1: ENHANCED   — Web search + synthesis (ReAct agent)
    Layer 2: EXPERT     — Full pipeline (Plan → Research → Verify → Write)

All 3 layers run concurrently via asyncio.gather(). Each layer has its own
progress callback that emits events tagged with its layer number.

Produces a ComparisonReport compatible with the frontend/API.
"""

from __future__ import annotations

import asyncio
import logging
import time

from config import get_llm, set_model_tier
from research_agent.models import ResearchResult, ComparisonReport
from research_agent.layers import baseline, enhanced, expert
from research_agent.react_engine import generate_report_outline
from research_agent.evaluator import evaluate_all_layers, compare_layers
from research_agent.cost import reset_tracker

logger = logging.getLogger(__name__)


async def run_pipeline(
    topic: str,
    progress_callback=None,
) -> ComparisonReport:
    """
    Run all 3 research layers in parallel, then evaluate and compare.

    Returns a ComparisonReport with 3 layer results (0-2).
    """
    reset_tracker()
    total_start = time.time()

    def notify(layer: int, status: str, msg: str):
        if progress_callback:
            progress_callback(layer, status, msg)
        logger.info(f"[Pipeline] L{layer}: {status} — {msg}")

    notify(-1, "start", "Running 3 layers in parallel: Baseline, Enhanced, Expert...")

    # ── Generate shared report outline (one cheap LLM call) ───────────
    # All 3 layers use the same section headings so comparison works
    set_model_tier("budget")
    outline_llm = get_llm("planner")
    shared_outline = await generate_report_outline(topic, outline_llm)
    if shared_outline:
        notify(-1, "planned", f"Shared outline: {shared_outline.splitlines()[0]}")

    # ── Run all 3 layers concurrently ───────────────────────────────────
    results: list[ResearchResult] = [None, None, None]  # type: ignore
    errors: list[str | None] = [None, None, None]

    async def run_layer_0():
        try:
            results[0] = await baseline.run(topic, progress_callback, outline=shared_outline)
        except Exception as e:
            logger.error(f"[Pipeline] Baseline failed: {e}")
            errors[0] = str(e)
            results[0] = ResearchResult(
                layer=0, topic=topic, content=f"## Error\n\nBaseline failed: {e}",
                metadata={"method": "single_prompt", "error": str(e)},
            )

    async def run_layer_1():
        try:
            results[1] = await enhanced.run(topic, progress_callback, outline=shared_outline)
        except Exception as e:
            logger.error(f"[Pipeline] Enhanced failed: {e}")
            errors[1] = str(e)
            results[1] = ResearchResult(
                layer=1, topic=topic, content=f"## Error\n\nEnhanced research failed: {e}",
                metadata={"method": "enhanced_search", "error": str(e)},
            )

    async def run_layer_2():
        try:
            results[2] = await expert.run(topic, progress_callback, outline=shared_outline)
        except Exception as e:
            logger.error(f"[Pipeline] Expert failed: {e}")
            errors[2] = str(e)
            results[2] = ResearchResult(
                layer=2, topic=topic, content=f"## Error\n\nExpert analysis failed: {e}",
                metadata={"method": "cmi_expert", "error": str(e)},
            )

    await asyncio.gather(run_layer_0(), run_layer_1(), run_layer_2())

    # ── Evaluate & Compare ──────────────────────────────────────────────
    notify(-1, "evaluating", "Evaluating and comparing all 3 layers...")
    evaluations = await evaluate_all_layers(results)
    report = await compare_layers(results, evaluations)

    total_elapsed = time.time() - total_start
    notify(-1, "complete", f"Pipeline complete in {total_elapsed:.1f}s")

    return report
