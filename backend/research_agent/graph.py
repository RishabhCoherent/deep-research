"""
LangGraph agent engine for Layer 1 (Enhancement) and Layer 2 (Deep Dive).

Replaces the manual ReAct loop in react_engine.py with a LangGraph StateGraph.
Both L1 and L2 use the same graph structure, differing only in:
  - System prompt (enhancement vs deep-dive)
  - Tool budget (25 vs 35)
  - Model tier (standard vs premium)

Graph structure:
  START → agent → [tool_calls?]
                   ├── YES → tools → [budget exceeded?]
                   │                   ├── YES → force_output → END
                   │                   └── NO  → agent
                   └── NO  → [valid draft?]
                              ├── YES → END
                              └── NO  → agent (retry)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Optional, Callable

from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage, AIMessage
from langchain_core.tools import tool

from research_agent.models import Source, AgentContext, EvidenceLedger, ClaimMap
from research_agent.cost import track
from research_agent.utils import strip_preamble, infer_publisher
from tools.search import search
from tools.scraper import scrape_url
from tools.source_classifier import get_source_tier
from tools.citation import is_banned_source, check_text_for_banned_citations

logger = logging.getLogger(__name__)


# ─── Competitor scrubbing ─────────────────────────────────────────────────────

# Phrases that identify competitor research firm attributions in report text.
# These are checked case-insensitively against the final draft.
_COMPETITOR_PHRASES = [
    "according to marketsandmarkets", "according to markets and markets",
    "according to mordor intelligence", "according to grand view research",
    "according to fortune business insights", "according to allied market research",
    "according to emergen research", "according to precedence research",
    "according to transparency market research", "according to frost & sullivan",
    "according to technavio", "according to euromonitor", "according to mintel",
    "according to statista", "according to imarc", "according to gartner",
    "according to idc", "according to verified market research",
    "according to future market insights", "according to expert market research",
    "according to ken research", "according to p&s intelligence",
    "according to fact.mr", "according to persistence market research",
    "according to straits research", "according to coherent market insights",
    "according to data bridge", "according to polaris market research",
    "according to skyquest", "according to astute analytica",
    "a report by marketsandmarkets", "a report by mordor intelligence",
    "a report by grand view research", "a study by marketsandmarkets",
    "marketsandmarkets estimates", "mordor intelligence estimates",
    "grand view research estimates", "marketsandmarkets projects",
    "mordor intelligence projects", "grand view research projects",
    "marketsandmarkets report", "mordor intelligence report",
    "grand view research report", "fortune business insights report",
]


def _scrub_competitor_mentions(draft: str) -> str:
    """Remove sentences that attribute data to competitor research firms.

    Uses two passes:
    1. Remove sentences containing known competitor attribution phrases
    2. Check for any remaining banned source names (log warning but don't break flow)
    """
    import re

    lines = draft.split("\n")
    cleaned_lines = []

    for line in lines:
        line_lower = line.lower()
        # Check if this line contains a competitor attribution
        has_competitor = False
        for phrase in _COMPETITOR_PHRASES:
            if phrase in line_lower:
                has_competitor = True
                logger.info(f"[Scrub] Removed competitor mention: '{phrase}' in line")
                break

        if has_competitor:
            # Try to remove just the offending sentence, not the whole line
            # Split by sentence boundaries and keep clean sentences
            sentences = re.split(r'(?<=[.!?])\s+', line)
            clean_sentences = []
            for sent in sentences:
                sent_lower = sent.lower()
                if not any(p in sent_lower for p in _COMPETITOR_PHRASES):
                    clean_sentences.append(sent)
            if clean_sentences:
                cleaned_lines.append(" ".join(clean_sentences))
            # else: entire line was competitor content, skip it
        else:
            cleaned_lines.append(line)

    result = "\n".join(cleaned_lines)

    # Final check — log any remaining banned names (from citation.py's full list)
    remaining = check_text_for_banned_citations(result)
    if remaining:
        logger.warning(f"[Scrub] Remaining competitor names in draft: {remaining}")

    return result


# ─── State schema ─────────────────────────────────────────────────────────────


class AgentState(TypedDict):
    """State for LangGraph research agents (L1 and L2)."""
    messages: Annotated[list[BaseMessage], add_messages]
    topic: str
    brief: str             # detailed client instructions (optional)
    layer: int
    prior_report: str
    tool_call_count: int
    max_tool_calls: int
    tool_calls_log: list[dict]
    draft: str
    retries: int           # number of times agent was asked to retry output
    max_retries: int
    min_word_count: int
    forced_search: bool    # whether we've already forced more research


# ─── Source-text validation ───────────────────────────────────────────────────

import re as _re


def _validate_finding_against_source(finding: str, source_text: str) -> bool:
    """Check that key entities and numbers in a finding appear in the source text.

    Uses simple keyword/number matching — not LLM. Returns True if the finding
    is reasonably grounded in the source, False if it appears to be inferred.

    Rules:
    - Extract all numbers (digits) from the finding
    - Extract capitalized proper nouns (2+ words starting with uppercase)
    - If ≥40% of extracted tokens appear in the source, it's grounded
    - If no source text is available, return False (unverifiable)
    """
    if not source_text or len(source_text.strip()) < 20:
        return False

    finding_lower = finding.lower()
    source_lower = source_text.lower()

    tokens_to_check = []

    # Extract numbers (e.g., "40,000", "2.16", "25%", "$47")
    numbers = _re.findall(r'\d[\d,\.]*', finding)
    for n in numbers:
        # Strip trailing dots/commas
        clean = n.rstrip('.,')
        if clean:
            tokens_to_check.append(clean)

    # Extract multi-word proper nouns (e.g., "Dixon Technologies", "Tamil Nadu")
    proper_nouns = _re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', finding)
    for pn in proper_nouns:
        tokens_to_check.append(pn.lower())

    # Extract single capitalized words that aren't sentence starters (heuristic)
    # Look for words like "MeitY", "SPECS", "PLI", "ECMS" (all-caps acronyms)
    acronyms = _re.findall(r'\b[A-Z]{2,}[a-z]*\b', finding)
    for acr in acronyms:
        tokens_to_check.append(acr.lower())

    if not tokens_to_check:
        # No verifiable tokens — can't validate, assume OK for short generic findings
        return len(finding.split()) < 15

    # Count how many tokens appear in source (with word-boundary matching for numbers)
    def _token_in_source(token: str, source: str) -> bool:
        # For pure numbers, use word-boundary match to avoid "25" matching inside "22,919"
        if _re.match(r'^\d[\d,\.]*$', token):
            # Escape dots for regex, match as standalone number
            pattern = r'(?<!\d)' + _re.escape(token) + r'(?!\d)'
            return bool(_re.search(pattern, source))
        return token in source

    matches = sum(1 for t in tokens_to_check if _token_in_source(t, source_lower))
    ratio = matches / len(tokens_to_check)

    logger.debug(
        f"[validate_finding] {matches}/{len(tokens_to_check)} tokens matched "
        f"({ratio:.0%}). Tokens: {tokens_to_check[:8]}"
    )

    return ratio >= 0.4


# ─── Tool factory ─────────────────────────────────────────────────────────────


def make_tools(ctx: AgentContext, ledger: EvidenceLedger | None = None, claim_map: ClaimMap | None = None) -> list:
    """Create LangChain tools with closures over shared AgentContext.

    Args:
        ctx: Shared agent context for source/tool tracking
        ledger: Optional evidence ledger for expert pipeline (enables record_finding tool)
        claim_map: Optional claim map for expert pipeline (enables coverage tracking)
    """

    @tool
    async def search_web(query: str) -> str:
        """Search the web for current data, trends, and insights. Returns titles,
        URLs, and snippets from top results. Use targeted queries with specific
        terms and the current year."""
        if ctx.tool_call_count >= ctx.max_tool_calls:
            return (
                "BUDGET EXCEEDED. Write your final report now — start directly "
                "with ## headings. No preamble, no explanation."
            )
        ctx.tool_call_count += 1

        try:
            results = await search(query, max_results=5, include_news=True)
        except Exception as e:
            ctx.tool_calls_log.append({
                "tool": "search_web", "query": query, "results": 0, "hits": [],
            })
            return f"Search failed: {e}. Try a different query."

        if not results:
            ctx.tool_calls_log.append({
                "tool": "search_web", "query": query, "results": 0, "hits": [],
            })
            return "No results found. Try a different query."

        # Filter out competitor market research firms and Wikipedia
        results = [
            r for r in results
            if not is_banned_source(r.get("url", ""), r.get("title", ""))
            and "wikipedia.org" not in r.get("url", "").lower()
        ]
        if not results:
            ctx.tool_calls_log.append({
                "tool": "search_web", "query": query, "results": 0, "hits": [],
            })
            return "No usable results (all from competitor research firms). Try a different query."

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
            {"title": r.get("title", ""), "snippet": r.get("snippet", "")[:200],
             "url": r.get("url", "")}
            for r in results if r.get("url")
        ][:3]
        ctx.tool_calls_log.append({
            "tool": "search_web", "query": query,
            "results": len(results), "hits": hit_data,
        })
        return f"{len(results)} results ({new_count} new):\n\n" + "\n\n".join(parts)

    @tool
    async def scrape_page(url: str) -> str:
        """Scrape full text content from a web page. Use on the most promising
        search results to get detailed data, statistics, or analysis."""
        if ctx.tool_call_count >= ctx.max_tool_calls:
            return "BUDGET EXCEEDED. Write your final report now."

        # Block scraping competitor research firm pages and Wikipedia
        if is_banned_source(url):
            return "BLOCKED: This is a competitor market research firm. Do not use this source. Try a different URL."
        if "wikipedia.org" in url.lower():
            return "BLOCKED: Wikipedia is not a credible source for market research. Use news outlets, company filings, or industry publications instead."

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
        return (
            f"[{tier_label}] Content from {infer_publisher(url)} "
            f"({len(content)} chars):\n\n{content}"
        )

    @tool
    async def assess_source(url: str) -> str:
        """Check credibility tier of a source URL. Returns T1 (gold-standard),
        T2 (reliable), or T3 (unverified)."""
        tier = get_source_tier(url)
        labels = {
            1: "TIER-1 HIGH-CREDIBILITY. Prefer this data when numbers conflict.",
            2: "TIER-2 RELIABLE. Generally trustworthy.",
            3: "TIER-3 UNVERIFIED. Cross-check against T1/T2 sources.",
        }
        return f"{infer_publisher(url)}: {labels[tier]}"

    tools_list = [search_web, scrape_page, assess_source]

    # Add record_finding tool for expert pipeline (evidence tracking)
    if ledger is not None and claim_map is not None:
        from research_agent.models import Evidence

        @tool
        async def record_finding(claim_id: str, finding: str, evidence_type: str, confidence: str) -> str:
            """Record a research finding and map it to a specific claim. Use this after
            finding relevant data from search or scrape to explicitly link evidence to claims.

            Args:
                claim_id: The claim ID this evidence supports (e.g., "s1_c01")
                finding: What you found (the factual content)
                evidence_type: "confirms", "contradicts", "extends", or "quantifies"
                confidence: "high", "medium", or "low"
            """
            # Get source info from most recent scrape/search
            source_url = ""
            source_title = ""
            source_tier = 3
            source_text = ""  # The actual text from the source for validation
            for tc in reversed(ctx.tool_calls_log):
                if tc.get("tool") == "scrape_page":
                    source_url = tc.get("url", "")
                    for s in ctx.sources:
                        if s.url == source_url:
                            source_title = s.title
                            source_tier = s.tier
                            source_text = s.scraped_content or s.snippet or ""
                            break
                    break
                elif tc.get("tool") == "search_web":
                    hits = tc.get("hits", [])
                    if hits:
                        source_url = hits[0].get("url", "")
                        source_title = hits[0].get("title", "")
                        source_text = hits[0].get("snippet", "")
                    break

            # ── Source-text validation ────────────────────────────────────
            # Check that key entities/numbers in the finding actually appear
            # in the source text. If not, downgrade confidence and mark as inferred.
            validated = _validate_finding_against_source(finding, source_text)
            if not validated:
                logger.warning(
                    f"[record_finding] Finding not grounded in source text. "
                    f"claim={claim_id}, confidence downgraded to 'low', type='inferred'. "
                    f"Finding: {finding[:120]}..."
                )
                confidence = "low"
                evidence_type = "inferred"

            evidence = Evidence(
                claim_id=claim_id,
                fact=finding,
                source_url=source_url,
                source_title=source_title,
                source_tier=source_tier,
                evidence_type=evidence_type,
                confidence=confidence,
            )
            ledger.add(evidence)

            # NOTE: record_finding does NOT increment tool_call_count — it's bookkeeping
            coverage = ledger.coverage_score(claim_map)
            uncovered = ledger.uncovered_claims(claim_map)
            remaining = len(uncovered)

            ctx.tool_calls_log.append({
                "tool": "record_finding",
                "claim_id": claim_id,
                "evidence_type": evidence_type,
            })

            return (
                f"Recorded. Coverage: {coverage:.0%}. "
                f"{remaining} claims still need evidence."
            )

        tools_list.append(record_finding)

    return tools_list


# ─── Graph builder ─────────────────────────────────────────────────────────────


ProgressFn = Optional[Callable[[int, str, str], None]]


def build_agent_graph(
    llm,
    tools: list,
    system_prompt: str,
    max_tool_calls: int = 25,
    min_word_count: int = 800,
    max_retries: int = 3,
    progress_callback: ProgressFn = None,
    layer: int = 1,
    ctx: AgentContext | None = None,
    ledger: EvidenceLedger | None = None,
    claim_map: ClaimMap | None = None,
):
    """Build and compile a LangGraph StateGraph for a research agent.

    Args:
        llm: ChatOpenAI instance (will be bound to tools internally)
        tools: List of LangChain tools [search_web, scrape_page, assess_source]
        system_prompt: System prompt (different for L1 vs L2)
        max_tool_calls: Tool budget cap
        min_word_count: Minimum words for a valid draft
        max_retries: Max times to ask agent to retry output
        progress_callback: SSE progress callback (layer, status, message)
        layer: Layer number (1 or 2) for logging/progress
        ctx: AgentContext for tracking tool calls (used for forced search check)
    """

    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    def notify(status: str, msg: str):
        if progress_callback:
            progress_callback(layer, status, msg)
        logger.info(f"[Agent L{layer}] {status}: {msg}")

    # ── Node: agent ────────────────────────────────────────────────────────
    async def agent_node(state: AgentState) -> dict:
        """Call LLM with tools bound. The LLM decides whether to use tools or output."""
        notify("researching", f"Agent working... ({state['tool_call_count']} tool calls so far)")

        try:
            response = await llm_with_tools.ainvoke(state["messages"])
            track(f"L{layer} agent", response)
        except Exception as e:
            logger.error(f"[Agent L{layer}] LLM call failed: {e}")
            error_msg = HumanMessage(
                content=f"Error occurred: {e}. Write your report with available data."
            )
            return {"messages": [error_msg]}

        return {"messages": [response]}

    # ── Node: tools ────────────────────────────────────────────────────────
    async def tool_node(state: AgentState) -> dict:
        """Execute tool calls from the last AI message."""
        last_msg = state["messages"][-1]
        if not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
            return {}

        tool_messages = []
        new_tool_count = 0

        for tc in last_msg.tool_calls:
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

            tool_messages.append(ToolMessage(content=str(result), tool_call_id=tid))
            new_tool_count += 1

        # Update tool call count in state
        new_count = state["tool_call_count"] + new_tool_count

        return {
            "messages": tool_messages,
            "tool_call_count": new_count,
        }

    # ── Node: force_output ─────────────────────────────────────────────────
    async def force_output_node(state: AgentState) -> dict:
        """Call LLM without tools to force a final report."""
        notify("forcing", "Requesting final report...")

        force_msg = HumanMessage(
            content=(
                "Write your final report NOW. Start DIRECTLY with ## headings — "
                "no preamble, no 'Here is...', no explanation. Just the report content.\n\n"
                "CRITICAL: Your report MUST include specific data points (numbers, percentages, "
                "company names, dates) from the search results and scraped pages above. "
                "Do NOT just paraphrase the baseline report with different words. "
                "Every paragraph should contain at least one SPECIFIC fact you discovered "
                "during your research. If a section has no new data from your searches, "
                "acknowledge the gap rather than restating baseline claims."
            )
        )

        try:
            # Call WITHOUT tools bound so it can't make more tool calls
            response = await llm.ainvoke(state["messages"] + [force_msg])
            track(f"L{layer} forced", response)
        except Exception as e:
            logger.error(f"[Agent L{layer}] Forced output failed: {e}")
            return {
                "messages": [force_msg],
                "draft": f"Error generating report: {e}",
            }

        content = response.content if isinstance(response.content, str) else str(response.content)
        draft = strip_preamble(content.strip())
        draft = _scrub_competitor_mentions(draft)
        notify("drafted", f"Report: {len(draft.split())} words")

        return {
            "messages": [force_msg, response],
            "draft": draft,
        }

    # ── Node: budget_nudge ─────────────────────────────────────────────────
    async def budget_nudge_node(state: AgentState) -> dict:
        """Append a message telling the agent its tool budget is exhausted."""
        nudge = HumanMessage(
            content=(
                "Tool budget exhausted. Write your final report NOW. "
                "Start DIRECTLY with ## headings — no preamble, no explanation.\n\n"
                "CRITICAL: Include the specific data you found — numbers, percentages, "
                "company details, dates. Do NOT just rephrase the baseline report. "
                "Every section needs real data from your searches."
            )
        )
        return {"messages": [nudge]}

    # ── Node: force_search ─────────────────────────────────────────────────
    async def force_search_node(state: AgentState) -> dict:
        """Force the agent to do more research before writing."""
        searches_done = sum(
            1 for tc in (ctx.tool_calls_log if ctx else [])
            if tc.get("tool") == "search_web"
        )
        scrapes_done = sum(
            1 for tc in (ctx.tool_calls_log if ctx else [])
            if tc.get("tool") == "scrape_page"
        )

        # Coverage-aware message for expert pipeline
        if ledger is not None and claim_map is not None:
            coverage = ledger.coverage_score(claim_map)
            findings_count = len(ledger.entries)
            uncovered = ledger.uncovered_claims(claim_map)
            uncovered_list = "\n".join(f"  - [{c.id}] {c.text}" for c in uncovered[:10])

            if searches_done >= 3 and findings_count == 0:
                # Agent is searching but never recording — this is the #1 failure mode
                msg = HumanMessage(
                    content=(
                        f"CRITICAL: You have done {searches_done} searches but recorded ZERO findings. "
                        "Your search results contain useful data — you MUST call record_finding() now.\n\n"
                        "EXAMPLE: After a search about cloud market size returns results mentioning '$600B', call:\n"
                        '  record_finding(claim_id="s1_c01", finding="Global cloud market reached $600B in 2025", '
                        'evidence_type="quantifies", confidence="high")\n\n'
                        f"Claims needing evidence:\n{uncovered_list}\n\n"
                        "Follow the 3-step cycle: SEARCH → SCRAPE → RECORD. Do it NOW."
                    )
                )
            else:
                msg = HumanMessage(
                    content=(
                        f"STOP. Coverage is only {coverage:.0%}. "
                        f"You have done {searches_done} searches and {scrapes_done} scrapes, "
                        f"but {len(uncovered)} claims still have NO evidence.\n\n"
                        f"Claims still needing evidence:\n{uncovered_list}\n\n"
                        "Follow the 3-step cycle: SEARCH → SCRAPE → RECORD. "
                        "Use record_finding to log your discoveries. Do NOT write the report yet."
                    )
                )
        else:
            msg = HumanMessage(
                content=(
                    f"STOP. You have only done {searches_done} searches and {scrapes_done} scrapes. "
                    "This is NOT enough research. You MUST:\n"
                    "1. Search for data on each major aspect of the topic\n"
                    "2. Scrape at least 3 promising pages for detailed data\n"
                    "Do MORE research now — do not write the report yet."
                )
            )
        return {"messages": [msg], "forced_search": True}

    # ── Node: reject_draft ─────────────────────────────────────────────────
    async def reject_draft_node(state: AgentState) -> dict:
        """Reject a thin draft and ask for expansion."""
        last_msg = state["messages"][-1]
        content = last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content)
        word_count = len(content.split())
        target = int(state["min_word_count"] * 1.5)

        msg = HumanMessage(
            content=(
                f"REJECTED: Your report is only {word_count} words. "
                f"The MINIMUM is {state['min_word_count']} words (ideally {target}). "
                "Rewrite your report with MUCH MORE DETAIL in every section. "
                "Use ALL the data you gathered from your searches and scrapes. "
                "Do not summarize — ANALYZE in depth. "
                "Start directly with ## headings."
            )
        )
        return {"messages": [msg], "retries": state["retries"] + 1}

    # ── Edge routing ───────────────────────────────────────────────────────

    def route_after_agent(state: AgentState) -> str:
        """Route based on the last AI message: tool calls, or final output."""
        last_msg = state["messages"][-1]

        # If the last message has tool calls, go to tools
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"

        # No tool calls — agent produced text output
        content = last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content)
        content = content.strip()

        # Check if agent has done enough research (first time only)
        if not state.get("forced_search", False) and ctx:
            searches_done = sum(
                1 for tc in ctx.tool_calls_log if tc.get("tool") == "search_web"
            )
            scrapes_done = sum(
                1 for tc in ctx.tool_calls_log if tc.get("tool") == "scrape_page"
            )

            # Coverage-aware check for expert pipeline
            if ledger is not None and claim_map is not None:
                coverage = ledger.coverage_score(claim_map)
                findings_count = len(ledger.entries)
                # If agent has searched but never recorded findings, remind it
                if searches_done >= 3 and findings_count == 0:
                    return "force_search"
                # If coverage is still low, push for more research
                if coverage < 0.7 and searches_done < 40:
                    return "force_search"
            elif searches_done < 5 or scrapes_done < 2:
                return "force_search"

        # Check if draft is long enough
        if content and len(content) > 100:
            candidate = strip_preamble(content)
            word_count = len(candidate.split())

            if word_count < state["min_word_count"] and state["retries"] < state["max_retries"]:
                return "reject_draft"

            # Valid draft — accept it
            return "accept_draft"

        # Too short to be a report — retry
        if state["retries"] < state["max_retries"]:
            return "reject_draft"

        return "force_output"

    def route_after_tools(state: AgentState) -> str:
        """After executing tools, check if budget is exceeded."""
        if state["tool_call_count"] >= state["max_tool_calls"]:
            return "budget_nudge"
        return "agent"

    # ── Node: accept_draft ─────────────────────────────────────────────────
    async def accept_draft_node(state: AgentState) -> dict:
        """Extract the draft from the last message."""
        last_msg = state["messages"][-1]
        content = last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content)
        draft = strip_preamble(content.strip())
        # Scrub any remaining competitor mentions from final text
        draft = _scrub_competitor_mentions(draft)
        word_count = len(draft.split())
        notify("drafted", f"Report: {word_count} words")
        return {"draft": draft}

    # ── Build the graph ────────────────────────────────────────────────────

    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("force_output", force_output_node)
    graph.add_node("budget_nudge", budget_nudge_node)
    graph.add_node("force_search", force_search_node)
    graph.add_node("reject_draft", reject_draft_node)
    graph.add_node("accept_draft", accept_draft_node)

    # Add edges
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent, {
        "tools": "tools",
        "force_search": "force_search",
        "reject_draft": "reject_draft",
        "accept_draft": "accept_draft",
        "force_output": "force_output",
    })
    graph.add_conditional_edges("tools", route_after_tools, {
        "budget_nudge": "budget_nudge",
        "agent": "agent",
    })
    graph.add_edge("budget_nudge", "agent")
    graph.add_edge("force_search", "agent")
    graph.add_edge("reject_draft", "agent")
    graph.add_edge("accept_draft", END)
    graph.add_edge("force_output", END)

    return graph.compile()


def build_initial_state(
    topic: str,
    layer: int,
    system_prompt: str,
    prior_report: str,
    brief: str = "",
    max_tool_calls: int = 25,
    min_word_count: int = 800,
    max_retries: int = 3,
) -> AgentState:
    """Build the initial state for a LangGraph agent invocation."""
    current_year = datetime.now().year

    user_content = (
        f"Research topic: {topic}\n"
        f"The current year is {current_year}. Write from a {current_year} perspective.\n\n"
    )

    if brief:
        user_content += (
            f"CLIENT BRIEF (follow these instructions carefully — they define the scope, "
            f"structure, and focus of this report):\n\n{brief}\n\n"
        )

    user_content += f"PREVIOUS LAYER'S REPORT (improve upon this):\n\n{prior_report}"

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]

    return {
        "messages": messages,
        "topic": topic,
        "brief": brief,
        "layer": layer,
        "prior_report": prior_report,
        "tool_call_count": 0,
        "max_tool_calls": max_tool_calls,
        "tool_calls_log": [],
        "draft": "",
        "retries": 0,
        "max_retries": max_retries,
        "min_word_count": min_word_count,
        "forced_search": False,
    }
