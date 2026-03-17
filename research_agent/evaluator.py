"""
Evaluation & Comparison framework for multi-layer research outputs.

Uses LLM to evaluate all layers COMPARATIVELY in a single call on 7 dimensions,
then generates pairwise content-based comparisons showing exactly WHY each layer
improves over the previous one — with specific evidence from the actual reports.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from config import get_llm
from research_agent.models import (
    ResearchResult, LayerEvaluation, LayerComparison, ComparisonReport,
)
from research_agent.prompts import (
    EVALUATION_PROMPT,
    COMPARATIVE_EVALUATION_PROMPT,
    LAYER_COMPARISON_PROMPT,
    EXECUTIVE_COMPARISON_SUMMARY,
)
from research_agent.utils import extract_json_scores, get_content
from research_agent.cost import track

logger = logging.getLogger(__name__)

LAYER_NAMES = {
    0: "Baseline (no research)",
    1: "Enhanced (web search + synthesis)",
    2: "CMI Expert (full pipeline: plan + research + verify + write)",
}

DIMS = [
    "factual_density", "source_grounding", "analytical_depth",
    "specificity", "insight_quality", "completeness", "structure_quality",
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

    # Build the layers content block — 20k chars per layer to avoid truncation
    layers_parts = []
    for r in sorted_results:
        name = LAYER_NAMES.get(r.layer, f"Layer {r.layer}")
        layers_parts.append(
            f"--- LAYER {r.layer}: {name} ({r.word_count} words, "
            f"{len(r.sources)} sources) ---\n{r.content[:20000]}"
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
        response = await llm.ainvoke(messages)
        track("Eval comparative", response)
        text = get_content(response).strip()

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
        response = await llm.ainvoke(messages)
        track(f"Eval L{result.layer}", response)
        text = get_content(response).strip()
        scores = extract_json_scores(text)
        if not scores:
            logger.warning(f"[Evaluator] No scores extracted for Layer {result.layer}")
    except Exception as e:
        logger.warning(f"[Evaluator] Evaluation failed for Layer {result.layer}: {e}")
        scores = {}

    return _build_layer_evaluation(result, scores)


def _get_avg_score(ev: LayerEvaluation) -> float:
    """Calculate average score across all dimensions for a LayerEvaluation."""
    raw = getattr(ev, "_raw_scores", {})
    scores = []
    for dim in DIMS:
        info = raw.get(dim, {})
        if isinstance(info, dict):
            s = info.get("score", 0)
            if s:
                scores.append(float(s))
    return sum(scores) / len(scores) if scores else 0.0


def _format_scores_for_prompt(ev: LayerEvaluation) -> str:
    """Format evaluation scores as a readable string for the comparison prompt."""
    raw = getattr(ev, "_raw_scores", {})
    parts = []
    for dim in DIMS:
        info = raw.get(dim, {})
        if isinstance(info, dict):
            parts.append(f"{dim}: {info.get('score', '?')}/10")
        else:
            parts.append(f"{dim}: {info}")
    return ", ".join(parts)


async def _compare_pair(
    r_from: ResearchResult,
    r_to: ResearchResult,
    evaluations: list[LayerEvaluation],
) -> LayerComparison:
    """Compare two adjacent layers using LLM with full content analysis."""
    from_ev = next((e for e in evaluations if e.layer == r_from.layer),
                   LayerEvaluation(layer=r_from.layer))
    to_ev = next((e for e in evaluations if e.layer == r_to.layer),
                 LayerEvaluation(layer=r_to.layer))

    score_delta = _get_avg_score(to_ev) - _get_avg_score(from_ev)

    llm = get_llm("reviewer")
    messages = [
        {"role": "system", "content": "You are a research quality analyst. Return ONLY valid JSON."},
        {"role": "user", "content": LAYER_COMPARISON_PROMPT.format(
            topic=r_from.topic,
            from_layer=r_from.layer,
            from_name=LAYER_NAMES.get(r_from.layer, f"Layer {r_from.layer}"),
            from_words=r_from.word_count,
            from_sources=len(r_from.sources),
            from_content=r_from.content[:15000],
            from_scores=_format_scores_for_prompt(from_ev),
            to_layer=r_to.layer,
            to_name=LAYER_NAMES.get(r_to.layer, f"Layer {r_to.layer}"),
            to_words=r_to.word_count,
            to_sources=len(r_to.sources),
            to_content=r_to.content[:15000],
            to_scores=_format_scores_for_prompt(to_ev),
        )},
    ]

    try:
        response = await llm.ainvoke(messages)
        track(f"Eval compare L{r_from.layer}→L{r_to.layer}", response)
        text = get_content(response).strip()
        parsed = extract_json_scores(text)

        improvements = parsed.get("improvements", []) if parsed else []
        if not isinstance(improvements, list):
            improvements = []

        return LayerComparison(
            from_layer=r_from.layer,
            to_layer=r_to.layer,
            improvements=improvements[:5],
            score_delta=round(score_delta, 1),
            key_evidence=parsed.get("key_evidence", "") if parsed else "",
            overall_verdict=parsed.get("overall_verdict", "") if parsed else "",
        )
    except Exception as e:
        logger.error(f"[Evaluator] Pair comparison L{r_from.layer}→L{r_to.layer} failed: {e}")
        return LayerComparison(
            from_layer=r_from.layer,
            to_layer=r_to.layer,
            score_delta=round(score_delta, 1),
        )


async def compare_layers(
    results: list[ResearchResult],
    evaluations: list[LayerEvaluation],
) -> ComparisonReport:
    """Generate pairwise content-based comparisons + executive summary.

    For each adjacent layer pair (L0→L1, L1→L2), analyzes the actual report
    content to identify 4-5 specific improvements with evidence. Then generates
    an executive summary from the structured comparison data.
    """
    if not results:
        return ComparisonReport(topic="", summary="No results to compare.")

    topic = results[0].topic
    sorted_results = sorted(results, key=lambda r: r.layer)

    # 1. Run pairwise content comparisons in parallel
    pairs = list(zip(sorted_results[:-1], sorted_results[1:]))
    if pairs:
        comparison_tasks = [_compare_pair(r1, r2, evaluations) for r1, r2 in pairs]
        layer_comparisons = await asyncio.gather(*comparison_tasks)
    else:
        layer_comparisons = []

    logger.info(f"[Evaluator] Completed {len(layer_comparisons)} pairwise comparisons")

    # 2. Generate executive summary from structured comparison data
    pairwise_parts = []
    for lc in layer_comparisons:
        from_name = LAYER_NAMES.get(lc.from_layer, f"Layer {lc.from_layer}")
        to_name = LAYER_NAMES.get(lc.to_layer, f"Layer {lc.to_layer}")
        part = f"**Layer {lc.from_layer} ({from_name}) → Layer {lc.to_layer} ({to_name}):**\n"
        part += f"Score improvement: +{lc.score_delta:.1f}/10\n"
        part += f"Verdict: {lc.overall_verdict}\n"
        part += "Improvements:\n"
        for i, imp in enumerate(lc.improvements, 1):
            part += f"  {i}. {imp}\n"
        if lc.key_evidence:
            part += f"Key evidence: {lc.key_evidence[:300]}\n"
        pairwise_parts.append(part)

    score_parts = []
    for ev in sorted(evaluations, key=lambda e: e.layer):
        name = LAYER_NAMES.get(ev.layer, f"Layer {ev.layer}")
        avg = _get_avg_score(ev)
        score_parts.append(f"Layer {ev.layer} ({name}): {avg:.1f}/10 avg, "
                          f"{ev.word_count} words, {ev.source_diversity} sources")

    llm = get_llm("analyst")
    messages = [
        {"role": "system", "content": "You are a research quality analyst."},
        {"role": "user", "content": EXECUTIVE_COMPARISON_SUMMARY.format(
            topic=topic,
            pairwise_summaries="\n\n".join(pairwise_parts),
            score_summary="\n".join(score_parts),
        )},
    ]

    try:
        response = await llm.ainvoke(messages)
        track("Eval summary", response)
        summary = get_content(response).strip()
    except Exception as e:
        logger.error(f"[Evaluator] Executive summary failed: {e}")
        summary = f"Error generating summary: {e}"

    return ComparisonReport(
        topic=topic,
        results=results,
        evaluations=evaluations,
        summary=summary,
        layer_comparisons=list(layer_comparisons),
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
