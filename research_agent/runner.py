"""
CLI runner for the multi-layer research agent.

Executes all 4 layers sequentially (each builds on the previous),
evaluates each output, and produces a comparison report.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from research_agent.types import ResearchResult, ComparisonReport
from research_agent import layer0_baseline, layer1_research, layer2_analysis, layer3_expert
from research_agent.evaluator import (
    evaluate_layer,
    evaluate_all_layers,
    compare_layers,
    format_evaluation_table,
    format_score_table,
)
from research_agent.cost import get_tracker, reset_tracker
from config import set_model_tier

# Progressive model tiers: each layer uses a better model than the last
PROGRESSIVE_TIERS = {
    0: "budget",      # gpt-4o-mini — fast baseline
    1: "standard",    # gpt-4o / gpt-4o-mini mix
    2: "premium",     # gpt-4.1 / gpt-4.1-mini
    3: "reasoning",   # o4-mini reasoning models
}

logger = logging.getLogger(__name__)


async def run_layer(topic: str, layer: int, previous: Optional[ResearchResult] = None) -> ResearchResult:
    """Run a single layer.

    Args:
        topic: The market research topic.
        layer: Layer number (0-3).
        previous: Result from the previous layer (required for layers 2-3).
    """
    if layer == 0:
        return await layer0_baseline.run(topic)
    elif layer == 1:
        return await layer1_research.run(topic)
    elif layer == 2:
        if previous is None:
            raise ValueError("Layer 2 requires Layer 1 result as input")
        return await layer2_analysis.run(topic, previous)
    elif layer == 3:
        if previous is None:
            raise ValueError("Layer 3 requires Layer 2 result as input")
        return await layer3_expert.run(topic, previous)
    else:
        raise ValueError(f"Unknown layer: {layer}")


async def run_all_layers(
    topic: str,
    max_layer: int = 3,
    progress_callback=None,
) -> ComparisonReport:
    """Run all layers sequentially and produce a comparison report.

    Args:
        topic: The market research topic to analyze.
        max_layer: Maximum layer to run (0-3). Default: run all 4.
        progress_callback: Optional callback(layer, status, message) for progress.
    """
    reset_tracker()
    total_start = time.time()
    results: list[ResearchResult] = []

    def notify(layer: int, status: str, msg: str):
        if progress_callback:
            progress_callback(layer, status, msg)
        logger.info(f"[Runner] Layer {layer} -- {status}: {msg}")

    # -- Layer 0: Baseline --------------------------------------
    set_model_tier(PROGRESSIVE_TIERS[0])
    notify(0, "start", "Generating baseline (no research)...")
    result_l0 = await layer0_baseline.run(topic)
    results.append(result_l0)
    notify(0, "done", f"{result_l0.word_count} words in {result_l0.elapsed_seconds:.1f}s")

    if max_layer < 1:
        return await _evaluate_and_compare(results)

    # -- Layer 1: Research --------------------------------------
    set_model_tier(PROGRESSIVE_TIERS[1])
    notify(1, "start", "Running web research agent...")
    result_l1 = await layer1_research.run(topic)
    results.append(result_l1)
    notify(1, "done", f"{result_l1.word_count} words, "
           f"{len(result_l1.sources)} sources in {result_l1.elapsed_seconds:.1f}s")

    if max_layer < 2:
        return await _evaluate_and_compare(results)

    # -- Layer 2: Analysis --------------------------------------
    set_model_tier(PROGRESSIVE_TIERS[2])
    notify(2, "start", "Running analysis agent (cross-reference + frameworks)...")
    result_l2 = await layer2_analysis.run(topic, result_l1)
    results.append(result_l2)
    notify(2, "done", f"{result_l2.word_count} words, "
           f"{len(result_l2.sources)} sources in {result_l2.elapsed_seconds:.1f}s")

    if max_layer < 3:
        return await _evaluate_and_compare(results)

    # -- Layer 3: Expert ----------------------------------------
    set_model_tier(PROGRESSIVE_TIERS[3])
    notify(3, "start", "Running expert agent (assumption challenging)...")
    result_l3 = await layer3_expert.run(topic, result_l2)
    results.append(result_l3)
    notify(3, "done", f"{result_l3.word_count} words, "
           f"{len(result_l3.sources)} sources in {result_l3.elapsed_seconds:.1f}s")

    # -- Evaluate & Compare -------------------------------------
    report = await _evaluate_and_compare(results)

    total_elapsed = time.time() - total_start
    notify(-1, "complete", f"All layers complete in {total_elapsed:.1f}s total")

    return report


async def _evaluate_and_compare(results: list[ResearchResult]) -> ComparisonReport:
    """Evaluate all results comparatively and generate comparison."""
    # Use comparative evaluation: single LLM call scores all layers side by side
    evaluations = await evaluate_all_layers(results)

    report = await compare_layers(results, evaluations)
    return report


def print_report(report: ComparisonReport):
    """Print a formatted comparison report to the console."""
    print("\n" + "=" * 80)
    print(f"  MULTI-LAYER RESEARCH COMPARISON: {report.topic}")
    print("=" * 80)

    # Print each layer's output
    layer_names = {
        0: "LAYER 0 -- BASELINE (No Research)",
        1: "LAYER 1 -- RESEARCH AGENT (Web Search + Synthesis)",
        2: "LAYER 2 -- ANALYSIS AGENT (Cross-Reference + Frameworks)",
        3: "LAYER 3 -- EXPERT AGENT (Assumption Challenging + Contrarian)",
    }

    for result in report.results:
        print(f"\n{'-' * 80}")
        print(f"  {layer_names.get(result.layer, f'LAYER {result.layer}')}")
        print(f"  Words: {result.word_count} | Sources: {len(result.sources)} | "
              f"Time: {result.elapsed_seconds:.1f}s")
        print(f"{'-' * 80}")
        print(result.content)
        print()

    # Print evaluation tables
    if report.evaluations:
        print(f"\n{'=' * 80}")
        print("  QUALITY METRICS")
        print("=" * 80)
        print(format_evaluation_table(report.evaluations))
        print()
        print(format_score_table(report.evaluations))

    # Print cost breakdown
    tracker = get_tracker()
    if tracker.total_calls > 0:
        print(f"\n{'=' * 80}")
        print("  COST BREAKDOWN")
        print("=" * 80)
        print(tracker.format_table())

    # Print comparison summary
    if report.summary:
        print(f"\n{'=' * 80}")
        print("  COMPARISON SUMMARY")
        print("=" * 80)
        print(report.summary)

    print(f"\n{'=' * 80}")


def save_report(report: ComparisonReport, output_dir: str = "outputs"):
    """Save the comparison report to files."""
    import os
    import json

    os.makedirs(output_dir, exist_ok=True)

    # Sanitize topic for filename
    safe_topic = "".join(c if c.isalnum() or c in " -_" else "_" for c in report.topic)
    safe_topic = safe_topic[:50].strip().replace(" ", "_")

    # Save each layer's content as a text file
    for result in report.results:
        path = os.path.join(output_dir, f"layer{result.layer}_{safe_topic}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Layer {result.layer} -- {report.topic}\n\n")
            f.write(f"Words: {result.word_count} | Sources: {len(result.sources)} | "
                    f"Time: {result.elapsed_seconds:.1f}s\n\n")
            f.write(result.content)
        logger.info(f"Saved Layer {result.layer} to {path}")

    # Save full comparison as JSON
    json_path = os.path.join(output_dir, f"comparison_{safe_topic}.json")
    data = {
        "topic": report.topic,
        "layers": [],
        "evaluations": [],
        "summary": report.summary,
    }

    for result in report.results:
        data["layers"].append({
            "layer": result.layer,
            "word_count": result.word_count,
            "source_count": len(result.sources),
            "elapsed_seconds": result.elapsed_seconds,
            "metadata": result.metadata,
            "content": result.content,
        })

    for ev in report.evaluations:
        raw = getattr(ev, "_raw_scores", {})
        data["evaluations"].append({
            "layer": ev.layer,
            "word_count": ev.word_count,
            "source_diversity": ev.source_diversity,
            "insight_depth": ev.insight_depth,
            "framework_usage": ev.framework_usage,
            "contrarian_views": ev.contrarian_views,
            "elapsed_seconds": ev.elapsed_seconds,
            "scores": raw,
        })

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved comparison JSON to {json_path}")

    # Save evaluation table as text
    table_path = os.path.join(output_dir, f"evaluation_{safe_topic}.txt")
    with open(table_path, "w", encoding="utf-8") as f:
        f.write(f"MULTI-LAYER RESEARCH COMPARISON: {report.topic}\n\n")
        f.write("QUALITY METRICS:\n")
        f.write(format_evaluation_table(report.evaluations))
        f.write("\n\nSCORE TABLE:\n")
        f.write(format_score_table(report.evaluations))
        f.write(f"\n\nCOMPARISON SUMMARY:\n{report.summary}\n")
    logger.info(f"Saved evaluation table to {table_path}")

    return json_path
