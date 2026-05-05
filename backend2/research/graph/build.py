"""Build the LangGraph DAG for the full 9-agent research pipeline."""

import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from research.core.types import RunState
from research.graph.nodes import (
    a0_node, a1_node, a2_node, a3_node, a4_node, a5_node, a6_node,
    a6_5_node, a7_node, a8_node, a8_5_node,
)


# Default SQLite path. Lives in backend2/ alongside the rest of this layer so
# a developer running `cd backend2 && python -m research.cli ...` writes
# checkpoints to a predictable spot. Override via env var `RESEARCH_CHECKPOINT_DB`.
_DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / ".checkpoints.db"


def _checkpoint_db_path() -> str:
    return os.environ.get("RESEARCH_CHECKPOINT_DB") or str(_DEFAULT_DB)


@asynccontextmanager
async def open_async_checkpointer():
    """Open the async SQLite checkpointer used by the CLI's `ainvoke` path.

    LangGraph requires AsyncSqliteSaver (built on aiosqlite) for async graph
    invocation; the synchronous SqliteSaver throws if used with `ainvoke`.
    Use this as an async context manager:

        async with open_async_checkpointer() as saver:
            graph = build_graph(checkpointer=saver)
            await graph.ainvoke(state, config=cfg)

    The DB path comes from $RESEARCH_CHECKPOINT_DB or defaults to
    backend2/.checkpoints.db. The graph writes a checkpoint AFTER EVERY NODE
    COMPLETES, so if a5 dies you can resume from where a4 left off
    (`run --resume <thread_id>`).
    """
    db_path = _checkpoint_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
        yield saver


def _get_checkpointer(persist: bool = True):
    """Return a sync checkpointer for sync callers (tests, list_runs).

    The async invocation path uses `open_async_checkpointer()` instead. This
    helper is mostly here for back-compat — older callers expected a
    synchronous saver from `build_graph()`.

    persist=True -> SqliteSaver (sync). NOT usable with `ainvoke`.
    persist=False -> in-memory only (for tests).
    """
    if not persist:
        return MemorySaver()

    db_path = _checkpoint_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False so the saver can be used from async/threaded
    # callers (LangGraph spawns workers when nodes run concurrently).
    conn = sqlite3.connect(db_path, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()   # idempotent — creates checkpoint tables on first use
    return saver


def build_graph(*, checkpointer=None, persist: bool = True):
    """Compile and return the LangGraph StateGraph.

    Full pipeline: a0_topic_profile -> a1_refiner -> a2_questions ->
    {a3_topic || a4_market || a5_news} -> a6_5_clusterer -> a6_consolidator
    -> a7_validator -> a8_causation -> a8_5_verifier -> END.

    a0 runs ONCE up front: produces a TopicProfile (topic_domain,
    expected_metric_kinds, key_dimensions, positive/negative_signals) that
    every downstream crew reads from RunState. This is what lets the same
    code handle market / clinical / policy / social-science topics without
    per-domain hardcoded vocabulary.

    A3-A5 fan out in parallel from a2 (each only reads sub_questions /
    topic_profile / chosen_query — all written by a0/a1/a2). They use
    operator.add reducers so concurrent writes to scratchpad_notes / claim
    buckets merge cleanly. Original sequential wiring existed to throttle
    Anthropic 429s; with OpenAI (current model_router pin) there is no such
    constraint, and the parallel fan-out roughly halves end-to-end wall time.

    a4 remains domain-conditional and skips itself for non-market topics
    (returns empty market_context bucket).
    """
    workflow = StateGraph(RunState)

    # ── Implemented nodes ──────────────────────────────────────────────────
    workflow.add_node("a0_topic_profile", a0_node)
    workflow.add_node("a1_refiner", a1_node)
    workflow.add_node("a2_questions", a2_node)
    workflow.add_node("a3_topic", a3_node)
    workflow.add_node("a4_market", a4_node)
    workflow.add_node("a5_news", a5_node)
    workflow.add_node("a6_consolidator", a6_node)
    workflow.add_node("a6_5_clusterer", a6_5_node)   # dimensional clustering (pure-Python)
    workflow.add_node("a7_validator", a7_node)
    workflow.add_node("a8_causation", a8_node)
    workflow.add_node("a8_5_verifier", a8_5_node)   # Phase 4c: fact-check brief

    # ── Edges ───────────────────────────────────────────────────────────────
    workflow.set_entry_point("a0_topic_profile")
    workflow.add_edge("a0_topic_profile", "a1_refiner")
    workflow.add_edge("a1_refiner", "a2_questions")

    # Parallel research branches: a3, a4, a5 fan out from a2 and merge at
    # a6.5. They read independent slices of RunState (chosen_query, intent,
    # sub_questions, topic_profile) and write into reducer-safe buckets
    # (topic_claims/market_claims/news_claims/scratchpad_notes all use
    # operator.add). LangGraph waits for ALL three to complete before
    # advancing to a6.5.
    workflow.add_edge("a2_questions", "a3_topic")
    workflow.add_edge("a2_questions", "a4_market")
    workflow.add_edge("a2_questions", "a5_news")

    # Sequential tail. NOTE: a6.5 (dimensional clustering) runs BEFORE a6
    # (consolidator) so a6's compose phase can read dimensional_clusters from
    # state and inject multi-source consensus values into the prose. Without
    # this ordering, the clusters would only appear as a tacked-on section
    # rather than being woven into the analyst narrative.
    workflow.add_edge("a3_topic", "a6_5_clusterer")
    workflow.add_edge("a4_market", "a6_5_clusterer")
    workflow.add_edge("a5_news", "a6_5_clusterer")
    workflow.add_edge("a6_5_clusterer", "a6_consolidator")
    workflow.add_edge("a6_consolidator", "a7_validator")
    workflow.add_edge("a7_validator", "a8_causation")
    workflow.add_edge("a8_causation", "a8_5_verifier")
    workflow.add_edge("a8_5_verifier", END)

    if checkpointer is None:
        checkpointer = _get_checkpointer(persist=persist)

    # interrupt_before a2_questions: a1 produces 4 ranked query variants and
    # the user MUST pick one before research starts. The HTTP layer detects
    # the pause, surfaces the variants over SSE, and resumes once
    # /select_variant fires with the chosen index. The CLI path uses a
    # configurable `auto_pick` (set in the run config) to skip the pause.
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["a2_questions"],
    )


def list_checkpointed_runs(limit: int = 20) -> list[dict]:
    """Inspect the checkpoint DB and return a summary of recent threads.

    Each thread_id corresponds to one graph invocation (one CLI run). For each
    we report the latest reached node and timestamp so the user can decide
    which run to --resume.
    """
    db_path = os.environ.get("RESEARCH_CHECKPOINT_DB") or str(_DEFAULT_DB)
    if not Path(db_path).exists():
        return []
    conn = sqlite3.connect(db_path, check_same_thread=False)
    saver = SqliteSaver(conn)
    runs: dict[str, dict] = {}
    try:
        # SqliteSaver.list yields CheckpointTuples; we group by thread_id and
        # keep the most recent one (highest checkpoint_id).
        for tup in saver.list(config=None, limit=200):
            cfg = tup.config.get("configurable", {}) if tup.config else {}
            tid = cfg.get("thread_id")
            if not tid:
                continue
            ts = (tup.checkpoint or {}).get("ts", "")
            existing = runs.get(tid)
            if existing is None or (ts and ts > existing.get("ts", "")):
                # Identify the latest node by inspecting state values
                state = (tup.checkpoint or {}).get("channel_values", {}) or {}
                # Heuristic: the most "advanced" run sets later RunState fields
                latest_node = "a0"
                if state.get("topic_profile"):                  latest_node = "a0_topic_profile"
                if state.get("query_variants"):                 latest_node = "a1_refiner"
                if state.get("sub_questions"):                  latest_node = "a2_questions"
                if state.get("topic_claims"):                   latest_node = "a3_topic"
                if state.get("market_claims") is not None and state.get("market_narrative") != "":
                    latest_node = "a4_market"
                if state.get("news_claims"):                    latest_node = "a5_news"
                if state.get("dimensional_clusters"):           latest_node = "a6_5_clusterer"
                if state.get("consolidated") is not None:       latest_node = "a6_consolidator"
                if state.get("validated_claims"):               latest_node = "a7_validator"
                if state.get("causations"):                     latest_node = "a8_causation"
                if state.get("verification") is not None:       latest_node = "a8_5_verifier"
                runs[tid] = {
                    "thread_id":  tid,
                    "ts":         ts,
                    "latest_node": latest_node,
                    "topic":      state.get("original_query", ""),
                }
    finally:
        conn.close()
    sorted_runs = sorted(runs.values(), key=lambda r: r.get("ts", ""), reverse=True)
    return sorted_runs[:limit]
