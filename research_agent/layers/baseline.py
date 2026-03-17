"""
Layer 0 — BASELINE: Single LLM prompt, no tools, no research.

Produces a report purely from the model's training data.
This is the control group to show what research adds.
"""

from __future__ import annotations

import logging
import time

from config import get_llm, set_model_tier
from research_agent.models import ResearchResult
from research_agent.cost import track
from research_agent.utils import get_content
from research_agent.react_engine import parse_outline_sections, parse_outline_type
from research_agent.prompts import BASELINE_SECTION_PLANNER_PROMPT, BASELINE_WRITE_PROMPT, get_quality_rules

logger = logging.getLogger(__name__)


async def run(
    topic: str,
    progress_callback=None,
    outline: str = "",
) -> ResearchResult:
    """Generate a baseline report from a single LLM prompt."""
    start = time.time()

    def notify(status: str, msg: str):
        if progress_callback:
            progress_callback(0, status, msg)
        logger.info(f"[Baseline] {status}: {msg}")

    notify("start", "Generating baseline report from model knowledge...")

    set_model_tier("budget")
    llm = get_llm("writer")

    try:
        # Use shared outline sections if available, otherwise plan our own
        section_names = parse_outline_sections(outline) if outline else []

        if not section_names:
            # Fallback: plan sections independently (cheap, ~50 tokens out)
            plan_messages = [
                {"role": "system", "content": "You output only valid JSON arrays. No explanation."},
                {"role": "user", "content": BASELINE_SECTION_PLANNER_PROMPT.format(topic=topic)},
            ]
            plan_response = await llm.ainvoke(plan_messages)
            track("L0 baseline", plan_response)

            import json
            raw = get_content(plan_response).strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            try:
                section_names = json.loads(raw)
            except json.JSONDecodeError:
                section_names = ["Market Overview", "Key Players", "Trends", "Challenges", "Outlook"]

        section_list = "\n".join(f"## {s}" for s in section_names)
        notify("planning", f"Planned {len(section_names)} sections")

        # Step 2: Write report using exactly those sections
        report_type = parse_outline_type(outline) if outline else ""
        topic_rules = get_quality_rules(report_type)

        write_messages = [
            {"role": "system", "content": (
                "You are a market research analyst. Write directly using ONLY the "
                "section headings provided. Do NOT add, remove, rename, or reorder any sections. "
                "All layers must produce identical section headings for cross-layer comparison."
            )},
            {"role": "user", "content": BASELINE_WRITE_PROMPT.format(
                topic=topic, sections=section_list, topic_rules=topic_rules
            )},
        ]
        response = await llm.ainvoke(write_messages)
        track("L0 baseline", response)
        content = get_content(response).strip()
    except Exception as e:
        logger.error(f"[Baseline] Failed: {e}")
        content = f"## Error\n\nBaseline generation failed: {e}"

    elapsed = time.time() - start
    word_count = len(content.split())

    notify("done", f"Baseline complete: {word_count} words in {elapsed:.1f}s")

    return ResearchResult(
        layer=0,
        topic=topic,
        content=content,
        sources=[],
        metadata={
            "method": "single_prompt",
            "iterations": 0,
            "final_score": 0,
            "tool_calls": 0,
            "sources_found": 0,
            "sources_scraped": 0,
            "iteration_history": [],
        },
        elapsed_seconds=elapsed,
    )
