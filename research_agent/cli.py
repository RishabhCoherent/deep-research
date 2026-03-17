"""
CLI utilities for printing and saving research reports.

Used by run_research.py for console output and file persistence.
"""

from __future__ import annotations

import json
import logging
import os

from research_agent.models import ComparisonReport
from research_agent.evaluator import format_evaluation_table, format_score_table

logger = logging.getLogger(__name__)


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

    # Print layer improvement analysis
    if report.layer_comparisons:
        print(f"\n{'=' * 80}")
        print("  LAYER IMPROVEMENT ANALYSIS")
        print("=" * 80)
        layer_names_short = {
            0: "Baseline",
            1: "Enhanced (web search + synthesis)",
            2: "CMI Expert (full pipeline)",
        }
        for lc in report.layer_comparisons:
            from_name = layer_names_short.get(lc.from_layer, f"Layer {lc.from_layer}")
            to_name = layer_names_short.get(lc.to_layer, f"Layer {lc.to_layer}")
            delta_str = f"+{lc.score_delta:.1f}" if lc.score_delta >= 0 else f"{lc.score_delta:.1f}"
            print(f"\n  L{lc.from_layer} ({from_name}) → L{lc.to_layer} ({to_name})  [{delta_str}/10]")
            print(f"  {'-' * 70}")
            if lc.overall_verdict:
                print(f"  Verdict: {lc.overall_verdict}")
            for i, imp in enumerate(lc.improvements, 1):
                print(f"    {i}. {imp}")
            if lc.key_evidence:
                print(f"\n  Key Evidence: {lc.key_evidence[:400]}")
            print()

    # Print comparison summary
    if report.summary:
        print(f"\n{'=' * 80}")
        print("  COMPARISON SUMMARY")
        print("=" * 80)
        print(report.summary)

    print(f"\n{'=' * 80}")


def save_report(report: ComparisonReport, output_dir: str = "outputs"):
    """Save the comparison report to files."""
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
        "layer_comparisons": [],
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

    for lc in report.layer_comparisons:
        data["layer_comparisons"].append({
            "from_layer": lc.from_layer,
            "to_layer": lc.to_layer,
            "improvements": lc.improvements,
            "score_delta": lc.score_delta,
            "key_evidence": lc.key_evidence,
            "overall_verdict": lc.overall_verdict,
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
        if report.layer_comparisons:
            f.write("\n\nLAYER IMPROVEMENT ANALYSIS:\n")
            for lc in report.layer_comparisons:
                f.write(f"\n  L{lc.from_layer} → L{lc.to_layer} "
                        f"[{'+'if lc.score_delta>=0 else ''}{lc.score_delta:.1f}/10]\n")
                if lc.overall_verdict:
                    f.write(f"  Verdict: {lc.overall_verdict}\n")
                for i, imp in enumerate(lc.improvements, 1):
                    f.write(f"    {i}. {imp}\n")
                if lc.key_evidence:
                    f.write(f"  Key Evidence: {lc.key_evidence[:400]}\n")
        f.write(f"\n\nCOMPARISON SUMMARY:\n{report.summary}\n")
    logger.info(f"Saved evaluation table to {table_path}")

    return json_path
