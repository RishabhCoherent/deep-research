"""
Layer 3 — Expert Agent (ReAct): autonomous strategic analyst.

Challenges assumptions, finds contrarian evidence, identifies second-order effects,
and draws cross-industry parallels. Produces C-suite-ready strategic analysis.
Evaluated by a simulated Fortune 500 CEO.
"""

from __future__ import annotations

import logging
import time

from config import get_llm
from research_agent.types import ResearchResult
from research_agent.prompts import LAYER3_AGENT_SYSTEM, LAYER3_CSUITE_REVIEW
from research_agent.agent_loop import run_react_agent, AgentContext

logger = logging.getLogger(__name__)


async def run(topic: str, layer2_result: ResearchResult, progress_callback=None) -> ResearchResult:
    """Run Layer 3: ReAct expert agent with assumption challenging."""
    logger.info(f"[Layer 3] ReAct expert agent starting for: {topic}")
    start = time.time()

    ctx = AgentContext(
        max_tool_calls=20,
        prior_content=layer2_result.content,
        existing_sources=list(layer2_result.sources),
    )
    # Pre-populate with L2 sources
    ctx.sources = list(layer2_result.sources)
    ctx.urls_seen = {s.url for s in layer2_result.sources}

    llm = get_llm("writer")
    eval_llm = get_llm("reviewer")

    draft, sources, iterations = await run_react_agent(
        topic=topic,
        layer=3,
        system_prompt=LAYER3_AGENT_SYSTEM,
        llm=llm,
        ctx=ctx,
        eval_prompt_template=LAYER3_CSUITE_REVIEW,
        eval_llm=eval_llm,
        max_iterations=3,
        convergence_threshold=8.0,
        progress_callback=progress_callback,
    )

    elapsed = time.time() - start
    final_score = iterations[-1].eval_score if iterations else 0
    total_tool_calls = len(ctx.tool_calls_log)

    logger.info(f"[Layer 3] Done in {elapsed:.1f}s — {len(draft.split())} words, "
                f"{len(sources)} sources, {len(iterations)} iters, "
                f"{total_tool_calls} tool calls, score: {final_score:.1f}/10")

    return ResearchResult(
        layer=3,
        topic=topic,
        content=draft,
        sources=sources,
        metadata={
            "method": "react_agent",
            "iterations": len(iterations),
            "final_score": final_score,
            "tool_calls": total_tool_calls,
            "iteration_history": [
                {"iteration": it.iteration, "score": it.eval_score,
                 "weaknesses": it.weaknesses, "queries": it.queries_run}
                for it in iterations
            ],
            "sources_found": len(sources),
            "sources_scraped": sum(1 for s in sources if s.scraped_content),
        },
        elapsed_seconds=elapsed,
    )
