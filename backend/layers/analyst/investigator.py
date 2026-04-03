"""
Phase 2: INVESTIGATE — Recursive decomposition + parallel research.

Each sub-question is decomposed into 2-3 smaller parts, researched
individually, then combined. Sub-questions are processed in parallel
batches of PARALLEL_BATCH_SIZE.

Flow per question:
  decompose → [research part 1, research part 2, research part 3] → combine → record
"""

import asyncio
import logging
import time

from config import get_llm, set_model_tier
from models.analyst import (
    ResearchBoard, ResearchTrace, SubQuestion, ResearchNode, AnalystEvidence,
)
from workflow.cmi_expert_graph import build_analyst_graph
from utils.cost_tracker import track
from utils import get_content, extract_json
from models.pipeline import Source
from tools.search import search as web_search
from tools.hybrid_scraper import hybrid_scrape
from tools.source_classifier import get_source_tier
from tools.citation import is_banned_source

logger = logging.getLogger(__name__)

PARALLEL_BATCH_SIZE = 3  # Research 3 sub-questions simultaneously


# ── Decompose a question into parts ──────────────────────────────────────────

DECOMPOSE_PART_PROMPT = """QUESTION: {question}

Break this into smaller, directly answerable sub-parts. Each part should be specific enough to answer with a single web search.

How many parts depends on the question's complexity:
- Simple factual question → 1-2 parts (or don't decompose at all)
- Moderate question → 2-3 parts
- Complex multi-faceted question → 3-4 parts

Return ONLY valid JSON:
{{"parts": ["part 1 question", "part 2 question"], "reason": "why this many parts"}}"""


COMBINE_PROMPT = """ORIGINAL QUESTION: {question}

SUB-PART ANSWERS:
{part_answers}

Combine these into a single comprehensive answer to the original question.
Use specific data, names, and numbers from the parts. If parts contradict, note it.

Return ONLY valid JSON:
{{"answer": "your combined answer here", "confidence": 0.75}}"""


MAX_DEEP_DIVES = 2  # Max nodes that go deeper than depth 1 per run


def _should_go_deeper(answer: str, evidence: list, sq_priority: int, budget_remaining: int, depth: int) -> bool:
    """Decide if a researched part needs sub-decomposition for richer data."""
    if depth >= 2:          # Max depth 3 (0→1→2)
        return False
    if budget_remaining < 20:
        return False
    if sq_priority > 2:     # Only go deep on P1-P2 questions
        return False
    if len(evidence) < 2:   # Too few evidence items — need more
        return True
    # Check if answer is vague (no numbers or specific entities)
    import re
    has_numbers = bool(re.search(r'\d{2,}', answer))
    has_specifics = len(answer) > 200 and has_numbers
    if not has_specifics:
        return True
    return False


async def _decompose_question(question: str, llm, budget_lock, board) -> list[str]:
    """Break a question into 2-3 directly answerable parts."""
    messages = [
        {"role": "system", "content": "You output only valid JSON."},
        {"role": "user", "content": DECOMPOSE_PART_PROMPT.format(question=question)},
    ]

    response = await llm.ainvoke(messages)
    track("analyst decompose_part", response)
    async with budget_lock:
        board.tool_calls_used += 1

    data = extract_json(get_content(response))
    if data and isinstance(data.get("parts"), list):
        parts = [p for p in data["parts"] if isinstance(p, str) and len(p) > 10]
        if len(parts) >= 1:
            return parts[:4]  # Max 4 parts

    # Fallback: just return the original question as a single part
    return [question]


async def _research_part(
    part_question: str,
    sq: SubQuestion,
    board: ResearchBoard,
    sources: list[Source],
    budget_lock: asyncio.Lock,
    trace: ResearchTrace | None = None,
) -> tuple[str, list[AnalystEvidence]]:
    """Research a single part: search + scrape + extract findings.

    Returns (answer_text, evidence_list).
    """
    findings = []
    answer = ""

    # Check budget
    async with budget_lock:
        if board.budget_remaining < 4:
            return "(budget exhausted)", []
        board.tool_calls_used += 1  # for search

    # Search
    try:
        results = await web_search(part_question, max_results=5, include_news=True)
    except Exception as e:
        logger.warning(f"[Part] Search failed: {e}")
        return "(search failed)", []

    if not results:
        return "(no results found)", []

    # Filter banned sources
    results = [r for r in results if not is_banned_source(r.get("url", ""), r.get("title", ""))]

    async with budget_lock:
        board.searches_done += 1

    # Collect snippets as evidence
    search_text = ""
    for r in results[:5]:
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        url = r.get("url", "")
        tier = get_source_tier(url)

        if snippet and len(snippet) > 50:
            ev = AnalystEvidence(
                sub_question_id=sq.id,
                fact=snippet[:500],
                source_url=url,
                source_title=title,
                source_tier=tier,
                evidence_type="confirmed",
                confidence=0.6,
            )
            findings.append(ev)
            search_text += f"- {title}: {snippet[:200]}\n"

        # Track source
        if url and url not in {s.url for s in sources}:
            sources.append(Source(
                url=url, title=title, snippet=snippet[:200],
                tier=tier,
            ))

    # Scrape top result for deeper data
    scrape_data = None
    if results and board.budget_remaining >= 2:
        top_url = results[0].get("url", "")
        if top_url and not is_banned_source(top_url, ""):
            async with budget_lock:
                board.tool_calls_used += 1

            try:
                scrape_result = await hybrid_scrape(top_url)
                if scrape_result["success"]:
                    async with budget_lock:
                        board.scrapes_done += 1
                    content = scrape_result["content"][:4000]
                    search_text += f"\n--- SCRAPED: {content[:2000]}"
                    scrape_data = {
                        "url": top_url,
                        "success": True,
                        "method": scrape_result["method"],
                        "content_length": len(scrape_result["content"]),
                        "content_preview": content[:300],
                    }
                else:
                    async with budget_lock:
                        board.scrapes_failed += 1
                    scrape_data = {"url": top_url, "success": False, "method": scrape_result["method"]}
            except Exception as e:
                logger.warning(f"[Part] Scrape failed: {e}")

    answer = search_text[:2000] if search_text else "(no data found)"

    # Record a single bundled trace step for this part
    if trace:
        trace.add("part_research", f"Part: {part_question[:60]}", {
            "part_question": part_question,
            "search_query": part_question,
            "search_results": [
                {"title": r.get("title",""), "url": r.get("url",""),
                 "snippet": r.get("snippet","")[:150], "tier": get_source_tier(r.get("url",""))}
                for r in results[:5]
            ],
            "scrape": scrape_data,
            "evidence_found": [
                {"fact": e.fact[:200], "source_title": e.source_title, "source_url": e.source_url}
                for e in findings
            ],
            "answer_summary": answer[:300],
        }, sq_id=sq.id)

    return answer, findings


async def _combine_answers(question: str, part_questions: list[str], part_answers: list[str], llm, budget_lock, board) -> tuple[str, float]:
    """Combine part answers into a single answer for the original question."""
    parts_text = ""
    for q, a in zip(part_questions, part_answers):
        parts_text += f"\nPart: {q}\nAnswer: {a[:500]}\n"

    messages = [
        {"role": "system", "content": "You output only valid JSON."},
        {"role": "user", "content": COMBINE_PROMPT.format(
            question=question,
            part_answers=parts_text,
        )},
    ]

    response = await llm.ainvoke(messages)
    track("analyst combine", response)
    async with budget_lock:
        board.tool_calls_used += 1

    data = extract_json(get_content(response))
    if data:
        answer = data.get("answer", "")
        confidence = data.get("confidence", 0.6)
        return answer, confidence

    return "Could not combine answers.", 0.3


async def _research_single_question(
    sq: SubQuestion,
    board: ResearchBoard,
    sources: list[Source],
    budget_lock: asyncio.Lock,
    notify=None,
    trace: ResearchTrace | None = None,
) -> None:
    """Research a sub-question by decomposing into parts, researching each, then combining."""
    set_model_tier("premium")
    llm = get_llm("writer")

    # Step 1: Decompose into parts
    parts = await _decompose_question(sq.question, llm, budget_lock, board)
    logger.info(f"[Analyst] {sq.id} decomposed into {len(parts)} parts: {[p[:50] for p in parts]}")

    # Create root node for this sub-question in the tree
    tree = board.research_tree
    root_node = ResearchNode(
        parent_id="",
        depth=0,
        query=sq.question,
        why_created="root",
        trigger_finding="",
        sq_id=sq.id,
        status="exploring",
    )
    tree.add_node(root_node)
    tree.sq_to_root[sq.id] = root_node.id
    root_node_id = root_node.id

    if trace:
        trace.add("think", f"Decomposed: {sq.question[:50]}", {
            "question": sq.question,
            "parts": parts,
            "part_count": len(parts),
        }, sq_id=sq.id)

    # Step 2: Research each part (with selective deeper recursion)
    part_answers = []
    all_evidence = []
    deep_dive_count = 0  # Track how many parts went deeper

    async def _research_part_recursive(
        part_q: str, parent_node_id: str, depth: int, part_index: int,
    ) -> tuple[str, list[AnalystEvidence]]:
        """Research a part, optionally going deeper if the answer is weak."""
        nonlocal deep_dive_count

        if board.budget_remaining < 4:
            return "(budget exhausted)", []

        # Create node in tree
        child_node = ResearchNode(
            parent_id=parent_node_id,
            depth=depth,
            query=part_q,
            why_created="decomposition",
            trigger_finding=f"{'Sub-p' if depth > 1 else 'P'}art {part_index+1}",
            sq_id=sq.id,
            status="exploring",
        )
        tree.add_node(child_node)

        if notify:
            notify("node_created", __import__('json').dumps({
                "node_id": child_node.id, "parent_id": parent_node_id,
                "depth": depth, "query": part_q[:100],
                "why": "decomposition" if depth == 1 else "deep_dive",
                "sq_id": sq.id,
            }))

        # Research this part
        answer, evidence = await _research_part(
            part_q, sq, board, sources, budget_lock, trace
        )

        # Check if we should go deeper
        if (deep_dive_count < MAX_DEEP_DIVES
                and _should_go_deeper(answer, evidence, sq.priority, board.budget_remaining, depth)):

            logger.info(f"[Analyst] Going deeper on: {part_q[:50]} (depth {depth} → {depth+1})")
            deep_dive_count += 1

            # Decompose this part further
            sub_parts = await _decompose_question(part_q, llm, budget_lock, board)

            if len(sub_parts) > 1:
                # Research sub-parts
                sub_answers = []
                sub_evidence = []
                for j, sub_q in enumerate(sub_parts):
                    sub_ans, sub_ev = await _research_part_recursive(
                        sub_q, child_node.id, depth + 1, j
                    )
                    sub_answers.append(sub_ans)
                    sub_evidence.extend(sub_ev)

                # Combine sub-part answers into this part's answer
                if any(a for a in sub_answers if "(budget" not in a):
                    combined, conf = await _combine_answers(
                        part_q, sub_parts, sub_answers, llm, budget_lock, board
                    )
                    answer = combined
                    evidence = evidence + sub_evidence

        # Update node
        child_node.answer = answer[:500]
        child_node.status = "complete" if answer and "(budget" not in answer else "dead-end"
        child_node.confidence = 0.7 if child_node.status == "complete" else 0.0
        child_node.evidence_ids = [e.id for e in evidence]

        if notify:
            notify("node_complete", __import__('json').dumps({
                "node_id": child_node.id, "depth": depth,
                "status": child_node.status,
                "confidence": child_node.confidence,
                "answer": answer[:100],
                "evidence_count": len(evidence),
            }))

        return answer, evidence

    for i, part_q in enumerate(parts):
        if board.budget_remaining < 4:
            part_answers.append("(budget exhausted)")
            continue

        answer, evidence = await _research_part_recursive(
            part_q, root_node_id, depth=1, part_index=i
        )
        part_answers.append(answer)
        all_evidence.extend(evidence)

    # Step 3: Combine part answers
    if len([a for a in part_answers if "(budget" not in a and "(no data" not in a]) >= 1:
        combined_answer, confidence = await _combine_answers(
            sq.question, parts, part_answers, llm, budget_lock, board
        )
        sq.status = "answered"
        sq.answer = combined_answer
        sq.confidence = confidence

        if trace:
            trace.add("reflect", f"Combined: {sq.question[:50]}", {
                "question": sq.question,
                "parts": parts,
                "part_answers": [a[:200] for a in part_answers],
                "answer": combined_answer[:500],
                "confidence": confidence,
            }, sq_id=sq.id)
    else:
        sq.status = "gap"
        sq.answer = "GAP: Could not research any parts of this question"
        sq.confidence = 0.0

    # Add all evidence to board
    for ev in all_evidence:
        board.evidence.append(ev)
        sq.evidence_ids.append(ev.id)

    # Update root node with combined result
    root_node.answer = sq.answer[:500] if sq.answer else ""
    root_node.confidence = sq.confidence
    root_node.status = "complete" if sq.status == "answered" else "dead-end"
    root_node.evidence_ids = [e.id for e in all_evidence]

    logger.info(
        f"[Analyst] {sq.id}: {sq.status} (conf={sq.confidence:.0%}, "
        f"{len(all_evidence)} evidence, {len(parts)} parts)"
    )


async def investigate(
    board: ResearchBoard,
    topic: str,
    sources: list[Source],
    notify=None,
    brief: str = "",
    trace: ResearchTrace | None = None,
) -> None:
    """Run parallel investigation with recursive decomposition.

    Each sub-question is decomposed into parts, researched, and combined.
    Sub-questions are processed in parallel batches of PARALLEL_BATCH_SIZE.
    """
    if notify:
        notify("investigate", "Starting structured research with reasoning loop...")

    budget_lock = asyncio.Lock()

    # Sort by priority (P1 first)
    pending = sorted(
        [sq for sq in board.framework.sub_questions if sq.needs_research],
        key=lambda sq: sq.priority
    )

    total = len(pending)
    processed = 0

    for batch_start in range(0, total, PARALLEL_BATCH_SIZE):
        batch = pending[batch_start:batch_start + PARALLEL_BATCH_SIZE]

        if board.budget_remaining < 6:
            logger.info(f"[Analyst] Budget too low ({board.budget_remaining}), stopping")
            break

        processed += len(batch)
        if notify:
            notify("investigate",
                   f"Q{processed}/{total} [P{batch[0].priority}]: "
                   f"Researching {len(batch)} questions in parallel...")

        for sq in batch:
            sq.status = "researching"

        tasks = [
            _research_single_question(sq, board, sources, budget_lock, notify, trace)
            for sq in batch
        ]
        await asyncio.gather(*tasks)

        for sq in batch:
            if sq.status == "answered":
                logger.info(f"[Analyst] {sq.id} answered (conf={sq.confidence:.0%})")
            else:
                logger.info(f"[Analyst] {sq.id} status={sq.status}")

    # Mark remaining as gaps
    for sq in board.framework.sub_questions:
        if sq.status in ("pending", "researching"):
            sq.status = "gap"
            sq.answer = "GAP: Budget exhausted before researching"
            sq.confidence = 0.0

    answered = len(board.framework.answered_questions())
    total_sq = len(board.framework.sub_questions)
    logger.info(
        f"[Analyst] Investigation complete: {answered}/{total_sq} answered, "
        f"{len(board.evidence)} evidence, {board.searches_done} searches"
    )

    if notify:
        notify("investigate",
               f"Research complete: {len(board.evidence)} findings, "
               f"{board.coverage:.0%} coverage")

    # Notify tree is built
    tree = board.research_tree
    if notify:
        notify("node_graph",
               f"Deep research complete: {tree.total_nodes} nodes, "
               f"{tree.max_depth_reached} levels deep, "
               f"{len(board.evidence)} total evidence pieces")
