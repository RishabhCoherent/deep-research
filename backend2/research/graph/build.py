"""Build the LangGraph DAG for the full 8-agent research pipeline."""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from pathlib import Path

from research.core.types import RunState
from research.graph.nodes import a1_node, a2_node, a3_node, a4_node, a5_node


def _get_checkpointer(db_path: str | None = None):
    """Return a SQLite checkpointer for run persistence."""
    if db_path is None:
        cache_dir = Path.home() / ".research" / "checkpoints"
        cache_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(cache_dir / "research.db")
    return SqliteSaver.from_conn_string(db_path)


def build_graph(*, checkpointer=None):
    """Compile and return the LangGraph StateGraph.

    Currently implements nodes: a1_refiner → a2_questions → a3_topic | a4_market | a5_news.
    Stub nodes (a6–a8) return state unchanged until implemented.
    """
    workflow = StateGraph(RunState)

    # ── Implemented nodes ──────────────────────────────────────────────────
    workflow.add_node("a1_refiner", a1_node)
    workflow.add_node("a2_questions", a2_node)
    workflow.add_node("a3_topic", a3_node)
    workflow.add_node("a4_market", a4_node)
    workflow.add_node("a5_news", a5_node)

    # ── Stub nodes (return state unchanged) ────────────────────────────────
    async def _stub(state: RunState, **_):
        return {}

    for name in ("a6_consolidator",
                 "a7_validator", "a8_causation"):
        workflow.add_node(name, _stub)

    # ── Edges ───────────────────────────────────────────────────────────────
    workflow.set_entry_point("a1_refiner")
    workflow.add_edge("a1_refiner", "a2_questions")

    # Fan-out: A2 → A3 / A4 / A5 in parallel
    workflow.add_edge("a2_questions", "a3_topic")
    workflow.add_edge("a2_questions", "a4_market")
    workflow.add_edge("a2_questions", "a5_news")

    # Join: A3/A4/A5 → A6
    workflow.add_edge("a3_topic", "a6_consolidator")
    workflow.add_edge("a4_market", "a6_consolidator")
    workflow.add_edge("a5_news", "a6_consolidator")

    # Sequential tail
    workflow.add_edge("a6_consolidator", "a7_validator")
    workflow.add_edge("a7_validator", "a8_causation")
    workflow.add_edge("a8_causation", END)

    if checkpointer is None:
        checkpointer = _get_checkpointer()

    return workflow.compile(checkpointer=checkpointer)
