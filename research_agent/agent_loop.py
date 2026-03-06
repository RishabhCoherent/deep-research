"""
ReAct Agent Loop: LLM autonomously calls tools, then evaluator scores output.

Architecture:
  OUTER LOOP (evaluation):
    for iteration in range(max_iterations):
      INNER LOOP (ReAct tool-calling):
        while steps < max_steps:
          response = llm.bind_tools(tools).ainvoke(messages)
          if tool_calls → execute, append results
          else → content is the final report → break

      evaluator scores draft
      if score >= threshold → done
      else → feedback appended, agent continues with full context
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Callable
from urllib.parse import urlparse

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, ToolMessage, SystemMessage

from research_agent.types import Source
from research_agent.cost import track
from research_agent.utils import extract_json
from tools.search import search
from tools.scraper import scrape_url
from tools.source_classifier import get_source_tier

logger = logging.getLogger(__name__)


# ─── Data classes (used by runner.py + metadata) ─────────────────────────────


@dataclass
class EvalResult:
    """Self-evaluation output from the reviewer."""
    overall_score: float  # 0.0 - 10.0
    dimension_scores: dict = field(default_factory=dict)
    weaknesses: list[str] = field(default_factory=list)
    suggested_queries: list[str] = field(default_factory=list)

    @property
    def pass_threshold(self) -> bool:
        return self._threshold_met

    def check_threshold(self, threshold: float) -> bool:
        self._threshold_met = self.overall_score >= threshold
        return self._threshold_met


@dataclass
class AgentIteration:
    """Record of one iteration for metadata/debugging."""
    iteration: int
    eval_score: float
    weaknesses: list[str]
    queries_run: list[str]
    new_sources_count: int


# ─── Agent Context (shared mutable state for tools) ─────────────────────────


@dataclass
class AgentContext:
    """Shared state passed to tools via closures."""
    sources: list[Source] = field(default_factory=list)
    urls_seen: set[str] = field(default_factory=set)
    tool_calls_log: list[dict] = field(default_factory=list)
    tool_call_count: int = 0
    max_tool_calls: int = 20
    prior_content: str = ""
    existing_sources: list[Source] = field(default_factory=list)


# ─── Shared utility ─────────────────────────────────────────────────────────


def _infer_publisher(url: str) -> str:
    """Extract publisher name from URL domain."""
    try:
        host = urlparse(url).hostname or ""
        host = host.replace("www.", "")
        return host.split(".")[0].capitalize() if host else "Unknown"
    except Exception:
        return "Unknown"


# ─── Tool factory ───────────────────────────────────────────────────────────


def make_tools(ctx: AgentContext) -> list:
    """Create LangChain tools with closures over shared AgentContext."""

    @tool
    async def search_web(query: str) -> str:
        """Search the web for market research data. Returns titles, URLs, and snippets
        from top results. Use targeted queries with specific terms and the current year."""
        if ctx.tool_call_count >= ctx.max_tool_calls:
            return "BUDGET EXCEEDED. Write your final report now with the data you have."
        ctx.tool_call_count += 1

        try:
            results = await search(query, max_results=5, include_news=True)
        except Exception as e:
            return f"Search failed: {e}. Try a different query."

        if not results:
            return "No results found. Try a different query."

        parts = []
        new_count = 0
        for r in results:
            url = r.get("url", "")
            if not url:
                continue
            title = r.get("title", "")
            snippet = r.get("snippet", "")

            if url not in ctx.urls_seen:
                ctx.urls_seen.add(url)
                ctx.sources.append(Source(
                    url=url, title=title, snippet=snippet,
                    publisher=_infer_publisher(url),
                    date=r.get("date", ""),
                    tier=get_source_tier(url),
                ))
                new_count += 1

            tier = get_source_tier(url)
            tier_label = {1: "T1", 2: "T2", 3: "T3"}[tier]
            parts.append(f"[{tier_label}] {title}\n  {snippet[:200]}")

        ctx.tool_calls_log.append({
            "tool": "search_web", "query": query, "results": len(results),
        })
        return f"{len(results)} results ({new_count} new):\n\n" + "\n\n".join(parts)

    @tool
    async def scrape_page(url: str) -> str:
        """Scrape full text content from a web page. Use on the most promising search
        results to get detailed data, tables, or analysis."""
        if ctx.tool_call_count >= ctx.max_tool_calls:
            return "BUDGET EXCEEDED. Write your final report now."
        ctx.tool_call_count += 1

        try:
            page = await scrape_url(url)
        except Exception as e:
            return f"Scrape failed: {e}"

        if not page or not page.get("content"):
            return "Could not extract content (paywall or JS required)."

        content = page["content"][:3000]

        # Update existing source or create new one
        for s in ctx.sources:
            if s.url == url:
                s.scraped_content = page["content"][:5000]
                break
        else:
            if url not in ctx.urls_seen:
                ctx.urls_seen.add(url)
                ctx.sources.append(Source(
                    url=url, title=page.get("title", ""),
                    snippet=content[:200],
                    scraped_content=page["content"][:5000],
                    publisher=_infer_publisher(url),
                    tier=get_source_tier(url),
                ))

        ctx.tool_calls_log.append({"tool": "scrape_page", "url": url})
        tier_label = {1: "T1", 2: "T2", 3: "T3"}[get_source_tier(url)]
        return f"[{tier_label}] Content from {_infer_publisher(url)} ({len(content)} chars):\n\n{content}"

    @tool
    async def assess_source(url: str) -> str:
        """Check credibility tier of a source URL. Returns T1 (gold-standard),
        T2 (reliable), or T3 (unverified). Use before citing data from unknown sources."""
        tier = get_source_tier(url)
        labels = {
            1: "TIER-1 HIGH-CREDIBILITY. Prefer this data when numbers conflict.",
            2: "TIER-2 RELIABLE. Generally trustworthy.",
            3: "TIER-3 UNVERIFIED. Cross-check against T1/T2 sources.",
        }
        return f"{_infer_publisher(url)}: {labels[tier]}"

    return [search_web, scrape_page, assess_source]


# ─── Evaluation helpers ─────────────────────────────────────────────────────


async def _evaluate_draft(draft, topic, eval_prompt, eval_llm, layer):
    """Score a draft using the evaluator LLM."""
    messages = [
        {"role": "system", "content": "You are a demanding reviewer. Return valid JSON only."},
        {"role": "user", "content": eval_prompt.format(topic=topic, draft=draft)},
    ]
    try:
        response = eval_llm.invoke(messages)
        track(f"L{layer} eval", response)
        result = extract_json(response.content.strip())
        if isinstance(result, dict):
            return EvalResult(
                overall_score=float(result.get("overall", 5.0)),
                dimension_scores=result.get("scores", {}),
                weaknesses=result.get("weaknesses", []),
                suggested_queries=result.get("suggested_queries", []),
            )
    except Exception as e:
        logger.warning(f"[Agent L{layer}] Eval failed: {e}")
    return EvalResult(overall_score=5.0, weaknesses=["Evaluation failed"])


def _format_feedback(eval_result: EvalResult) -> str:
    """Format evaluator feedback for the agent to continue from."""
    parts = [
        f"EVALUATOR FEEDBACK (score: {eval_result.overall_score:.1f}/10):",
        "Your report needs improvement:",
    ]
    for i, w in enumerate(eval_result.weaknesses, 1):
        parts.append(f"{i}. {w}")
    if eval_result.suggested_queries:
        parts.append("\nSuggested research queries:")
        for q in eval_result.suggested_queries:
            parts.append(f"  - {q}")
    parts.append("\nUse your tools to research these gaps, then write an IMPROVED report "
                 "that retains all correct data and fixes the weaknesses.")
    return "\n".join(parts)


# ─── Main ReAct Engine ──────────────────────────────────────────────────────


ProgressFn = Optional[Callable[[int, str, str], None]]


async def run_react_agent(
    topic: str,
    layer: int,
    system_prompt: str,
    llm,
    ctx: AgentContext,
    eval_prompt_template: str,
    eval_llm,
    max_iterations: int = 3,
    convergence_threshold: float = 7.0,
    max_steps_per_iteration: int = 25,
    extra_tools: list | None = None,
    progress_callback: ProgressFn = None,
) -> tuple[str, list[Source], list[AgentIteration]]:
    """
    Run the ReAct agent: inner tool-calling loop + outer evaluation loop.

    Returns (final_draft, all_sources, iteration_history).
    """
    iterations: list[AgentIteration] = []

    def notify(status: str, msg: str):
        if progress_callback:
            progress_callback(layer, status, msg)
        logger.info(f"[Agent L{layer}] {status}: {msg}")

    # Build tools and bind to LLM
    tools = make_tools(ctx)
    if extra_tools:
        tools.extend(extra_tools)
    tool_map = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)

    # Initial message
    initial = f"Research topic: {topic}\nCurrent year: 2026"
    if ctx.prior_content:
        initial += (f"\n\nPrior layer analysis (RETAIN all verified data, CORRECT errors):"
                    f"\n{ctx.prior_content}")
    if ctx.existing_sources:
        initial += f"\n\n{len(ctx.existing_sources)} sources already tracked from previous layer."

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=initial),
    ]

    draft = ""

    for iteration in range(max_iterations):
        notify("researching", f"Iteration {iteration + 1}/{max_iterations}: agent working...")

        # Reset per-iteration counters
        ctx.tool_call_count = 0
        log_start = len(ctx.tool_calls_log)
        sources_start = len(ctx.sources)

        # ── Inner ReAct loop ──────────────────────────────────────────
        for step in range(max_steps_per_iteration):
            try:
                response = await llm_with_tools.ainvoke(messages)
                track(f"L{layer} react", response)
            except Exception as e:
                logger.error(f"[Agent L{layer}] LLM call failed: {e}")
                messages.append(HumanMessage(
                    content=f"Error occurred: {e}. Write your report with available data."
                ))
                continue

            messages.append(response)

            # No tool calls → agent produced its final output
            if not response.tool_calls:
                if response.content and len(response.content.strip()) > 100:
                    draft = response.content.strip()
                    notify("drafted", f"Iter {iteration + 1}: "
                           f"{len(draft.split())} words")
                break

            # Execute tool calls
            for tc in response.tool_calls:
                name = tc["name"]
                args = tc["args"]
                tid = tc["id"]

                if name in tool_map:
                    try:
                        result = await tool_map[name].ainvoke(args)
                    except Exception as e:
                        result = f"Tool error: {e}"
                        logger.warning(f"[Agent L{layer}] Tool {name} failed: {e}")
                else:
                    result = f"Unknown tool: {name}"

                messages.append(ToolMessage(content=str(result), tool_call_id=tid))

            # Nudge if tool budget exhausted
            if ctx.tool_call_count >= ctx.max_tool_calls:
                messages.append(HumanMessage(
                    content="Tool budget exhausted. Write your final report NOW "
                            "using all the data you have gathered."
                ))

        # Force output if agent didn't produce a report
        if not draft or len(draft.strip()) < 100:
            notify("forcing", "Agent didn't produce output, requesting report...")
            messages.append(HumanMessage(
                content="Write your final comprehensive report NOW using all gathered "
                        "data. Do not call any more tools — just write the report."
            ))
            try:
                # Call WITHOUT tools bound so it can't make tool calls
                response = await llm.ainvoke(messages)
                track(f"L{layer} forced", response)
                messages.append(response)
                if response.content:
                    draft = response.content.strip()
            except Exception as e:
                logger.error(f"[Agent L{layer}] Forced draft failed: {e}")
                draft = f"Error generating report: {e}"

        # ── Outer evaluation ──────────────────────────────────────────
        notify("evaluating", f"Iter {iteration + 1}: evaluating draft...")
        eval_result = await _evaluate_draft(
            draft, topic, eval_prompt_template, eval_llm, layer
        )
        eval_result.check_threshold(convergence_threshold)

        # Track per-iteration metrics
        new_logs = ctx.tool_calls_log[log_start:]
        queries = [l["query"] for l in new_logs if l.get("tool") == "search_web"]

        iterations.append(AgentIteration(
            iteration=iteration,
            eval_score=eval_result.overall_score,
            weaknesses=eval_result.weaknesses,
            queries_run=queries,
            new_sources_count=len(ctx.sources) - sources_start,
        ))

        notify("eval_done",
               f"Iter {iteration + 1}: {eval_result.overall_score:.1f}/10"
               f"{' — converged!' if eval_result.pass_threshold else ''}")

        if eval_result.pass_threshold:
            break

        # Check for minimal improvement (stop if plateauing)
        if iteration > 0 and len(iterations) >= 2:
            prev = iterations[-2].eval_score
            if eval_result.overall_score - prev < 0.3:
                logger.info(f"[Agent L{layer}] Minimal improvement "
                           f"({prev:.1f} → {eval_result.overall_score:.1f}), stopping.")
                break

        # Append feedback and continue (agent keeps full context)
        feedback = _format_feedback(eval_result)
        messages.append(HumanMessage(content=feedback))

    return draft, ctx.sources, iterations
