"""
Layer 1 — Research Agent (ReAct): autonomous tool-calling agent.

The agent searches the web, scrapes pages, and assesses source credibility
autonomously, then writes a source-grounded market research report.
An external evaluator scores the output and sends feedback if it's not
good enough, triggering another round of research.
"""

from __future__ import annotations

import logging
import time

from config import get_llm
from research_agent.types import ResearchResult
from research_agent.prompts import LAYER1_AGENT_SYSTEM, LAYER1_SELF_REVIEW
from research_agent.agent_loop import run_react_agent, AgentContext

logger = logging.getLogger(__name__)


async def run(topic: str, progress_callback=None) -> ResearchResult:
    """Run Layer 1: ReAct research agent with autonomous tool calling."""
    logger.info(f"[Layer 1] ReAct research agent starting for: {topic}")
    start = time.time()

    ctx = AgentContext(max_tool_calls=20)
    llm = get_llm("writer")
    eval_llm = get_llm("reviewer")

    draft, sources, iterations = await run_react_agent(
        topic=topic,
        layer=1,
        system_prompt=LAYER1_AGENT_SYSTEM,
        llm=llm,
        ctx=ctx,
        eval_prompt_template=LAYER1_SELF_REVIEW,
        eval_llm=eval_llm,
        max_iterations=3,
        convergence_threshold=7.0,
        progress_callback=progress_callback,
    )

    elapsed = time.time() - start
    final_score = iterations[-1].eval_score if iterations else 0
    total_tool_calls = len(ctx.tool_calls_log)

    logger.info(f"[Layer 1] Done in {elapsed:.1f}s — {len(draft.split())} words, "
                f"{len(sources)} sources, {len(iterations)} iters, "
                f"{total_tool_calls} tool calls, score: {final_score:.1f}/10")

    return ResearchResult(
        layer=1,
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
