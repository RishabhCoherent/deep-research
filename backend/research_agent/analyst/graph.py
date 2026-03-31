"""
LangGraph for the Analyst Agent — with MANDATORY reasoning nodes.

The graph enforces: THINK → RESEARCH → REFLECT → RECORD for each sub-question.
The agent can't skip thinking. The agent can't skip reflection.

Graph structure:
  START → pick_question → think → research (agent+tools loop) → reflect → record
                ↑                                                          |
                +── (more questions AND budget remaining) ─────────────────+
                                                                           |
                                                                    (done) → END
"""

from __future__ import annotations

import logging
from typing import Annotated, TypedDict, Optional

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from research_agent.analyst.models import (
    AnalystEvidence, Contradiction, ResearchBoard, ResearchTrace, SubQuestion,
)
from research_agent.analyst.tools import hybrid_scrape
from research_agent.cost import track
from research_agent.models import Source
from research_agent.utils import get_content, extract_json, date_vars as _date_vars, format_tier
from tools.search import search
from tools.source_classifier import get_source_tier
from tools.citation import is_banned_source

logger = logging.getLogger(__name__)





# ── Graph State ───────────────────────────────────────────────────────────────

class AnalystState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    current_sq_id: str                # ID of the sub-question being researched
    hypothesis: str                   # Current hypothesis from THINK
    would_change_mind: str            # What would revise the hypothesis
    search_results_text: str          # Accumulated search results for REFLECT
    scraped_text: str                 # Accumulated scraped content for REFLECT
    research_tool_calls: int          # Tool calls in current research loop
    phase: str                        # "pick" | "think" | "research" | "reflect" | "record"


# ── Prompts for mandatory nodes ───────────────────────────────────────────────

THINK_SYSTEM = """You are a senior analyst. Before researching a question, you MUST form a hypothesis.

TODAY'S DATE: {current_date}
We are in {current_year}. Search for {current_year}-{next_year} data. Treat {last_year} and earlier as historical/actual, not projected.

Think like this: "Before I search, what do I EXPECT to find? What would CHANGE MY MIND?"

This is NOT optional. A good analyst never searches blindly."""

THINK_USER = """QUESTION TO RESEARCH: {question}
TYPE: {answer_type} | STRATEGY: {research_strategy}

WHAT YOU ALREADY KNOW (from prior questions):
{prior_knowledge}

Form your hypothesis. Output ONLY valid JSON:
{{
  "hypothesis": "I expect...",
  "search_queries": ["specific query 1", "specific query 2", "specific query 3"],
  "would_change_mind": "I would revise my view if...",
  "ideal_sources": ["type 1", "type 2"]
}}"""

RESEARCH_SYSTEM = """You are researching a specific question. You have search and scrape tools.

TODAY'S DATE: {current_date}
Search for {current_year}-{next_year} data. {last_year} data is historical, not projected.

QUESTION: {question}
YOUR HYPOTHESIS: {hypothesis}

RULES:
- Search with the queries from your hypothesis. If results are poor, REFORMULATE.
- Include the year {current_year} or {next_year} in your search queries to get fresh data.
- ALWAYS scrape at least 1-2 promising results. Snippets alone are NOT enough.
- Prioritize T1 (government, Reuters, Bloomberg) and T2 (industry, major news) sources.
- After 2-3 searches + scrapes, STOP and let the reflect phase evaluate.
- Do NOT call more than 8 tool calls for a single question."""

REFLECT_SYSTEM = """You are a senior analyst evaluating what you found against your hypothesis.

TODAY'S DATE: {current_date}
DATA FRESHNESS: We are in {current_year}. If a source says "projected to reach X by {last_year}", that is now HISTORICAL — the projection period has passed. Flag such data as outdated and note whether you found actual {current_year} data. Prefer the most recent numbers available."""

REFLECT_USER = """QUESTION: {question}
YOUR HYPOTHESIS: {hypothesis}
WHAT WOULD CHANGE YOUR MIND: {would_change_mind}

SEARCH RESULTS:
{search_results}

SCRAPED CONTENT:
{scraped_content}

Evaluate what you found. Output ONLY valid JSON:
{{
  "findings": [
    {{
      "data_point": "The specific fact/number found",
      "source_title": "Source Name",
      "source_url": "https://...",
      "source_tier": 2,
      "confirms_hypothesis": true,
      "confidence": 0.7,
      "reasoning": "Why I trust/distrust this"
    }}
  ],
  "contradictions": [
    {{"description": "Source A says X, Source B says Y"}}
  ],
  "answer": "My answer to the question based on evidence",
  "confidence": 0.75,
  "hypothesis_revised": false,
  "revised_hypothesis": ""
}}"""


# ── Build the graph ───────────────────────────────────────────────────────────

def build_analyst_graph(
    llm,
    board: ResearchBoard,
    sources: list[Source],
    notify=None,
    trace: ResearchTrace | None = None,
):
    """Build a LangGraph that enforces THINK → RESEARCH → REFLECT → RECORD."""

    urls_seen: set[str] = set()

    # ── Research tools (only available in research node) ──────────────────

    @tool
    async def search_web(query: str) -> str:
        """Search the web for data. Write queries like a journalist with specific terms and years."""
        if board.budget_remaining <= 0:
            return "BUDGET EXHAUSTED. Move to reflect and record your findings."
        board.searches_done += 1
        board.tool_calls_used += 1

        try:
            results = await search(query, max_results=5, include_news=True)
        except Exception as e:
            return f"Search failed: {e}"

        if not results:
            return "No results. Try different terms."

        results = [
            r for r in results
            if not is_banned_source(r.get("url", ""), r.get("title", ""))
            and "wikipedia.org" not in r.get("url", "").lower()
        ]

        # Record search trace
        if trace:
            trace.add("search", f"Search: {query[:60]}", {
                "query": query,
                "results": [
                    {"title": r.get("title", ""), "url": r.get("url", ""),
                     "snippet": r.get("snippet", "")[:200], "tier": get_source_tier(r.get("url", ""))}
                    for r in results[:5]
                ],
            }, sq_id=board.framework.sub_questions[
                next((i for i, sq in enumerate(board.framework.sub_questions)
                      if sq.status == "researching"), 0)
            ].id if any(sq.status == "researching" for sq in board.framework.sub_questions) else "")

        parts = []
        for r in results:
            url = r.get("url", "")
            if not url:
                continue
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            tier = get_source_tier(url)
            tier_label = format_tier(tier)

            if url not in urls_seen:
                urls_seen.add(url)
                sources.append(Source(
                    url=url, title=title, snippet=snippet[:200],
                    publisher=_infer_publisher(url),
                    date=r.get("date", ""), tier=tier,
                ))

            parts.append(f"{tier_label} {title}\n  URL: {url}\n  {snippet[:300]}")

        return "\n\n".join(parts) if parts else "No usable results."

    @tool
    async def scrape_page(url: str) -> str:
        """Scrape full text from a web page. Use this for promising search results."""
        if board.budget_remaining <= 0:
            return "BUDGET EXHAUSTED. Move to reflect and record your findings."
        board.tool_calls_used += 1

        if is_banned_source(url, ""):
            return "Competitor research firm URL — skip."

        result = await hybrid_scrape(url)
        # Find current sub-question for trace
        _current_sq_id = ""
        for _sq in board.framework.sub_questions:
            if _sq.status == "researching":
                _current_sq_id = _sq.id
                break

        if result["success"]:
            board.scrapes_done += 1
            content = result["content"]
            for s in sources:
                if s.url == url:
                    s.scraped_content = content[:8000]
                    break
            tier = get_source_tier(url)
            if trace:
                trace.add("scrape", f"Scraped: {url[:50]}", {
                    "url": url, "success": True, "method": result["method"],
                    "content_length": len(content),
                    "content_preview": content[:300],
                    "tier": tier,
                }, sq_id=_current_sq_id)
            return f"[T{tier}] {len(content)} chars via {result['method']}\n\n{content[:6000]}"
        else:
            board.scrapes_failed += 1
            if trace:
                trace.add("scrape", f"Failed: {url[:50]}", {
                    "url": url, "success": False, "method": result["method"],
                    "content_length": 0,
                }, sq_id=_current_sq_id)
            return f"Scrape failed ({result['method']}). Try another URL."

    research_tools = [search_web, scrape_page]
    llm_with_tools = llm.bind_tools(research_tools)
    tool_node = ToolNode(research_tools)

    # ── NODE: pick_question ───────────────────────────────────────────────

    async def pick_question(state: AnalystState) -> dict:
        """Select the next sub-question to research."""
        pending = board.framework.pending_questions()
        if not pending or board.budget_remaining < 8:
            return {"current_sq_id": "", "phase": "done"}

        sq = pending[0]  # Highest priority
        sq.status = "researching"

        answered = len(board.framework.answered_questions())
        total = len(board.framework.sub_questions)

        if notify:
            notify("investigate",
                   f"Q{answered+1}/{total} [P{sq.priority}]: {sq.question[:60]}...")

        logger.info(f"[Analyst] Picking: {sq.id} (P{sq.priority}): {sq.question[:60]}")

        return {
            "current_sq_id": sq.id,
            "hypothesis": "",
            "would_change_mind": "",
            "search_results_text": "",
            "scraped_text": "",
            "research_tool_calls": 0,
            "phase": "think",
        }

    # ── NODE: think (MANDATORY — no tools, just reasoning) ────────────────

    async def think(state: AnalystState) -> dict:
        """MANDATORY: Form hypothesis before researching."""
        sq = _get_sq(board, state["current_sq_id"])
        if not sq:
            return {"phase": "done"}

        # Build prior knowledge
        prior_lines = []
        for prev in board.framework.answered_questions()[-5:]:
            prior_lines.append(f"- {prev.question}: {prev.answer[:150]}")
        prior_knowledge = "\n".join(prior_lines) if prior_lines else "(none yet)"

        messages = [
            {"role": "system", "content": THINK_SYSTEM.format(**_date_vars())},
            {"role": "user", "content": THINK_USER.format(
                question=sq.question,
                answer_type=sq.answer_type,
                research_strategy=sq.research_strategy,
                prior_knowledge=prior_knowledge,
            )},
        ]

        response = await llm.ainvoke(messages)
        track("analyst think", response)
        board.tool_calls_used += 1

        raw = get_content(response)
        data = extract_json(raw)

        hypothesis = ""
        would_change = ""
        queries = sq.search_queries

        if data:
            hypothesis = data.get("hypothesis", "")
            would_change = data.get("would_change_mind", "")
            new_queries = data.get("search_queries", [])
            if new_queries:
                queries = new_queries
            sq.hypothesis = hypothesis
            sq.search_queries = queries

        logger.info(f"[Analyst] THINK {sq.id}: {hypothesis[:80]}")

        # Record trace
        if trace:
            trace.add("think", f"Hypothesis for: {sq.question[:50]}", {
                "question": sq.question,
                "priority": sq.priority,
                "answer_type": sq.answer_type,
                "research_strategy": sq.research_strategy,
                "hypothesis": hypothesis,
                "would_change_mind": would_change,
                "search_queries": queries[:3],
            }, sq_id=sq.id)

        # Inject hypothesis into messages for research phase
        return {
            "hypothesis": hypothesis,
            "would_change_mind": would_change,
            "messages": [
                SystemMessage(content=RESEARCH_SYSTEM.format(
                    question=sq.question,
                    hypothesis=hypothesis or "No specific hypothesis",
                    **_date_vars(),
                )),
                HumanMessage(content=(
                    f"Research this question now. Your queries:\n"
                    + "\n".join(f"- {q}" for q in queries[:3])
                    + "\n\nSearch, scrape top results, then stop after 6-8 tool calls."
                )),
            ],
            "phase": "research",
        }

    # ── NODE: research (agent + tools loop) ───────────────────────────────

    async def research_agent(state: AnalystState) -> dict:
        """Agent decides: search or scrape. Limited tool budget per question."""
        messages = state["messages"]
        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    async def research_tools_node(state: AnalystState) -> dict:
        """Execute tool calls and accumulate results for reflect."""
        result = await tool_node.ainvoke(state)

        # Accumulate search/scrape text for the reflect phase
        new_messages = result.get("messages", [])
        search_text = state.get("search_results_text", "")
        scraped_text = state.get("scraped_text", "")
        tool_calls = state.get("research_tool_calls", 0)

        for msg in new_messages:
            if hasattr(msg, "content") and isinstance(msg.content, str):
                content = msg.content
                if "[T1" in content or "[T2" in content or "[T3" in content:
                    if "chars via" in content:  # scrape result
                        scraped_text += "\n---\n" + content[:3000]
                    else:  # search result
                        search_text += "\n\n" + content[:2000]
                tool_calls += 1

        return {
            **result,
            "search_results_text": search_text,
            "scraped_text": scraped_text,
            "research_tool_calls": tool_calls,
        }

    def route_research(state: AnalystState) -> str:
        """After agent: continue research, or move to reflect."""
        messages = state["messages"]
        last = messages[-1] if messages else None
        tool_calls = state.get("research_tool_calls", 0)

        # If agent made tool calls and BOTH per-question and global budget remain
        if (isinstance(last, AIMessage) and last.tool_calls
                and tool_calls < 8
                and board.budget_remaining > 0):
            return "tools"

        # Done researching this question → reflect
        return "reflect"

    # ── NODE: reflect (MANDATORY — evaluate findings) ─────────────────────

    async def reflect(state: AnalystState) -> dict:
        """MANDATORY: Evaluate findings against hypothesis."""
        sq = _get_sq(board, state["current_sq_id"])
        if not sq:
            return {"phase": "record"}

        search_text = state.get("search_results_text", "")
        scraped_text = state.get("scraped_text", "")

        if not search_text and not scraped_text:
            # No data found — mark as gap
            logger.info(f"[Analyst] REFLECT {sq.id}: No data found, marking gap")
            sq.status = "gap"
            sq.answer = "GAP: No relevant data found"
            sq.confidence = 0.0
            if trace:
                trace.add("reflect", f"No data found for: {sq.question[:50]}", {
                    "question": sq.question, "answer": "GAP: No relevant data found",
                    "confidence": 0.0, "findings": [],
                }, sq_id=sq.id)
            return {"phase": "record"}

        messages = [
            {"role": "system", "content": REFLECT_SYSTEM.format(**_date_vars())},
            {"role": "user", "content": REFLECT_USER.format(
                question=sq.question,
                hypothesis=state.get("hypothesis", ""),
                would_change_mind=state.get("would_change_mind", ""),
                search_results=search_text[:4000],
                scraped_content=scraped_text[:6000],
            )},
        ]

        response = await llm.ainvoke(messages)
        track("analyst reflect", response)
        board.tool_calls_used += 1

        raw = get_content(response)
        data = extract_json(raw)

        if data:
            # Record findings
            for f in data.get("findings", []):
                if not isinstance(f, dict) or not f.get("data_point"):
                    continue
                ev = AnalystEvidence(
                    sub_question_id=sq.id,
                    fact=f["data_point"],
                    source_url=f.get("source_url", ""),
                    source_title=f.get("source_title", ""),
                    source_tier=f.get("source_tier", 3),
                    evidence_type="confirmed" if f.get("confirms_hypothesis") else "disputed",
                    confidence=f.get("confidence", 0.5),
                )
                board.evidence.append(ev)
                sq.evidence_ids.append(ev.id)

            # Record contradictions
            for ct in data.get("contradictions", []):
                if isinstance(ct, dict) and ct.get("description"):
                    board.contradictions.append(Contradiction(
                        sub_question_id=sq.id,
                        description=ct["description"],
                    ))

            # Update answer
            answer = data.get("answer", "")
            confidence = data.get("confidence", 0.0)
            if answer and confidence >= 0.3:
                sq.status = "answered"
                sq.answer = answer
                sq.confidence = confidence
                sq.reasoning = f"Hypothesis: {sq.hypothesis}. Conclusion: {answer}"
            else:
                sq.status = "gap"
                sq.answer = f"GAP (low confidence): {answer[:200]}"
                sq.confidence = confidence

            logger.info(
                f"[Analyst] REFLECT {sq.id}: {len(data.get('findings',[]))} findings, "
                f"conf={confidence:.0%}, status={sq.status}"
            )

            # Record trace
            if trace:
                trace.add("reflect", f"Evaluated: {sq.question[:50]}", {
                    "question": sq.question,
                    "hypothesis": state.get("hypothesis", ""),
                    "findings": [
                        {"data_point": f.get("data_point", ""), "source_title": f.get("source_title", ""),
                         "source_tier": f.get("source_tier", 3), "confirms_hypothesis": f.get("confirms_hypothesis", False),
                         "confidence": f.get("confidence", 0)}
                        for f in data.get("findings", []) if isinstance(f, dict)
                    ],
                    "contradictions": [c.get("description", "") for c in data.get("contradictions", []) if isinstance(c, dict)],
                    "answer": answer,
                    "confidence": confidence,
                    "hypothesis_revised": data.get("hypothesis_revised", False),
                    "revised_hypothesis": data.get("revised_hypothesis", ""),
                }, sq_id=sq.id)
        else:
            # Fallback: auto-record from raw search results
            sq.status = "gap"
            sq.answer = "GAP: Reflection failed"
            sq.confidence = 0.0
            if trace:
                trace.add("reflect", f"Reflection failed: {sq.question[:50]}", {
                    "question": sq.question, "answer": "GAP: Reflection failed",
                    "confidence": 0.0, "findings": [],
                }, sq_id=sq.id)

        return {"phase": "record"}

    # ── NODE: record (update board, decide next) ──────────────────────────

    async def record(state: AnalystState) -> dict:
        """Update the board and decide: next question or done."""
        sq = _get_sq(board, state["current_sq_id"])
        if sq:
            logger.info(
                f"[Analyst] RECORD {sq.id}: status={sq.status}, "
                f"{len(sq.evidence_ids)} evidence, conf={sq.confidence:.0%}"
            )

        # Check if we should continue
        pending = board.framework.pending_questions()
        if not pending or board.budget_remaining < 8:
            return {"phase": "done"}

        return {"phase": "pick"}

    # ── ROUTING ───────────────────────────────────────────────────────────

    def route_after_pick(state: AnalystState) -> str:
        if state.get("phase") == "done" or not state.get("current_sq_id"):
            return END
        return "think"

    def route_after_record(state: AnalystState) -> str:
        if state.get("phase") == "done":
            return END
        return "pick_question"

    # ── BUILD GRAPH ───────────────────────────────────────────────────────

    graph = StateGraph(AnalystState)

    graph.add_node("pick_question", pick_question)
    graph.add_node("think", think)
    graph.add_node("research_agent", research_agent)
    graph.add_node("research_tools", research_tools_node)
    graph.add_node("reflect", reflect)
    graph.add_node("record", record)

    # Edges
    graph.add_edge(START, "pick_question")
    graph.add_conditional_edges("pick_question", route_after_pick, {"think": "think", END: END})
    graph.add_edge("think", "research_agent")
    graph.add_conditional_edges("research_agent", route_research, {"tools": "research_tools", "reflect": "reflect"})
    graph.add_edge("research_tools", "research_agent")
    graph.add_edge("reflect", "record")
    graph.add_conditional_edges("record", route_after_record, {"pick_question": "pick_question", END: END})

    return graph.compile()


def _get_sq(board: ResearchBoard, sq_id: str) -> Optional[SubQuestion]:
    """Look up a sub-question by ID."""
    for sq in board.framework.sub_questions:
        if sq.id == sq_id:
            return sq
    return None


def _infer_publisher(url: str) -> str:
    import re
    from urllib.parse import urlparse
    try:
        domain = urlparse(url).netloc.lower()
        domain = re.sub(r'^www\.', '', domain)
        parts = domain.split('.')
        return parts[-2].capitalize() if len(parts) >= 2 else ""
    except Exception:
        return ""
