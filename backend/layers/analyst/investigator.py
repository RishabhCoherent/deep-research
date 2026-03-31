"""
Phase 2: INVESTIGATE — LangGraph with mandatory reasoning nodes.

The graph enforces: THINK → RESEARCH → REFLECT → RECORD for each sub-question.
The agent CANNOT skip thinking. The agent CANNOT skip reflection.

Graph flow:
  pick_question → think → research (agent+tools) → reflect → record → [next?] → pick_question
"""

import logging
import time

from config import get_llm, set_model_tier
from models.analyst import ResearchBoard, ResearchTrace
from workflow.cmi_expert_graph import build_analyst_graph
from layers.analyst.tree_research import expand_research_tree
from utils.cost_tracker import track
from models.pipeline import Source

logger = logging.getLogger(__name__)


async def investigate(
    board: ResearchBoard,
    topic: str,
    sources: list[Source],
    notify=None,
    brief: str = "",
    trace: ResearchTrace | None = None,
) -> None:
    """Run the structured reasoning graph to research all sub-questions.

    Mutates the board in-place: adds evidence, contradictions, judgments.
    """
    if notify:
        notify("investigate", "Starting structured research with reasoning loop...")

    set_model_tier("premium")
    llm = get_llm("writer")
    expand_llm = get_llm("writer")  # Same tier for depth expansion

    # Build the mandatory-reasoning graph
    graph = build_analyst_graph(
        llm=llm,
        board=board,
        sources=sources,
        notify=notify,
        trace=trace,
    )

    # Run the graph
    initial_state = {
        "messages": [],
        "current_sq_id": "",
        "hypothesis": "",
        "would_change_mind": "",
        "search_results_text": "",
        "scraped_text": "",
        "research_tool_calls": 0,
        "phase": "pick",
    }

    try:
        await graph.ainvoke(initial_state)
    except Exception as e:
        logger.error(f"[Analyst] Investigation graph failed: {e}")
        import traceback
        traceback.print_exc()

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
    # Evaluate low-confidence and contradicted questions and go deeper.
    if board.budget_remaining >= 10:
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
