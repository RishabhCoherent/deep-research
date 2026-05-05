"""In-memory job manager for backend2's HTTP layer.

Each `POST /api/research` spawns an asyncio task running the LangGraph
pipeline. The task ID is the LangGraph thread_id (stable across resumes).
While the task runs, an `asyncio.Queue` collects events that the SSE
endpoint drains. After the task finishes, the final state is also reachable
from the SqliteSaver checkpoint DB — no separate persistence needed.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog

from research.core.state import create_initial_state
from research.graph.build import open_async_checkpointer, build_graph


_log = structlog.get_logger(__name__)


# ── Per-job state ──────────────────────────────────────────────────────────

@dataclass
class JobRecord:
    """One in-flight or recently-completed run."""
    job_id: str
    topic: str
    started_at: float
    task: asyncio.Task | None
    queue: asyncio.Queue   # events for /progress SSE
    finished_at: float | None = None
    error: str | None = None
    final_state: dict | None = None
    # Interactive variant-pick (mandatory after a1, before a2)
    variant_choice_event: asyncio.Event = field(default_factory=asyncio.Event)
    chosen_variant_query: str | None = None
    awaiting_variant: bool = False


# Global in-memory store. Persists for the lifetime of the uvicorn process.
_jobs: dict[str, JobRecord] = {}
_jobs_lock = asyncio.Lock()


def _gen_job_id() -> str:
    return str(uuid.uuid4())


# ── Event helpers ──────────────────────────────────────────────────────────

async def _emit(queue: asyncio.Queue, event: str, data: dict | str | None = None) -> None:
    """Push an SSE-shaped event onto the per-job queue."""
    payload = {"event": event, "data": data if data is not None else {}}
    try:
        await queue.put(payload)
    except Exception:
        pass


# ── Run lifecycle ──────────────────────────────────────────────────────────

_NODE_NAMES = (
    "a0_topic_profile", "a1_refiner", "a2_questions",
    "a3_topic", "a4_market", "a5_news",
    "a6_5_clusterer", "a6_consolidator",
    "a7_validator", "a8_causation", "a8_5_verifier",
)


async def _drain_stream(graph, payload, config: dict, queue: asyncio.Queue) -> None:
    """Translate LangGraph's astream_events output into backend2-native
    SSE events on the per-job queue. Returns when the stream ends (either
    completion or an interrupt)."""
    async for ev in graph.astream_events(payload, config=config, version="v2"):
        kind = ev.get("event")
        name = ev.get("name", "")
        if name in _NODE_NAMES:
            if kind == "on_chain_start":
                await _emit(queue, "node_started", {"node": name})
            elif kind == "on_chain_end":
                await _emit(queue, "node_done", {"node": name})


def _coerce_variants_for_emit(variants_sorted) -> list[dict]:
    """Variants on RunState may be ScoredVariant pydantic models OR rehydrated
    dicts (depending on whether we're reading live state vs a checkpoint).
    Normalise to a small JSON-friendly shape for the SSE payload."""
    out: list[dict] = []
    for i, sv in enumerate(variants_sorted or []):
        if hasattr(sv, "model_dump"):
            d = sv.model_dump()
        elif isinstance(sv, dict):
            d = sv
        else:
            continue
        var = d.get("variant") or {}
        out.append({
            "index":     i + 1,
            "text":      var.get("text") if isinstance(var, dict) else "",
            "composite": d.get("composite", 0.0),
            "reason":    d.get("reason", ""),
        })
    return out


async def _run_job(record: JobRecord, brief: str = "") -> None:
    """Coroutine body for one research run. Streams events into the per-job
    queue as nodes complete. Pauses at the interrupt before a2 to let the
    user pick a query variant; resumes once `record.variant_choice_event`
    fires (set by /select_variant)."""
    job_id = record.job_id
    queue = record.queue
    await _emit(queue, "job_started",
                {"job_id": job_id, "topic": record.topic, "brief": brief})
    try:
        async with open_async_checkpointer() as saver:
            graph = build_graph(checkpointer=saver)
            initial_state = create_initial_state(job_id, record.topic)

            config = {
                "configurable": {
                    "thread_id":         job_id,
                    # interactive_http=True tells a1_node to leave chosen_query
                    # empty so the graph's interrupt_before=["a2_questions"]
                    # actually pauses with variants visible in state.
                    "interactive_http":  True,
                },
                "recursion_limit": 50,
            }

            # Phase 1: run a0 + a1 until the graph hits the interrupt before a2.
            await _drain_stream(graph, initial_state, config, queue)

            # Read the checkpoint to see whether we're paused at the variant
            # pick or just finished early (e.g. a0/a1 timed out).
            tup = await saver.aget_tuple({"configurable": {"thread_id": job_id}})
            state = (tup.checkpoint or {}).get("channel_values", {}) if tup else {}
            variants = state.get("query_variants") or []
            already_chosen = bool(state.get("chosen_query"))

            if variants and not already_chosen:
                # Surface the variants to the frontend and wait for the pick.
                record.awaiting_variant = True
                await _emit(queue, "awaiting_variant_choice", {
                    "variants":       _coerce_variants_for_emit(variants),
                    "original_query": state.get("original_query") or record.topic,
                })

                await record.variant_choice_event.wait()
                record.awaiting_variant = False

                if not record.chosen_variant_query:
                    raise RuntimeError("variant_choice_event fired without a chosen query")

                # Patch the checkpointed state with the user's pick. LangGraph
                # records this as a partial update on the a1 channel.
                await graph.aupdate_state(
                    config,
                    {"chosen_query": record.chosen_variant_query},
                    as_node="a1_refiner",
                )
                await _emit(queue, "variant_chosen", {
                    "chosen_query": record.chosen_variant_query,
                })

                # Phase 2: resume from the interrupt (input=None tells LangGraph
                # to pick up from the latest checkpoint).
                await _drain_stream(graph, None, config, queue)

            # After the graph finishes, the final state lives in the
            # checkpointer. Read the latest checkpoint for this thread.
            final_tuple = await saver.aget_tuple(
                {"configurable": {"thread_id": job_id}}
            )
            if final_tuple is not None:
                cv = (final_tuple.checkpoint or {}).get("channel_values", {}) or {}
                record.final_state = dict(cv)

        record.finished_at = time.time()
        await _emit(queue, "done", {"success": True})
    except asyncio.CancelledError:
        record.finished_at = time.time()
        record.error = "cancelled"
        # Unblock anyone waiting on the variant pick (no-op if not waiting).
        record.variant_choice_event.set()
        with contextlib.suppress(Exception):
            await _emit(queue, "done",
                        {"success": False, "error": "cancelled"})
        raise
    except Exception as exc:
        _log.exception("job_failed", job_id=job_id, error=str(exc))
        record.finished_at = time.time()
        record.error = str(exc)
        record.variant_choice_event.set()
        await _emit(queue, "done",
                    {"success": False, "error": str(exc)[:300]})


async def start_job(topic: str, brief: str = "") -> str:
    """Create and launch a new job. Returns the job_id immediately; the run
    continues in the background asyncio task."""
    job_id = _gen_job_id()
    record = JobRecord(
        job_id=job_id,
        topic=topic,
        started_at=time.time(),
        task=None,
        queue=asyncio.Queue(),
    )
    async with _jobs_lock:
        _jobs[job_id] = record
    record.task = asyncio.create_task(_run_job(record, brief=brief))
    return job_id


async def get_job(job_id: str) -> JobRecord | None:
    async with _jobs_lock:
        return _jobs.get(job_id)


async def select_variant(job_id: str, index: int) -> tuple[bool, str]:
    """Resolve the user's variant pick for a paused job.

    Returns (ok, message). On success, signals `record.variant_choice_event`
    so `_run_job` can patch state.chosen_query and resume the graph.
    """
    rec = await get_job(job_id)
    if rec is None:
        return False, "unknown job_id"
    if not rec.awaiting_variant:
        return False, "job is not awaiting a variant choice"

    # Read the variants out of the latest checkpoint.
    async with open_async_checkpointer() as saver:
        tup = await saver.aget_tuple({"configurable": {"thread_id": job_id}})
        state = (tup.checkpoint or {}).get("channel_values", {}) if tup else {}
    variants = state.get("query_variants") or []
    if not variants:
        return False, "no variants in state"
    if not (1 <= index <= len(variants)):
        return False, f"index {index} out of range (1-{len(variants)})"

    # Variants in checkpoint state are dict-shaped (rehydrated from json)
    sv = variants[index - 1]
    if hasattr(sv, "model_dump"):
        sv = sv.model_dump()
    var = sv.get("variant") or {}
    chosen = var.get("text") if isinstance(var, dict) else None
    if not chosen:
        return False, "variant has no text"

    rec.chosen_variant_query = chosen
    rec.variant_choice_event.set()
    return True, chosen


async def cancel_job(job_id: str) -> bool:
    rec = await get_job(job_id)
    if rec and rec.task and not rec.task.done():
        rec.task.cancel()
        return True
    return False


async def stream_events(job_id: str) -> Any:
    """Async generator yielding SSE-shaped events for one job. Closes when
    a `done` event is observed or after a timeout."""
    rec = await get_job(job_id)
    if rec is None:
        return
    queue = rec.queue
    deadline = time.time() + 60 * 60   # 1-hour cap
    last_pulse = time.time()
    while True:
        timeout = max(0.0, min(15.0, deadline - time.time()))
        if timeout <= 0:
            return
        try:
            ev = await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            # Heartbeat to keep the SSE connection alive
            yield {"event": "heartbeat", "data": {}}
            last_pulse = time.time()
            continue
        yield ev
        if ev.get("event") == "done":
            return
