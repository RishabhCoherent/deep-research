"""
Layer 1 — ENHANCEMENT: LangGraph agent enriches baseline report with web data.

Receives Layer 0's report and improves it by:
- Searching the web for current data, trends, and insights
- Scraping promising pages for detailed statistics
- Rewriting sections with sourced, verified information
"""

from __future__ import annotations

import logging
import time

from config import get_llm, set_model_tier
from research_agent.models import ResearchResult, Source, AgentContext
from research_agent.graph import build_agent_graph, build_initial_state, make_tools
from research_agent.prompts import L1_ENHANCEMENT_PROMPT

logger = logging.getLogger(__name__)


async def run(
    topic: str,
    progress_callback=None,
    prior_report: str = "",
    prior_sources: list[Source] | None = None,
    brief: str = "",
) -> ResearchResult:
    """Run Layer 1: enhance baseline report with web research via LangGraph agent."""
    start = time.time()

    def notify(status: str, msg: str):
        if progress_callback:
            progress_callback(1, status, msg)
        logger.info(f"[Enhanced] {status}: {msg}")

    notify("start", "Starting enhanced research with web search...")

    set_model_tier("standard")
    llm = get_llm("writer")

    # Create agent context for tool closures
    ctx = AgentContext(max_tool_calls=25)

    # Seed with prior sources
    if prior_sources:
        for s in prior_sources:
            ctx.sources.append(s)
            ctx.urls_seen.add(s.url)

    # Build tools and graph
    tools = make_tools(ctx)
    graph = build_agent_graph(
        llm=llm,
        tools=tools,
        system_prompt=L1_ENHANCEMENT_PROMPT,
        max_tool_calls=35,
        min_word_count=1200,
        max_retries=3,
        progress_callback=progress_callback,
        layer=1,
        ctx=ctx,
    )

    # Build initial state
    initial_state = build_initial_state(
        topic=topic,
        layer=1,
        system_prompt=L1_ENHANCEMENT_PROMPT,
        prior_report=prior_report,
        brief=brief,
        max_tool_calls=35,
        min_word_count=1200,
        max_retries=3,
    )

    # Run the graph
    final_state = await graph.ainvoke(initial_state)

    draft = final_state.get("draft", "")
    if not draft:
        # Fallback: try to extract from last message
        for msg in reversed(final_state.get("messages", [])):
            if hasattr(msg, "content") and msg.content and len(str(msg.content)) > 200:
                from research_agent.utils import strip_preamble
                draft = strip_preamble(str(msg.content).strip())
                break
        if not draft:
            draft = "## Error\n\nEnhanced agent did not produce output."

    elapsed = time.time() - start

    # Build iteration_history for frontend — include ALL tool calls
    searches = [tc for tc in ctx.tool_calls_log if tc.get("tool") == "search_web"]
    scrapes = [tc for tc in ctx.tool_calls_log if tc.get("tool") == "scrape_page"]
    sources_inherited = len(prior_sources) if prior_sources else 0
    sources_new = len(ctx.sources) - sources_inherited

    iteration_history = [{
        "iteration": 0,
        "score": 0,
        "weaknesses": [],
        "queries": ctx.tool_calls_log,  # All tool calls (searches + scrapes)
        "stop_reason": "complete",
    }]

    notify("done", f"Enhanced complete: {len(draft.split())} words, "
                    f"{len(ctx.sources)} sources in {elapsed:.1f}s")

    return ResearchResult(
        layer=1,
        topic=topic,
        content=draft,
        sources=ctx.sources,
        metadata={
            "method": "langgraph_enhancement",
            "iterations": 1,
            "final_score": 0,
            "tool_calls": ctx.tool_call_count,
            "sources_found": len(ctx.sources),
            "sources_scraped": sum(1 for s in ctx.sources if s.scraped_content),
            "searches_count": len(searches),
            "scrapes_count": len(scrapes),
            "sources_inherited": sources_inherited,
            "sources_new": sources_new,
            "iteration_history": iteration_history,
        },
        elapsed_seconds=elapsed,
    )
