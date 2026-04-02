"""
Phase 2: INVESTIGATE — Parallel sub-question research.

Sub-questions are researched in parallel batches of PARALLEL_BATCH_SIZE.
Each batch gets its own LangGraph instance but shares the ResearchBoard
(with asyncio.Lock for budget and status synchronization).

Graph flow per question:
  pick_question → think → research (agent+tools) → reflect → record
"""

import asyncio
import logging
import time

from config import get_llm, set_model_tier
from models.analyst import ResearchBoard, ResearchTrace, SubQuestion
from workflow.cmi_expert_graph import build_analyst_graph
from layers.analyst.tree_research import expand_research_tree
from utils.cost_tracker import track
from models.pipeline import Source

logger = logging.getLogger(__name__)

PARALLEL_BATCH_SIZE = 3  # Research 3 sub-questions simultaneously


async def _research_single_question(
    sq: SubQuestion,
    board: ResearchBoard,
    sources: list[Source],
    budget_lock: asyncio.Lock,
    notify=None,
    trace: ResearchTrace | None = None,
) -> None:
    """Research a single sub-question using its own graph instance."""
    set_model_tier("premium")
    llm = get_llm("writer")

    # Build a separate graph instance for this question
    graph = build_analyst_graph(
        llm=llm,
        board=board,
        sources=sources,
        notify=notify,
        trace=trace,
        budget_lock=budget_lock,
        single_sq_id=sq.id,  # Only research this one question
    )

    initial_state = {
        "messages": [],
        "current_sq_id": sq.id,
        "hypothesis": "",
        "would_change_mind": "",
        "search_results_text": "",
        "scraped_text": "",
        "research_tool_calls": 0,
        "phase": "think",  # Skip pick — go straight to think for this question
    }

    try:
        await graph.ainvoke(initial_state)
    except Exception as e:
        logger.error(f"[Analyst] Research failed for {sq.id}: {e}")
        sq.status = "gap"
        sq.answer = f"GAP: Research failed — {str(e)[:100]}"
        sq.confidence = 0.0


async def investigate(
    board: ResearchBoard,
    topic: str,
    sources: list[Source],
    notify=None,
    brief: str = "",
    trace: ResearchTrace | None = None,
) -> None:
    """Run parallel investigation of all sub-questions.

    Sub-questions are processed in batches of PARALLEL_BATCH_SIZE.
    Each batch runs simultaneously, sharing the board via asyncio.Lock.
    """
    if notify:
        notify("investigate", "Starting structured research with reasoning loop...")

    # Lock for shared board state (budget, searches_done, etc.)
    budget_lock = asyncio.Lock()

    # Sort questions by priority (P1 first)
    pending = sorted(
        [sq for sq in board.framework.sub_questions if sq.needs_research],
        key=lambda sq: sq.priority
    )

    total = len(pending)
    processed = 0

    # Process in parallel batches
    for batch_start in range(0, total, PARALLEL_BATCH_SIZE):
        batch = pending[batch_start:batch_start + PARALLEL_BATCH_SIZE]

        # Check budget before starting batch
        if board.budget_remaining < 6:
            logger.info(f"[Analyst] Budget too low ({board.budget_remaining} remaining), stopping investigation")
            break

        batch_ids = ", ".join(sq.id for sq in batch)
        processed += len(batch)
        if notify:
            notify("investigate",
                   f"Q{processed}/{total} [P{batch[0].priority}]: "
                   f"Researching {len(batch)} questions in parallel...")

        # Mark all as researching
        for sq in batch:
            sq.status = "researching"

        # Run batch in parallel
        tasks = [
            _research_single_question(
                sq=sq,
                board=board,
                sources=sources,
                budget_lock=budget_lock,
                notify=notify,
                trace=trace,
            )
            for sq in batch
        ]

        await asyncio.gather(*tasks)

        # Log batch results
        for sq in batch:
            if sq.status == "answered":
                logger.info(f"[Analyst] {sq.id} answered (conf={sq.confidence:.0%})")
            else:
                logger.info(f"[Analyst] {sq.id} status={sq.status}")

    # Mark remaining pending questions as gaps
    for sq in board.framework.sub_questions:
        if sq.status in ("pending", "researching"):
            sq.status = "gap"
            sq.answer = "GAP: Budget exhausted before researching"
            sq.confidence = 0.0

    answered = len(board.framework.answered_questions())
    total = len(board.framework.sub_questions)
    logger.info(
        f"[Analyst] Investigation complete: {answered}/{total} answered, "
        f"{len(board.evidence)} evidence, {board.searches_done} searches, "
        f"{board.scrapes_done} scrapes ({board.scrapes_failed} failed)"
    )

    if notify:
        notify("investigate",
               f"Research complete: {len(board.evidence)} findings, "
               f"{board.coverage:.0%} coverage")

    # ── Recursive Tree Expansion ───────────────────────────────────────────
    if board.budget_remaining >= 10:
        set_model_tier("premium")
        expand_llm = get_llm("writer")
        if notify:
            notify("investigate",
                   "Evaluating research depth — going deeper on uncertain findings...")
        try:
            await expand_research_tree(
                board=board,
                sources=sources,
                notify=notify,
                trace=trace,
                llm=expand_llm,
            )
        except Exception as e:
            logger.error(f"[Analyst] Tree expansion failed: {e}")
            import traceback
            traceback.print_exc()

        new_answered = len(board.framework.answered_questions())
        new_evidence = len(board.evidence)
        tree = board.research_tree
        logger.info(
            f"[Analyst] After tree expansion: {new_answered}/{total} answered, "
            f"{new_evidence} evidence, {tree.total_nodes} nodes, "
            f"max depth {tree.max_depth_reached}"
        )
