"""
Evaluation & Comparison framework for multi-layer research outputs.

Uses LLM to evaluate all layers COMPARATIVELY in a single call on 6 dimensions,
then generates a comparative summary showing progressive improvement.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from config import get_llm
from research_agent.types import ResearchResult, LayerEvaluation, ComparisonReport
from research_agent.prompts import (
    EVALUATION_PROMPT,
    COMPARATIVE_EVALUATION_PROMPT,
    COMPARISON_SUMMARY,
)
from research_agent.utils import extract_json_scores
from research_agent.cost import track

logger = logging.getLogger(__name__)

LAYER_NAMES = {
    0: "Baseline (no research)",
    1: "Research Agent (web search + synthesis)",
    2: "Analysis Agent (cross-reference + frameworks)",
    3: "Expert Agent (assumption challenging + contrarian views)",
}

DIMS = [
    "factual_density", "source_grounding", "analytical_depth",
    "specificity", "insight_quality", "completeness",
]


def _build_layer_evaluation(
    result: ResearchResult,
    scores: dict,
) -> LayerEvaluation:
    """Build a LayerEvaluation from a result and its scores dict."""

    def get_score(key: str) -> float:
        val = scores.get(key, {})
        if isinstance(val, dict):
            return float(val.get("score", 0))
        return float(val) if val else 0.0

    # Map insight quality score to depth label
    iq = get_score("insight_quality")
    if iq >= 8:
        depth = "expert"
    elif iq >= 6:
        depth = "deep"
    elif iq >= 4:
        depth = "moderate"
    else:
        depth = "shallow"

    # Detect frameworks mentioned in content
    frameworks_detected = []
    content_lower = result.content.lower()
    framework_keywords = {
        "Porter's Five Forces": ["porter", "five forces", "bargaining power", "threat of"],
        "PEST Analysis": ["pest", "political", "economic", "social", "technological"],
        "SWOT Analysis": ["swot", "strengths", "weaknesses", "opportunities", "threats"],
        "Value Chain": ["value chain", "upstream", "downstream"],
    }
    for framework, keywords in framework_keywords.items():
        if any(kw in content_lower for kw in keywords):
            frameworks_detected.append(framework)

    # Count contrarian indicators
    contrarian_keywords = [
        "however", "contrary to", "despite", "risk", "bear case",
        "assumption", "if.*fails", "challenge", "overlooked", "contrarian",
    ]
    contrarian_count = sum(
        1 for kw in contrarian_keywords
        if kw in content_lower
    )

    eval_result = LayerEvaluation(
        layer=result.layer,
        factual_density=get_score("factual_density"),
        source_diversity=len(result.sources),
        specificity_score=get_score("specificity"),
        framework_usage=frameworks_detected,
        insight_depth=depth,
        contrarian_views=contrarian_count,
        word_count=result.word_count,
        elapsed_seconds=result.elapsed_seconds,
    )

    # Store full scores in metadata for the report
    eval_result._raw_scores = scores  # type: ignore

    return eval_result


async def evaluate_all_layers(
    results: list[ResearchResult],
) -> list[LayerEvaluation]:
    """Evaluate ALL layers comparatively in a single LLM call.

    This ensures consistent scoring — the evaluator sees all layers side by side
    and scores them relative to each other, eliminating the noise from independent
    evaluations.
    """
    if not results:
        return []

    topic = results[0].topic
    sorted_results = sorted(results, key=lambda r: r.layer)

    # Build the layers content block — increased cap to 6000 chars per layer
    layers_parts = []
    for r in sorted_results:
        name = LAYER_NAMES.get(r.layer, f"Layer {r.layer}")
        layers_parts.append(
            f"--- LAYER {r.layer}: {name} ({r.word_count} words, "
            f"{len(r.sources)} sources) ---\n{r.content[:6000]}"
        )
    layers_content = "\n\n".join(layers_parts)

    # Build the JSON template dynamically based on actual layers
    json_parts = []
    for r in sorted_results:
        dim_entries = ",\n      ".join(
            f'"{d}": {{"score": N, "justification": "..."}}'
            for d in DIMS
        )
        json_parts.append(f'  "layer_{r.layer}": {{\n      {dim_entries}\n    }}')
    json_template = ",\n  ".join(json_parts)

    logger.info(f"[Evaluator] Comparative evaluation of {len(results)} layers")

    llm = get_llm("reviewer")
    messages = [
        {"role": "system", "content": "You are a research quality evaluator. Return ONLY valid JSON."},
        {"role": "user", "content": COMPARATIVE_EVALUATION_PROMPT.format(
            topic=topic,
            num_layers=len(results),
            layers_content=layers_content,
            json_template=json_template,
        )},
    ]

    all_scores: dict[int, dict] = {}
    try:
        response = llm.invoke(messages)
        track("Eval comparative", response)
        text = response.content.strip()

        # Parse the comparative JSON response
        parsed = extract_json_scores(text)
        if parsed:
            # The response should have keys like "layer_0", "layer_1", etc.
            for r in sorted_results:
                key = f"layer_{r.layer}"
                if key in parsed:
                    all_scores[r.layer] = parsed[key]
                else:
                    # Fallback: maybe the scores are flat (single layer response)
                    logger.warning(f"[Evaluator] Missing {key} in comparative response")
                    all_scores[r.layer] = {}

            # If no layer_N keys found, it might be a flat dict (fallback for 1 layer)
            if not all_scores or all(not v for v in all_scores.values()):
                if len(results) == 1 and any(d in parsed for d in DIMS):
                    all_scores[sorted_results[0].layer] = parsed
                    logger.info("[Evaluator] Single-layer fallback: used flat scores")

        if not all_scores:
            logger.warning("[Evaluator] No scores extracted from comparative evaluation")
    except Exception as e:
        logger.warning(f"[Evaluator] Comparative evaluation failed: {e}")

    # Build LayerEvaluation objects
    evaluations = []
    for r in sorted_results:
        scores = all_scores.get(r.layer, {})
        ev = _build_layer_evaluation(r, scores)
        evaluations.append(ev)

    return evaluations


async def evaluate_layer(result: ResearchResult) -> LayerEvaluation:
    """Evaluate a single layer's output on 6 quality dimensions.

    NOTE: Prefer evaluate_all_layers() for multi-layer runs — it scores
    comparatively in one call, producing more consistent results.
    This function is kept as a fallback for single-layer evaluation.
    """
    layer_name = LAYER_NAMES.get(result.layer, f"Layer {result.layer}")
    logger.info(f"[Evaluator] Evaluating {layer_name}")

    llm = get_llm("reviewer")
    messages = [
        {"role": "system", "content": "You are a research quality evaluator. Return ONLY valid JSON."},
        {"role": "user", "content": EVALUATION_PROMPT.format(
            topic=result.topic,
            layer_name=layer_name,
            content=result.content[:6000],
        )},
    ]

    scores = {}
    try:
        response = llm.invoke(messages)
        track(f"Eval L{result.layer}", response)
        text = response.content.strip()
        scores = extract_json_scores(text)
        if not scores:
            logger.warning(f"[Evaluator] No scores extracted for Layer {result.layer}")
    except Exception as e:
        logger.warning(f"[Evaluator] Evaluation failed for Layer {result.layer}: {e}")
        scores = {}

    return _build_layer_evaluation(result, scores)


async def compare_layers(
    results: list[ResearchResult],
    evaluations: list[LayerEvaluation],
) -> ComparisonReport:
    """Generate a comparative summary across all layers."""
    if not results:
        return ComparisonReport(topic="", summary="No results to compare.")

    topic = results[0].topic

    # Build evaluation summaries for the comparison prompt
    def eval_summary(ev: LayerEvaluation) -> str:
        raw = getattr(ev, "_raw_scores", {})
        parts = []
        for dim in DIMS:
            info = raw.get(dim, {})
            if isinstance(info, dict):
                parts.append(f"  {dim}: {info.get('score', 'N/A')}/10 — {info.get('justification', '')}")
            else:
                parts.append(f"  {dim}: {info}")
        parts.append(f"  sources: {ev.source_diversity}")
        parts.append(f"  frameworks: {', '.join(ev.framework_usage) if ev.framework_usage else 'none'}")
        parts.append(f"  elapsed: {ev.elapsed_seconds:.1f}s")
        return "\n".join(parts)

    # Pad with empty defaults if we have fewer than 4 layers
    def get_eval(layer: int) -> LayerEvaluation:
        for ev in evaluations:
            if ev.layer == layer:
                return ev
        return LayerEvaluation(layer=layer)

    def get_words(layer: int) -> int:
        for r in results:
            if r.layer == layer:
                return r.word_count
        return 0

    llm = get_llm("analyst")
    messages = [
        {"role": "system", "content": "You are a research quality analyst."},
        {"role": "user", "content": COMPARISON_SUMMARY.format(
            topic=topic,
            l0_words=get_words(0),
            l0_eval=eval_summary(get_eval(0)),
            l1_words=get_words(1),
            l1_eval=eval_summary(get_eval(1)),
            l2_words=get_words(2),
            l2_eval=eval_summary(get_eval(2)),
            l3_words=get_words(3),
            l3_eval=eval_summary(get_eval(3)),
        )},
    ]

    try:
        response = llm.invoke(messages)
        track("Eval compare", response)
        summary = response.content.strip()
    except Exception as e:
        logger.error(f"[Evaluator] Comparison summary failed: {e}")
        summary = f"Error generating comparison: {e}"

    return ComparisonReport(
        topic=topic,
        results=results,
        evaluations=evaluations,
        summary=summary,
    )


def format_evaluation_table(evaluations: list[LayerEvaluation]) -> str:
    """Format evaluations as a readable ASCII table for console output."""
    header = (
        f"{'Layer':<10} | {'Words':>6} | {'Sources':>7} | "
        f"{'Depth':<10} | {'Frameworks':>10} | "
        f"{'Contrarian':>10} | {'Time':>6}"
    )
    separator = "-" * len(header)
    rows = [separator, header, separator]

    for ev in sorted(evaluations, key=lambda e: e.layer):
        row = (
            f"Layer {ev.layer:<4} | {ev.word_count:>6} | {ev.source_diversity:>7} | "
            f"{ev.insight_depth:<10} | {len(ev.framework_usage):>10} | "
            f"{ev.contrarian_views:>10} | {ev.elapsed_seconds:>5.1f}s"
        )
        rows.append(row)

    rows.append(separator)
    return "\n".join(rows)


def format_score_table(evaluations: list[LayerEvaluation]) -> str:
    """Format raw LLM evaluation scores as an ASCII table."""
    header = f"{'Dimension':<20} | " + " | ".join(f"L{ev.layer:>1}" for ev in sorted(evaluations, key=lambda e: e.layer))
    separator = "-" * len(header)
    rows = [separator, header, separator]

    sorted_evals = sorted(evaluations, key=lambda e: e.layer)
    for dim in DIMS:
        scores = []
        for ev in sorted_evals:
            raw = getattr(ev, "_raw_scores", {})
            info = raw.get(dim, {})
            score = info.get("score", "?") if isinstance(info, dict) else "?"
            scores.append(f"{score:>2}")
        row = f"{dim:<20} | " + " | ".join(scores)
        rows.append(row)

    rows.append(separator)

    # Add total row
    totals = []
    for ev in sorted_evals:
        raw = getattr(ev, "_raw_scores", {})
        total = sum(
            info.get("score", 0) if isinstance(info, dict) else 0
            for info in (raw.get(d, {}) for d in DIMS)
        )
        totals.append(f"{total:>2}")
    rows.append(f"{'TOTAL (/60)':<20} | " + " | ".join(totals))
    rows.append(separator)

    return "\n".join(rows)
