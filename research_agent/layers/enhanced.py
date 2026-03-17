"""
Layer 1 — ENHANCED: Web search + synthesis, no verification pipeline.

Uses the ReAct agent with search/scrape tools to gather real data,
then writes a report. No formal research plan, no fact verification,
no multi-phase pipeline. A solid middle ground.
"""

from __future__ import annotations

import logging
import time
from config import get_llm, set_model_tier
from research_agent.models import ResearchResult, AgentContext
from research_agent.react_engine import run_react_agent, parse_outline_type
from research_agent.prompts import ENHANCED_SYSTEM_PROMPT, LAYER1_SELF_REVIEW, get_quality_rules

logger = logging.getLogger(__name__)


async def run(
    topic: str,
    progress_callback=None,
    outline: str = "",
) -> ResearchResult:
    """Run enhanced research: search + synthesize via ReAct agent."""
    start = time.time()

    def notify(status: str, msg: str):
        if progress_callback:
            progress_callback(1, status, msg)
        logger.info(f"[Enhanced] {status}: {msg}")

    notify("start", "Starting enhanced research with web search...")

    set_model_tier("standard")
    llm = get_llm("writer")
    eval_llm = get_llm("reviewer")

    ctx = AgentContext(max_tool_calls=25)

    report_type = parse_outline_type(outline) if outline else ""
    topic_rules = get_quality_rules(report_type)

    draft, sources, iterations = await run_react_agent(
        topic=topic,
        layer=1,
        system_prompt=ENHANCED_SYSTEM_PROMPT,
        llm=llm,
        ctx=ctx,
        eval_prompt_template=LAYER1_SELF_REVIEW,
        eval_llm=eval_llm,
        max_iterations=3,
        convergence_threshold=7.5,
        max_steps_per_iteration=20,
        progress_callback=progress_callback,
        outline=outline,
        topic_rules=topic_rules,
    )

    elapsed = time.time() - start

    # Build iteration_history for frontend
    iteration_history = []
    for it in iterations:
        iteration_history.append({
            "iteration": it.iteration,
            "score": round(it.eval_score, 1),
            "weaknesses": it.weaknesses[:3],
            "queries": it.queries_run,
            "stop_reason": it.stop_reason,
        })

    notify("done", f"Enhanced complete: {len(draft.split())} words, "
                    f"{len(sources)} sources in {elapsed:.1f}s")

    return ResearchResult(
        layer=1,
        topic=topic,
        content=draft,
        sources=sources,
        metadata={
            "method": "enhanced_search",
            "iterations": len(iterations),
            "final_score": round(iterations[-1].eval_score, 1) if iterations else 0,
            "tool_calls": ctx.tool_call_count,
            "sources_found": len(sources),
            "sources_scraped": sum(1 for s in sources if s.scraped_content),
            "iteration_history": iteration_history,
        },
        elapsed_seconds=elapsed,
    )
