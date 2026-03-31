"""
LangGraph builder for Layer 1 (Enhancement) and Layer 2 (Deep Dive).

Graph structure:
  START -> agent -> [tool_calls?]
                    |-- YES -> tools -> [budget exceeded?]
                    |                    |-- YES -> force_output -> END
                    |                    +-- NO  -> agent
                    +-- NO  -> [valid draft?]
                               |-- YES -> END
                               +-- NO  -> agent (retry)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional, Callable

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from workflow.state import AgentState
from utils.text_cleaning import _scrub_competitor_mentions
from utils.cost_tracker import track
from utils import strip_preamble
from models.pipeline import AgentContext, EvidenceLedger, ClaimMap

logger = logging.getLogger(__name__)

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
    """Build and compile a LangGraph StateGraph for a research agent."""

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
            response = await asyncio.wait_for(
                llm_with_tools.ainvoke(state["messages"]),
                timeout=120.0
            )
            track(f"L{layer} agent", response)
        except Exception as e:
            logger.error(f"[Agent L{layer}] LLM call failed: {e}")
            repair_msgs = []
            if state["messages"]:
                last = state["messages"][-1]
                if hasattr(last, "tool_calls") and last.tool_calls:
                    for tc in last.tool_calls:
                        repair_msgs.append(ToolMessage(
                            content=f"Tool call failed due to error: {e}",
                            tool_call_id=tc["id"],
                        ))
            error_msg = HumanMessage(
                content=f"Error occurred: {e}. Write your report with available data."
            )
            return {"messages": repair_msgs + [error_msg]}

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

        new_count = state["tool_call_count"] + new_tool_count

        return {
            "messages": tool_messages,
            "tool_call_count": new_count,
        }

    # ── Node: force_output ─────────────────────────────────────────────────
    async def force_output_node(state: AgentState) -> dict:
        """Call LLM without tools to force a final report."""
        notify("forcing", "Requesting final report...")

        messages = list(state["messages"])
        if messages and hasattr(messages[-1], "tool_calls") and messages[-1].tool_calls:
            for tc in messages[-1].tool_calls:
                messages.append(ToolMessage(
                    content="Budget exceeded — tool call skipped.",
                    tool_call_id=tc["id"],
                ))

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
            response = await asyncio.wait_for(
                llm.ainvoke(messages + [force_msg]),
                timeout=120.0
            )
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
                msg = HumanMessage(
                    content=(
                        f"CRITICAL: You have done {searches_done} searches but recorded ZERO findings. "
                        "Your search results contain useful data — you MUST call record_finding() now.\n\n"
                        "EXAMPLE: After a search about cloud market size returns results mentioning '$600B', call:\n"
                        '  record_finding(claim_id="s1_c01", finding="Global cloud market reached $600B in 2025", '
                        'evidence_type="quantifies", confidence="high")\n\n'
                        f"Claims needing evidence:\n{uncovered_list}\n\n"
                        "Follow the 3-step cycle: SEARCH -> SCRAPE -> RECORD. Do it NOW."
                    )
                )
            else:
                msg = HumanMessage(
                    content=(
                        f"STOP. Coverage is only {coverage:.0%}. "
                        f"You have done {searches_done} searches and {scrapes_done} scrapes, "
                        f"but {len(uncovered)} claims still have NO evidence.\n\n"
                        f"Claims still needing evidence:\n{uncovered_list}\n\n"
                        "Follow the 3-step cycle: SEARCH -> SCRAPE -> RECORD. "
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

        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            if state["tool_call_count"] >= state["max_tool_calls"]:
                return "force_output"
            return "tools"

        if isinstance(last_msg, HumanMessage):
            msg_text = last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content)
            if "Error occurred:" in msg_text and state["retries"] >= state["max_retries"]:
                return "force_output"

        content = last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content)
        content = content.strip()

        if not state.get("forced_search", False) and ctx:
            searches_done = sum(
                1 for tc in ctx.tool_calls_log if tc.get("tool") == "search_web"
            )
            scrapes_done = sum(
                1 for tc in ctx.tool_calls_log if tc.get("tool") == "scrape_page"
            )

            if ledger is not None and claim_map is not None:
                coverage = ledger.coverage_score(claim_map)
                findings_count = len(ledger.entries)
                if searches_done >= 3 and findings_count == 0:
                    return "force_search"
                if coverage < 0.7 and searches_done < 40:
                    return "force_search"
            elif searches_done < 5 or scrapes_done < 2:
                return "force_search"

        if content and len(content) > 100:
            candidate = strip_preamble(content)
            word_count = len(candidate.split())

            if word_count < state["min_word_count"] and state["retries"] < state["max_retries"]:
                return "reject_draft"

            return "accept_draft"

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
        draft = _scrub_competitor_mentions(draft)
        word_count = len(draft.split())
        notify("drafted", f"Report: {word_count} words")
        return {"draft": draft}

    # ── Build the graph ────────────────────────────────────────────────────

    graph = StateGraph(AgentState)

    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("force_output", force_output_node)
    graph.add_node("budget_nudge", budget_nudge_node)
    graph.add_node("force_search", force_search_node)
    graph.add_node("reject_draft", reject_draft_node)
    graph.add_node("accept_draft", accept_draft_node)

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
