"""
ReAct Agent Engine: LLM autonomously calls tools, then evaluator scores output.

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

Used by layers/enhanced.py (Layer 1). Not used by Layer 0 or Layer 2.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Callable

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, ToolMessage, SystemMessage

from research_agent.models import Source, EvalResult, AgentIteration, AgentContext
from research_agent.cost import track
from research_agent.utils import extract_json, strip_preamble, infer_publisher
from research_agent.prompts import REPORT_OUTLINE_PROMPT
from tools.search import search
from tools.scraper import scrape_url
from tools.source_classifier import get_source_tier

logger = logging.getLogger(__name__)


# ─── Report outline generation ────────────────────────────────────────────


async def generate_report_outline(topic: str, llm) -> str:
    """Generate a shared report outline for all layers.

    First runs a quick web search to disambiguate the topic — this ensures the
    LLM understands niche/ambiguous topics (e.g. "utility marker market" vs
    "utility market") before generating the outline.

    Returns a plain-text outline like:
      Report type: PEST Analysis
      Sections:
      1. Political Factors — trade policy, regulation, geopolitical risk
      2. Economic Factors — macro conditions, consumer spending, input costs
      ...

    Returns empty string on failure — callers fall back to their own structure.
    """
    try:
        # Quick web search to disambiguate the topic before planning
        topic_context = ""
        try:
            results = await search(topic, max_results=3, include_news=False)
            if results:
                snippets = []
                for r in results[:3]:
                    title = r.get("title", "")
                    snippet = r.get("snippet", "")
                    if title or snippet:
                        snippets.append(f"- {title}: {snippet[:150]}")
                if snippets:
                    topic_context = (
                        "\n\nWeb search context (use this to understand what this topic/market "
                        "actually refers to — do NOT confuse with similar-sounding markets):\n"
                        + "\n".join(snippets)
                    )
                    logger.info(f"[Outline] Topic context from {len(snippets)} search results")
        except Exception as e:
            logger.warning(f"[Outline] Topic disambiguation search failed: {e}")

        prompt_content = REPORT_OUTLINE_PROMPT.format(topic=topic) + topic_context

        messages = [
            {"role": "system", "content": "You are a research planning expert. Follow the output format exactly."},
            {"role": "user", "content": prompt_content},
        ]
        response = await llm.ainvoke(messages)
        track("outline", response)
        outline = response.content.strip()
        if "Sections:" in outline and "Report type:" in outline:
            logger.info(f"[Outline] Generated for: {topic[:60]}")
            return outline
        logger.warning("[Outline] Unexpected format, skipping")
    except Exception as e:
        logger.warning(f"[Outline] Generation failed: {e}")
    return ""


def parse_outline_type(outline: str) -> str:
    """Extract report type from the outline text.

    Parses 'Report type: PEST Analysis' → 'PEST Analysis'.
    Returns empty string if not found.
    """
    import re
    for line in outline.splitlines():
        m = re.match(r"Report\s+type:\s*(.+)", line.strip(), re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def parse_outline_sections(outline: str) -> list[str]:
    """Extract section names from the outline text.

    Parses lines like '1. Political Factors — trade policy...' into ['Political Factors', ...].
    """
    import re
    sections = []
    for line in outline.splitlines():
        m = re.match(r"\d+\.\s+(.+?)(?:\s*[—–-]\s+.*)?$", line.strip())
        if m:
            sections.append(m.group(1).strip())
    return sections


# ─── Tool factory ──────────────────────────────────────────────────────────


def make_tools(ctx: AgentContext) -> list:
    """Create LangChain tools with closures over shared AgentContext."""

    @tool
    async def search_web(query: str) -> str:
        """Search the web for market research data. Returns titles, URLs, and snippets
        from top results. Use targeted queries with specific terms and the current year."""
        if ctx.tool_call_count >= ctx.max_tool_calls:
            return "BUDGET EXCEEDED. Output ONLY the report content now — start directly with ## headings. No preamble, no explanation, no 'Below is...' or 'I can't run more queries'."
        ctx.tool_call_count += 1

        try:
            results = await search(query, max_results=5, include_news=True)
        except Exception as e:
            ctx.tool_calls_log.append({"tool": "search_web", "query": query, "results": 0, "hits": []})
            return f"Search failed: {e}. Try a different query."

        if not results:
            ctx.tool_calls_log.append({"tool": "search_web", "query": query, "results": 0, "hits": []})
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
                    publisher=infer_publisher(url),
                    date=r.get("date", ""),
                    tier=get_source_tier(url),
                ))
                new_count += 1

            tier = get_source_tier(url)
            tier_label = {1: "T1", 2: "T2", 3: "T3"}[tier]
            parts.append(f"[{tier_label}] {title}\n  {snippet[:200]}")

        hit_data = [
            {"title": r.get("title", ""), "snippet": r.get("snippet", "")[:200], "url": r.get("url", "")}
            for r in results if r.get("url")
        ][:3]
        ctx.tool_calls_log.append({
            "tool": "search_web", "query": query, "results": len(results), "hits": hit_data,
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
                    publisher=infer_publisher(url),
                    tier=get_source_tier(url),
                ))

        ctx.tool_calls_log.append({"tool": "scrape_page", "url": url})
        tier_label = {1: "T1", 2: "T2", 3: "T3"}[get_source_tier(url)]
        return f"[{tier_label}] Content from {infer_publisher(url)} ({len(content)} chars):\n\n{content}"

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
        return f"{infer_publisher(url)}: {labels[tier]}"

    return [search_web, scrape_page, assess_source]


# ─── Evaluation helpers ───────────────────────────────────────────────────


async def _evaluate_draft(draft, topic, eval_prompt, eval_llm, layer,
                          iteration: int = 0, prev_weaknesses: list[str] | None = None):
    """Score a draft using the evaluator LLM."""
    iteration_context = ""
    if iteration > 0 and prev_weaknesses:
        iteration_context = (
            f"\n\nThis is revision #{iteration + 1}. Previous weaknesses were:\n"
            + "\n".join(f"- {w}" for w in prev_weaknesses)
            + "\n\nScore based on WHETHER these weaknesses have been addressed. "
            "If all were fixed, the score MUST increase. "
            "Only repeat a weakness if it is genuinely still present."
        )

    messages = [
        {"role": "system", "content": "You are a demanding reviewer. Return valid JSON only."},
        {"role": "user", "content": eval_prompt.format(topic=topic, draft=draft) + iteration_context},
    ]
    try:
        response = await eval_llm.ainvoke(messages)
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


# ─── Main ReAct Engine ────────────────────────────────────────────────────


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
    outline: str = "",
    topic_rules: str = "",
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

    # Phase 0: Use shared outline or generate one
    if not outline:
        notify("planning", "Planning report structure...")
        outline = await generate_report_outline(topic, llm)
    if outline:
        notify("planned", f"Structure planned: {outline.splitlines()[0]}")

    # Initial message — dynamic context goes here (not in system prompt) for prompt caching.
    # OpenAI auto-caches identical system prompt prefixes at 50% cost discount.
    current_year = datetime.now().year
    initial = (f"Research topic: {topic}\n"
               f"IMPORTANT: The current year is {current_year}. All analysis must be written "
               f"from a {current_year} perspective. Do NOT write 'in {current_year - 1}' as if "
               f"it is the present — {current_year - 1} is last year.")
    if topic_rules:
        initial += f"\n\n{topic_rules}"
    if outline:
        initial += (f"\n\nREPORT OUTLINE — follow this structure exactly:\n{outline}"
                    f"\n\nCRITICAL: Do NOT add, remove, rename, or reorder any sections. "
                    f"Use EXACTLY these sections as your ## headings. All layers must produce "
                    f"identical section headings for cross-layer comparison.")
    if ctx.prior_content:
        initial += (f"\n\nPrior layer analysis (RETAIN all verified data, CORRECT errors):"
                    f"\n{ctx.prior_content}")
    if ctx.existing_sources:
        initial += f"\n\n{len(ctx.existing_sources)} sources already tracked from previous layer."

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=initial),
    ]

    # Adaptive minimum word count: ~200 words per section, minimum 800
    num_sections = len(parse_outline_sections(outline)) if outline else 5
    min_word_count = max(num_sections * 200, 800)

    draft = ""
    _forced_search = False

    for iteration in range(max_iterations):
        notify("researching", f"Iteration {iteration + 1}/{max_iterations}: agent working...")

        # Reset per-iteration counters
        ctx.tool_call_count = 0
        log_start = len(ctx.tool_calls_log)
        sources_start = len(ctx.sources)

        # ── Inner ReAct loop ──────────────────────────────────────────
        for _ in range(max_steps_per_iteration):
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
                # GUARD: Reject draft if agent hasn't done enough research (first iteration).
                if iteration == 0 and not _forced_search:
                    searches_done = sum(1 for tc in ctx.tool_calls_log if tc.get("tool") == "search_web")
                    scrapes_done = sum(1 for tc in ctx.tool_calls_log if tc.get("tool") == "scrape_page")
                    if searches_done < 5 or scrapes_done < 2:
                        _forced_search = True
                        logger.info(f"[Agent L{layer}] Rejected draft — only {searches_done} searches, "
                                    f"{scrapes_done} scrapes. Forcing more research.")
                        messages.append(HumanMessage(
                            content=f"STOP. You have only done {searches_done} searches and {scrapes_done} scrapes. "
                                    "This is NOT enough research. You MUST:\n"
                                    "1. Call search_web at least 8 times (one per section in your outline)\n"
                                    "2. Call scrape_page on at least 3 promising URLs for detailed data\n"
                                    "Do MORE research now — do not write the report yet."
                        ))
                        continue

                if response.content and len(response.content.strip()) > 100:
                    candidate = strip_preamble(response.content.strip())
                    word_count = len(candidate.split())

                    # WORD COUNT GUARD: reject thin drafts and force expansion
                    if word_count < min_word_count and iteration < max_iterations - 1:
                        target = int(min_word_count * 1.5)
                        logger.info(f"[Agent L{layer}] Rejected draft — only {word_count} words "
                                    f"(minimum {min_word_count}). Forcing expansion.")
                        messages.append(HumanMessage(
                            content=f"REJECTED: Your report is only {word_count} words. "
                                    f"The MINIMUM is {min_word_count} words (ideally {target}). "
                                    f"You have {num_sections} sections — each needs 200-350 words with "
                                    "specific named companies, causal analysis, and detailed mechanisms.\n\n"
                                    "Rewrite your report NOW with MUCH MORE DETAIL in every section. "
                                    "Use ALL the data you gathered from your searches and scrapes. "
                                    "Do not summarize — ANALYZE in depth. "
                                    "Start directly with ## headings."
                        ))
                        continue

                    draft = candidate
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
                    content="Tool budget exhausted. Write your final report NOW. "
                            "Start DIRECTLY with ## headings — no preamble, no 'I can't run more queries', "
                            "no explanation of what you're about to write. Just the report."
                ))

        # Force output if agent didn't produce a report
        if not draft or len(draft.strip()) < 100:
            notify("forcing", "Agent didn't produce output, requesting report...")
            messages.append(HumanMessage(
                content="Write your final report NOW. Start DIRECTLY with ## headings — "
                        "no preamble, no 'Here is...', no explanation. Just the report content."
            ))
            try:
                # Call WITHOUT tools bound so it can't make tool calls
                response = await llm.ainvoke(messages)
                track(f"L{layer} forced", response)
                messages.append(response)
                if response.content:
                    draft = strip_preamble(response.content.strip())
            except Exception as e:
                logger.error(f"[Agent L{layer}] Forced draft failed: {e}")
                draft = f"Error generating report: {e}"

        # ── Outer evaluation ──────────────────────────────────────────
        notify("evaluating", f"Iter {iteration + 1}: evaluating draft...")
        prev_weaknesses = iterations[-1].weaknesses if iterations else None
        eval_result = await _evaluate_draft(
            draft, topic, eval_prompt_template, eval_llm, layer,
            iteration=iteration, prev_weaknesses=prev_weaknesses,
        )
        eval_result.check_threshold(convergence_threshold)

        # Track per-iteration metrics
        new_logs = ctx.tool_calls_log[log_start:]
        queries = [
            {
                "tool": l.get("tool", "search_web"),
                "query": l.get("query") or l.get("search_query", ""),
                "hits": l.get("hits", []),
            }
            for l in new_logs
            if l.get("tool") in ("search_web", "verify_claim", "challenge_assumption", "find_bear_case", "cross_industry_search")
            and (l.get("query") or l.get("search_query"))
        ]

        # Determine stop reason
        draft_words = len(draft.split()) if draft else 0
        stop_reason = ""
        if eval_result.pass_threshold and draft_words >= min_word_count:
            stop_reason = "threshold"
        elif eval_result.pass_threshold and draft_words < min_word_count:
            logger.info(f"[Agent L{layer}] Score {eval_result.overall_score:.1f} passes threshold "
                        f"but draft is only {draft_words}/{min_word_count} words — forcing expansion")
        elif iteration > 0 and len(iterations) >= 1:
            prev = iterations[-1].eval_score
            if eval_result.overall_score - prev < 0.3:
                if draft_words >= min_word_count:
                    stop_reason = "plateau"
                else:
                    logger.info(f"[Agent L{layer}] Plateau at {eval_result.overall_score:.1f} "
                                f"but draft only {draft_words}/{min_word_count} words — continuing")

        iterations.append(AgentIteration(
            iteration=iteration,
            eval_score=eval_result.overall_score,
            weaknesses=eval_result.weaknesses,
            queries_run=queries,
            new_sources_count=len(ctx.sources) - sources_start,
            stop_reason=stop_reason,
        ))

        notify("eval_done",
               f"Iter {iteration + 1}: {eval_result.overall_score:.1f}/10"
               f"{' — converged!' if stop_reason == 'threshold' else ''}"
               f"{' — plateaued' if stop_reason == 'plateau' else ''}")

        if stop_reason:
            break

        # Append feedback and continue (agent keeps full context)
        feedback = _format_feedback(eval_result)
        if draft_words < min_word_count:
            feedback += (
                f"\n\nCRITICAL: Your report is only {draft_words} words. "
                f"MINIMUM is {min_word_count} words ({num_sections} sections × 200+ words each). "
                "Each section needs specific companies, causal chains, and detailed analysis. "
                "EXPAND every section significantly."
            )
        messages.append(HumanMessage(content=feedback))

    return draft, ctx.sources, iterations
