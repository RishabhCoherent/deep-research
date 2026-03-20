"""
Layer 0 — BASELINE: Best model, single prompt, no tools.

Produces a report purely from the model's training data.
Uses the best available model for maximum quality from knowledge alone.
"""

from __future__ import annotations

import json
import logging
import time

from config import get_llm, set_model_tier
from research_agent.models import ResearchResult
from research_agent.cost import track
from research_agent.utils import get_content, generate_report_outline, parse_outline_sections, parse_outline_type
from research_agent.prompts import BASELINE_SECTION_PLANNER_PROMPT, BASELINE_WRITE_PROMPT, get_quality_rules
from research_agent.graph import _scrub_competitor_mentions

logger = logging.getLogger(__name__)


async def run(
    topic: str,
    progress_callback=None,
    brief: str = "",
) -> ResearchResult:
    """Generate a baseline report from a single LLM prompt using the best model."""
    start = time.time()

    def notify(status: str, msg: str):
        if progress_callback:
            progress_callback(0, status, msg)
        logger.info(f"[Baseline] {status}: {msg}")

    notify("start", "Generating baseline report from model knowledge...")

    # Generate outline for section structure (cheap model)
    set_model_tier("budget")
    outline_llm = get_llm("planner")
    outline = await generate_report_outline(topic, outline_llm, brief=brief)

    # Use best model for the actual report
    set_model_tier("premium")
    llm = get_llm("writer")

    try:
        section_names = parse_outline_sections(outline) if outline else []

        if not section_names:
            # Fallback: plan sections independently
            plan_messages = [
                {"role": "system", "content": "You output only valid JSON arrays. No explanation."},
                {"role": "user", "content": BASELINE_SECTION_PLANNER_PROMPT.format(topic=topic)},
            ]
            plan_response = await llm.ainvoke(plan_messages)
            track("L0 plan", plan_response)

            raw = get_content(plan_response).strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            try:
                section_names = json.loads(raw)
            except json.JSONDecodeError:
                section_names = ["Market Overview", "Key Players", "Trends", "Challenges", "Outlook"]

        section_list = "\n".join(f"## {s}" for s in section_names)
        notify("planning", f"Planned {len(section_names)} sections")

        # Write report using best model
        report_type = parse_outline_type(outline) if outline else ""
        topic_rules = get_quality_rules(report_type)

        brief_instruction = ""
        if brief:
            brief_instruction = (
                f"\n\nCLIENT BRIEF (follow these instructions carefully — they define the scope, "
                f"structure, and focus of this report):\n\n{brief}\n"
            )

        from datetime import datetime
        current_date = datetime.now().strftime("%B %Y")
        current_year = datetime.now().year

        write_messages = [
            {"role": "system", "content": (
                f"You are a business research analyst. Today is {current_date}. "
                f"Write from a {current_year} perspective — events from {current_year - 1} and earlier "
                f"use PAST TENSE. Write a clear, direct report using ONLY "
                f"your existing knowledge. Be opinionated — state conclusions clearly. "
                f"Use simple language, short sentences, and bullet points where appropriate."
            )},
            {"role": "user", "content": BASELINE_WRITE_PROMPT.format(
                topic=topic, sections=section_list, topic_rules=topic_rules
            ) + brief_instruction},
        ]
        response = await llm.ainvoke(write_messages)
        track("L0 baseline", response)
        content = get_content(response).strip()
        content = _scrub_competitor_mentions(content)
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
