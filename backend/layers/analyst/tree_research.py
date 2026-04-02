"""
Recursive Tree Research — deep expansion after the flat sub-question loop.

After the main think→search→reflect loop finishes all root SubQuestions,
this module evaluates each result and decides whether to go deeper:

  - Confidence < 55% on P1/P2 → spawn 1-2 child queries
  - 2+ unresolved contradictions → spawn tiebreaker query
  - Comparison/list question with < 3 data points → spawn entity-specific queries
  - Surprising finding → spawn verification query

Each child is researched via its own think→search→reflect cycle (no LangGraph —
just direct async LLM calls).  Children can go 1 level deeper (max depth = 2).

All new evidence is deposited into board.evidence with the correct sub_question_id
so the analyze/compose phases pick it up without any changes.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional
from urllib.parse import urlparse
import re

from models.analyst import (
    AnalystEvidence,
    Contradiction,
    ResearchBoard,
    ResearchNode,
    ResearchTrace,
    SubQuestion,
)
from tools.hybrid_scraper import hybrid_scrape
from utils.cost_tracker import track
from models.pipeline import Source
from utils import get_content, extract_json
from tools.search import search
from tools.source_classifier import get_source_tier
from tools.citation import is_banned_source

logger = logging.getLogger(__name__)

MAX_DEPTH = 1               # Only 1 level deep — prioritize breadth over depth
MAX_CHILDREN_PER_ROOT = 2   # Max 2 child questions per root (was 3)
MAX_CHILDREN_PER_CHILD = 0  # No grandchildren — save budget for unanswered roots
MAX_TOTAL_NODES = 12        # Hard cap (was 25) — leaves budget for flat investigation


# ── Prompts ───────────────────────────────────────────────────────────────────

_DECIDE_PROMPT = """\
You just researched a question. Decide if spawning child research nodes would \
meaningfully improve the answer quality.

QUESTION: {question}
PRIORITY: P{priority}
QUESTION TYPE: {answer_type}
ANSWER: {answer}
CONFIDENCE: {confidence:.0%}
UNRESOLVED CONTRADICTIONS: {contradiction_count}
EVIDENCE PIECES: {evidence_count}
BUDGET REMAINING: {budget}
CURRENT DEPTH: {depth} / {max_depth}

GO DEEPER when:
- Confidence < 55% on a P1 or P2 question
- 2+ unresolved contradictions need a tiebreaker source
- A comparison/list question has fewer than 3 data points
- A surprising finding is worth verifying with a second source

STAY when:
- Confidence ≥ 70%
- Budget < 12
- Depth is already at max ({max_depth})
- P3 priority question
- Data simply doesn't exist (marked as gap)

Output ONLY valid JSON (no surrounding text):
If not expanding:
{{"should_expand": false, "reason": "one line", "child_queries": []}}

If expanding:
{{
  "should_expand": true,
  "reason": "one line",
  "child_queries": [
    {{
      "query": "specific follow-up question to investigate",
      "why": "vague_finding | contradiction | thin_data | surprising_data | missing_entity",
      "trigger_finding": "the finding that triggered this, ≤30 words"
    }}
  ]
}}"""


_NODE_THINK_PROMPT = """\
You are a senior analyst doing a focused follow-up investigation.

PARENT QUESTION: {parent_question}
PARENT ANSWER: {parent_answer}
FOLLOW-UP QUESTION: {query}
REASON FOR DIGGING DEEPER: {why_created}
TRIGGER: {trigger_finding}

Form a specific hypothesis. Output ONLY valid JSON:
{{
  "hypothesis": "I expect to find...",
  "search_queries": ["specific query 1", "specific query 2"],
  "would_change_mind": "I would revise my view if..."
}}"""


_NODE_REFLECT_PROMPT = """\
You are a senior analyst evaluating follow-up research findings.

FOLLOW-UP QUESTION: {query}
YOUR HYPOTHESIS: {hypothesis}
PARENT QUESTION: {parent_question}
PARENT ANSWER (what we were trying to improve): {parent_answer}

SEARCH RESULTS:
{search_results}

SCRAPED CONTENT:
{scraped_content}

Evaluate and output ONLY valid JSON:
{{
  "findings": [
    {{
      "data_point": "specific fact or number found",
      "source_title": "Source Name",
      "source_url": "https://...",
      "source_tier": 2,
      "confirms_hypothesis": true,
      "confidence": 0.7
    }}
  ],
  "contradictions": [
    {{"description": "Source A says X, Source B says Y"}}
  ],
  "answer": "direct answer to the follow-up question",
  "confidence": 0.75,
  "resolves_parent_issue": true,
  "how_it_helps_parent": "this resolves the contradiction by..."
}}"""


# ── Public entry point ────────────────────────────────────────────────────────

async def expand_research_tree(
    board: ResearchBoard,
    sources: list[Source],
    notify,
    trace: Optional[ResearchTrace],
    llm,
) -> None:
    """Expand the research tree by going deeper on low-confidence nodes.

    Called after the flat SubQuestion loop completes.  Mutates board in-place.
    """
    tree = board.research_tree

    # Step 1: create root nodes for every researched SubQuestion
    for sq in board.framework.sub_questions:
        if sq.needs_research:
            continue  # Still pending — skip
        node = ResearchNode(
            depth=0,
            query=sq.question,
            sq_id=sq.id,
            why_created="root",
            answer=sq.answer,
            confidence=sq.confidence,
            status="complete" if sq.status == "answered" else "dead-end",
            hypothesis=sq.hypothesis,
            search_queries=list(sq.search_queries),
        )
        node.evidence_ids = list(sq.evidence_ids)
        tree.add_node(node)
        tree.sq_to_root[sq.id] = node.id
        _emit_node_created(notify, node)
        _emit_node_complete(notify, node)

    if tree.total_nodes == 0:
        return

    if notify:
        notify("node_graph", f"Research tree built: {tree.total_nodes} root nodes")

    # Step 2: decide which root nodes to expand
    # But ONLY if all questions have been attempted — breadth first
    unanswered = [sq for sq in board.framework.sub_questions
                  if sq.status in ("pending", "researching")]
    if unanswered:
        logger.info(f"[TreeResearch] {len(unanswered)} questions still unanswered — skipping tree expansion to preserve budget")
        return

    if board.budget_remaining < 12:
        logger.info("[TreeResearch] Budget too low for expansion, skipping")
        return

    for sq in board.framework.sub_questions:
        if board.budget_remaining < 10 or tree.total_nodes >= MAX_TOTAL_NODES:
            break

        # Only expand P1 and P2 questions
        if sq.priority == 3:
            continue

        root_node_id = tree.sq_to_root.get(sq.id)
        if not root_node_id:
            continue
        root_node = tree.get_node(root_node_id)
        if not root_node:
            continue

        contradiction_count = sum(
            1 for c in board.contradictions
            if c.sub_question_id == sq.id and not c.resolved
        )
        evidence_count = len([e for e in board.evidence if e.sub_question_id == sq.id])

        should_expand, child_queries = await _decide_expansion(
            sq=sq,
            node=root_node,
            contradiction_count=contradiction_count,
            evidence_count=evidence_count,
            board=board,
            llm=llm,
            depth=0,
        )

        if not should_expand or not child_queries:
            continue

        logger.info(f"[TreeResearch] Expanding {sq.id}: {len(child_queries)} children queued")

        # Step 3: research each child
        for child_data in child_queries[:MAX_CHILDREN_PER_ROOT]:
            if board.budget_remaining < 8 or tree.total_nodes >= MAX_TOTAL_NODES:
                break

            child = ResearchNode(
                parent_id=root_node.id,
                depth=1,
                query=child_data.get("query", ""),
                why_created=child_data.get("why", "vague_finding"),
                trigger_finding=child_data.get("trigger_finding", ""),
                sq_id=sq.id,
                status="pending",
            )
            if not child.query:
                continue

            tree.add_node(child)

            _emit_node_created(notify, child)

            await _research_node(
                node=child,
                parent_sq=sq,
                parent_answer=root_node.answer,
                board=board,
                sources=sources,
                notify=notify,
                trace=trace,
                llm=llm,
            )

            _emit_node_complete(notify, child)

            # Step 4: optionally go one level deeper (depth 2)
            if (
                child.status == "complete"
                and child.confidence < 0.55
                and child.depth < MAX_DEPTH
                and board.budget_remaining >= 10
            ):
                gc_contradiction_count = sum(
                    1 for c in board.contradictions
                    if c.sub_question_id == sq.id and not c.resolved
                )
                gc_evidence_count = len([e for e in board.evidence if e.sub_question_id == sq.id])

                should_expand_2, gc_queries = await _decide_expansion(
                    sq=sq,
                    node=child,
                    contradiction_count=gc_contradiction_count,
                    evidence_count=gc_evidence_count,
                    board=board,
                    llm=llm,
                    depth=1,
                )

                if should_expand_2 and gc_queries:
                    for gc_data in gc_queries[:MAX_CHILDREN_PER_CHILD]:
                        if board.budget_remaining < 6 or tree.total_nodes >= MAX_TOTAL_NODES:
                            break

                        gc = ResearchNode(
                            parent_id=child.id,
                            depth=2,
                            query=gc_data.get("query", ""),
                            why_created=gc_data.get("why", "vague_finding"),
                            trigger_finding=gc_data.get("trigger_finding", ""),
                            sq_id=sq.id,
                        )
                        if not gc.query:
                            continue

                        tree.add_node(gc)
                        _emit_node_created(notify, gc)

                        await _research_node(
                            node=gc,
                            parent_sq=sq,
                            parent_answer=child.answer,
                            board=board,
                            sources=sources,
                            notify=notify,
                            trace=trace,
                            llm=llm,
                        )

                        _emit_node_complete(notify, gc)

    # Final summary
    depth_counts = {}
    for n in tree.nodes.values():
        depth_counts[n.depth] = depth_counts.get(n.depth, 0) + 1

    logger.info(
        f"[TreeResearch] Complete: {tree.total_nodes} nodes total, "
        f"max depth {tree.max_depth_reached}, "
        f"by depth: {depth_counts}, "
        f"total budget used: {board.tool_calls_used}"
    )

    if notify:
        notify(
            "node_graph",
            f"Deep research complete: {tree.total_nodes} nodes, "
            f"{tree.max_depth_reached} levels deep, "
            f"{len(board.evidence)} total evidence pieces",
        )


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _decide_expansion(
    sq: SubQuestion,
    node: ResearchNode,
    contradiction_count: int,
    evidence_count: int,
    board: ResearchBoard,
    llm,
    depth: int,
) -> tuple[bool, list[dict]]:
    """Ask the LLM whether this node should spawn children."""
    prompt = _DECIDE_PROMPT.format(
        question=node.query,
        priority=sq.priority,
        answer_type=sq.answer_type,
        answer=node.answer[:300] if node.answer else "No answer yet",
        confidence=node.confidence,
        contradiction_count=contradiction_count,
        evidence_count=evidence_count,
        budget=board.budget_remaining,
        depth=depth,
        max_depth=MAX_DEPTH,
    )

    try:
        response = await llm.ainvoke([{"role": "user", "content": prompt}])
        track("tree decide", response)
        board.tool_calls_used += 1

        raw = get_content(response)
        data = extract_json(raw)

        if not data or not isinstance(data, dict):
            return False, []

        should_expand = data.get("should_expand", False)
        child_queries = data.get("child_queries", [])

        if not isinstance(child_queries, list):
            child_queries = []

        logger.info(
            f"[TreeResearch] DECIDE {node.id} depth={depth}: "
            f"expand={should_expand} ({data.get('reason', '')[:60]}), "
            f"{len(child_queries)} queries"
        )
        return should_expand, child_queries

    except Exception as e:
        logger.warning(f"[TreeResearch] DECIDE failed for {node.id}: {e}")
        return False, []


async def _research_node(
    node: ResearchNode,
    parent_sq: SubQuestion,
    parent_answer: str,
    board: ResearchBoard,
    sources: list[Source],
    notify,
    trace: Optional[ResearchTrace],
    llm,
) -> None:
    """Run think → search+scrape → reflect on a single ResearchNode."""
    node.status = "exploring"
    start_t = time.time()

    # ── THINK ─────────────────────────────────────────────────────────────
    if notify:
        notify("node_thinking", json.dumps({
            "node_id": node.id,
            "query": node.query[:70],
            "depth": node.depth,
        }))

    hypothesis, queries = await _think_for_node(node, parent_sq, parent_answer, llm)
    node.hypothesis = hypothesis
    node.search_queries = queries

    if trace:
        trace.add("think", f"[Depth {node.depth}] {node.query[:50]}", {
            "question": node.query,
            "node_id": node.id,
            "depth": node.depth,
            "why_created": node.why_created,
            "hypothesis": hypothesis,
            "search_queries": queries[:2],
        }, sq_id=node.sq_id or "")

    # ── RESEARCH (search + scrape) ─────────────────────────────────────────
    search_results_text, scraped_text = await _search_and_scrape(
        node=node,
        queries=queries,
        board=board,
        sources=sources,
        notify=notify,
        trace=trace,
    )

    # ── REFLECT ───────────────────────────────────────────────────────────
    await _reflect_for_node(
        node=node,
        parent_sq=parent_sq,
        parent_answer=parent_answer,
        search_results_text=search_results_text,
        scraped_text=scraped_text,
        board=board,
        trace=trace,
        llm=llm,
    )

    elapsed = round(time.time() - start_t, 1)
    logger.info(
        f"[TreeResearch] Node {node.id} depth={node.depth}: "
        f"status={node.status}, conf={node.confidence:.0%}, {elapsed}s"
    )


async def _think_for_node(
    node: ResearchNode,
    parent_sq: SubQuestion,
    parent_answer: str,
    llm,
) -> tuple[str, list[str]]:
    """Form hypothesis and search queries for a child node."""
    prompt = _NODE_THINK_PROMPT.format(
        parent_question=parent_sq.question,
        parent_answer=(parent_answer or "No answer yet")[:300],
        query=node.query,
        why_created=node.why_created.replace("_", " "),
        trigger_finding=node.trigger_finding or "See parent answer",
    )

    try:
        response = await llm.ainvoke([{"role": "user", "content": prompt}])
        track("tree think", response)

        raw = get_content(response)
        data = extract_json(raw)

        if data and isinstance(data, dict):
            hypothesis = data.get("hypothesis", "")
            queries = data.get("search_queries", [])
            if isinstance(queries, list) and queries:
                return hypothesis, [str(q) for q in queries[:3]]

    except Exception as e:
        logger.warning(f"[TreeResearch] THINK failed for {node.id}: {e}")

    # Fallback: use node query as the search query
    return f"Investigating: {node.query}", [node.query]


async def _search_and_scrape(
    node: ResearchNode,
    queries: list[str],
    board: ResearchBoard,
    sources: list[Source],
    notify,
    trace: Optional[ResearchTrace],
) -> tuple[str, str]:
    """Run 2 searches + scrape top results. Returns (search_text, scraped_text)."""
    search_results_text = ""
    scraped_text = ""
    urls_seen: set[str] = set()

    for query in queries[:2]:
        if board.budget_remaining < 4:
            break

        board.searches_done += 1
        board.tool_calls_used += 1

        if notify:
            notify("node_searching", json.dumps({
                "node_id": node.id,
                "query": query[:70],
                "depth": node.depth,
            }))

        try:
            results = await search(query, max_results=5, include_news=True)
        except Exception as e:
            logger.warning(f"[TreeResearch] search failed: {e}")
            continue

        results = [
            r for r in results
            if not is_banned_source(r.get("url", ""), r.get("title", ""))
            and "wikipedia.org" not in r.get("url", "").lower()
        ]

        if trace:
            trace.add("search", f"[D{node.depth}] {query[:50]}", {
                "query": query,
                "node_id": node.id,
                "depth": node.depth,
                "results": [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("snippet", "")[:150],
                        "tier": get_source_tier(r.get("url", "")),
                    }
                    for r in results[:5]
                ],
            }, sq_id=node.sq_id or "")

        for r in results[:4]:
            url = r.get("url", "")
            if not url:
                continue
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            tier = get_source_tier(url)
            tier_label = {1: "[T1]", 2: "[T2]", 3: "[T3]"}[tier]

            if url not in urls_seen:
                urls_seen.add(url)
                sources.append(Source(
                    url=url,
                    title=title,
                    snippet=snippet[:200],
                    publisher=_infer_publisher(url),
                    date=r.get("date", ""),
                    tier=tier,
                ))

            search_results_text += f"{tier_label} {title}\n  {url}\n  {snippet[:200]}\n\n"

        # Scrape top 2 results
        for r in results[:2]:
            url = r.get("url", "")
            if not url or url in urls_seen or board.budget_remaining < 3:
                break

            board.tool_calls_used += 1

            try:
                result = await hybrid_scrape(url)
            except Exception as e:
                logger.warning(f"[TreeResearch] scrape error {url[:50]}: {e}")
                board.scrapes_failed += 1
                continue

            if result["success"]:
                board.scrapes_done += 1
                content = result["content"]
                tier = get_source_tier(url)
                scraped_text += f"[T{tier}] SOURCE: {url}\n{content[:3000]}\n---\n"

                # Update existing source record (O(1) lookup)
                matching = next((s for s in sources if s.url == url), None)
                if matching:
                    matching.scraped_content = content[:8000]

                if trace:
                    trace.add("scrape", f"[D{node.depth}] {url[:50]}", {
                        "url": url,
                        "node_id": node.id,
                        "depth": node.depth,
                        "success": True,
                        "method": result["method"],
                        "content_length": len(content),
                        "content_preview": content[:200],
                    }, sq_id=node.sq_id or "")
            else:
                board.scrapes_failed += 1
                if trace:
                    trace.add("scrape", f"[D{node.depth}] FAIL {url[:50]}", {
                        "url": url,
                        "node_id": node.id,
                        "depth": node.depth,
                        "success": False,
                        "method": result["method"],
                        "content_length": 0,
                    }, sq_id=node.sq_id or "")

    return search_results_text, scraped_text


async def _reflect_for_node(
    node: ResearchNode,
    parent_sq: SubQuestion,
    parent_answer: str,
    search_results_text: str,
    scraped_text: str,
    board: ResearchBoard,
    trace: Optional[ResearchTrace],
    llm,
) -> None:
    """Evaluate findings and deposit evidence into the board."""
    if not search_results_text and not scraped_text:
        node.status = "dead-end"
        node.answer = "No relevant data found at this depth"
        node.confidence = 0.0
        if trace:
            trace.add("reflect", f"[D{node.depth}] Dead end: {node.query[:40]}", {
                "question": node.query,
                "node_id": node.id,
                "depth": node.depth,
                "answer": node.answer,
                "confidence": 0.0,
                "findings": [],
            }, sq_id=node.sq_id or "")
        return

    prompt = _NODE_REFLECT_PROMPT.format(
        query=node.query,
        hypothesis=node.hypothesis or "No specific hypothesis",
        parent_question=parent_sq.question,
        parent_answer=(parent_answer or "Unknown")[:300],
        search_results=search_results_text[:4000],
        scraped_content=scraped_text[:5000],
    )

    try:
        response = await llm.ainvoke([{"role": "user", "content": prompt}])
        track("tree reflect", response)
        board.tool_calls_used += 1

        raw = get_content(response)
        data = extract_json(raw)

    except Exception as e:
        logger.warning(f"[TreeResearch] REFLECT failed for {node.id}: {e}")
        node.status = "dead-end"
        node.answer = "Reflection failed"
        node.confidence = 0.0
        return

    if not data or not isinstance(data, dict):
        node.status = "dead-end"
        node.answer = "Could not parse reflection"
        node.confidence = 0.0
        return

    # Deposit findings as evidence on the parent SubQuestion
    for f in data.get("findings", []):
        if not isinstance(f, dict) or not f.get("data_point"):
            continue
        ev = AnalystEvidence(
            sub_question_id=node.sq_id or "",
            fact=f["data_point"],
            source_url=f.get("source_url", ""),
            source_title=f.get("source_title", ""),
            source_tier=f.get("source_tier", 3),
            evidence_type="confirmed" if f.get("confirms_hypothesis") else "disputed",
            confidence=f.get("confidence", 0.5),
            scrape_method=f"depth_{node.depth}",  # mark as deep evidence
        )
        board.evidence.append(ev)
        node.evidence_ids.append(ev.id)

        # Also add to the parent SubQuestion's evidence list
        for sq in board.framework.sub_questions:
            if sq.id == node.sq_id:
                sq.evidence_ids.append(ev.id)
                break

    # Record any new contradictions
    for ct in data.get("contradictions", []):
        if isinstance(ct, dict) and ct.get("description"):
            board.contradictions.append(Contradiction(
                sub_question_id=node.sq_id or "",
                description=ct["description"],
            ))

    # Update node answer
    answer = data.get("answer", "")
    confidence = data.get("confidence", 0.0)

    node.answer = answer
    node.confidence = confidence
    node.status = "complete" if confidence >= 0.3 else "dead-end"

    # If this child improves the parent sub-question's confidence, update it
    if data.get("resolves_parent_issue") and node.sq_id and confidence >= 0.5:
        for sq in board.framework.sub_questions:
            if sq.id == node.sq_id and sq.confidence < confidence:
                how_it_helps = data.get("how_it_helps_parent", "")
                if how_it_helps:
                    sq.answer = f"{sq.answer}\n\n[Deep verification at depth {node.depth}]: {how_it_helps}"
                sq.confidence = max(sq.confidence, confidence * 0.8)  # partial credit
                if sq.status == "gap" and confidence >= 0.5:
                    sq.status = "answered"
                break

    if trace:
        trace.add("reflect", f"[D{node.depth}] {node.query[:50]}", {
            "question": node.query,
            "node_id": node.id,
            "depth": node.depth,
            "why_created": node.why_created,
            "hypothesis": node.hypothesis,
            "findings": [
                {
                    "data_point": f.get("data_point", ""),
                    "source_title": f.get("source_title", ""),
                    "source_tier": f.get("source_tier", 3),
                    "confirms_hypothesis": f.get("confirms_hypothesis", False),
                    "confidence": f.get("confidence", 0),
                }
                for f in data.get("findings", [])
                if isinstance(f, dict)
            ],
            "contradictions": [
                c.get("description", "") for c in data.get("contradictions", [])
                if isinstance(c, dict)
            ],
            "answer": answer,
            "confidence": confidence,
            "resolves_parent_issue": data.get("resolves_parent_issue", False),
            "how_it_helps_parent": data.get("how_it_helps_parent", ""),
        }, sq_id=node.sq_id or "")


# ── SSE event helpers ─────────────────────────────────────────────────────────

def _emit_node_created(notify, node: ResearchNode) -> None:
    if not notify:
        return
    try:
        notify("node_created", json.dumps({
            "node_id": node.id,
            "parent_id": node.parent_id,
            "depth": node.depth,
            "query": node.query[:100],
            "why": node.why_created,
            "trigger_finding": node.trigger_finding[:80] if node.trigger_finding else "",
            "sq_id": node.sq_id or "",
        }))
    except Exception as e:
        logger.warning(f"[TreeResearch] Failed to emit node_created: {e}")


def _emit_node_complete(notify, node: ResearchNode) -> None:
    if not notify:
        return
    try:
        notify("node_complete", json.dumps({
            "node_id": node.id,
            "depth": node.depth,
            "status": node.status,
            "confidence": node.confidence,
            "answer": node.answer[:120] if node.answer else "",
            "evidence_count": len(node.evidence_ids),
        }))
    except Exception as e:
        logger.warning(f"[TreeResearch] Failed to emit node_complete: {e}")


# ── Utility ───────────────────────────────────────────────────────────────────

def _infer_publisher(url: str) -> str:
    try:
        domain = urlparse(url).netloc.lower()
        domain = re.sub(r"^www\.", "", domain)
        parts = domain.split(".")
        return parts[-2].capitalize() if len(parts) >= 2 else ""
    except Exception:
        return ""
