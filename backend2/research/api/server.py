"""FastAPI server for backend2 (port 8001).

Mirrors the URL scheme of `backend/api.py` so the frontend's existing
fetch calls work with only a base-URL flip — but the JSON shapes are
backend2-native (Backend2Report instead of ComparisonReport).
"""
from __future__ import annotations

import json
import os
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from research.api.job_manager import (
    cancel_job, get_job, select_variant, start_job, stream_events,
)
from research.api.runstate_serializer import (
    history_summary_from_state, runstate_to_backend2_report,
)
from research.graph.build import (
    _checkpoint_db_path, list_checkpointed_runs, open_async_checkpointer,
)


_log = structlog.get_logger(__name__)


# ── App + CORS ─────────────────────────────────────────────────────────────

app = FastAPI(title="Deep Research backend2", version="1.0.0")

_FRONTEND_ORIGIN = os.environ.get("FRONTEND_URL")
_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
if _FRONTEND_ORIGIN:
    _CORS_ORIGINS.append(_FRONTEND_ORIGIN)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / response models ──────────────────────────────────────────────

class HealthResponse(BaseModel):
    openai: bool
    searxng: bool
    tavily: bool = False


class ResearchRequest(BaseModel):
    topic: str
    brief: str = ""
    max_layer: int = 3   # accepted for parity with old API; backend2 ignores


class ResearchResponse(BaseModel):
    job_id: str


# ── Health ────────────────────────────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Minimal health probe. Returns whether the OpenAI key is set + whether
    the local SearXNG container is reachable."""
    openai_ok = bool(os.environ.get("OPENAI_API_KEY"))
    searxng_ok = False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(
                os.environ.get("SEARXNG_URL", "http://localhost:8888")
            )
            searxng_ok = r.status_code < 500
    except Exception:
        searxng_ok = False
    return HealthResponse(openai=openai_ok, searxng=searxng_ok, tavily=False)


@app.get("/api/version")
async def version() -> dict:
    return {"version": "backend2-1.0.0"}


# ── Clustering-only iteration path ────────────────────────────────────────
#
# Skips a4/a5/a6/a7/a8/verifier — runs only what's needed to produce + cluster
# numeric claims, then writes an HTML report (claim_clustering visualiser).
# Synchronous: blocks for ~1-3 minutes per call, returns when the run is done.
# Use for fast iteration on extraction + clustering.

class ClusterOnlyRequest(BaseModel):
    topic: str
    brief: str = ""
    skip_a1_a2: bool = False   # skip query refinement + sub-question gen for fastest iter


class ClusterOnlyResponse(BaseModel):
    topic: str
    chosen_query: str
    html_path: str
    json_path: str
    html_url: str
    claims: int
    clusters: int
    multi_source: int
    five_plus_clusters: int
    top_size: int
    median_size: int
    cluster_size_distribution: dict[int, int]
    a0_seconds: float
    a1_seconds: float
    a2_seconds: float
    a3_seconds: float
    cluster_seconds: float
    total_seconds: float
    llm_calls: int
    llm_tokens_in: int
    llm_tokens_out: int
    llm_cost_usd: float
    provider: str


@app.post("/api/cluster", response_model=ClusterOnlyResponse)
async def cluster_only(req: ClusterOnlyRequest) -> ClusterOnlyResponse:
    """Run a0 -> a1 -> a2 -> a3 -> cluster on `topic`. Writes HTML to
    backend2/clustering_test_runs/<slug>/run.html and returns the path.

    Synchronous: this blocks until the run finishes (typically 1-3 minutes).
    """
    if not req.topic or not req.topic.strip():
        raise HTTPException(status_code=400, detail="topic must be non-empty")
    from research.api.cluster_only import run_clustering_only
    result = await run_clustering_only(
        req.topic.strip(),
        brief=req.brief,
        skip_a1_a2=req.skip_a1_a2,
    )
    _log.info("api.cluster_only.done",
              topic=req.topic[:80],
              claims=result["claims"],
              clusters=result["clusters"],
              cost_usd=result["llm_cost_usd"],
              total_s=result["total_seconds"])
    return ClusterOnlyResponse(**result)


@app.get("/api/cluster/runs/{slug}/run.html")
async def cluster_html(slug: str):
    """Serve the rendered HTML report for a clustering-only run."""
    from fastapi.responses import FileResponse
    from pathlib import Path as _Path
    base = _Path(__file__).resolve().parent.parent.parent / "clustering_test_runs"
    html_path = base / slug / "run.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail=f"no report at {slug}")
    return FileResponse(html_path, media_type="text/html")


@app.get("/api/cluster/runs/{slug}/run.json")
async def cluster_json(slug: str):
    """Serve the raw JSON for a clustering-only run."""
    from fastapi.responses import FileResponse
    from pathlib import Path as _Path
    base = _Path(__file__).resolve().parent.parent.parent / "clustering_test_runs"
    json_path = base / slug / "run.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail=f"no run at {slug}")
    return FileResponse(json_path, media_type="application/json")


# ── Research lifecycle ────────────────────────────────────────────────────

@app.post("/api/research", response_model=ResearchResponse)
async def start_research(req: ResearchRequest) -> ResearchResponse:
    """Spawn a new research job. Returns job_id immediately."""
    if not req.topic or not req.topic.strip():
        raise HTTPException(status_code=400, detail="topic must be non-empty")
    job_id = await start_job(topic=req.topic.strip(), brief=req.brief)
    _log.info("api.research_started", job_id=job_id, topic=req.topic[:80])
    return ResearchResponse(job_id=job_id)


@app.get("/api/research/{job_id}/progress")
async def research_progress(job_id: str, request: Request) -> EventSourceResponse:
    """SSE stream of node-level events. Backend2-native event names —
    NOT translated to legacy `layer_*` shapes. The frontend's
    `Backend2NodeProgress` component consumes these directly.
    """
    rec = await get_job(job_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="unknown job_id")

    async def event_gen():
        async for ev in stream_events(job_id):
            if await request.is_disconnected():
                break
            yield {
                "event": ev.get("event", "message"),
                "data": json.dumps(ev.get("data", {}), default=str),
            }

    return EventSourceResponse(event_gen())


@app.delete("/api/research/{job_id}")
async def cancel_research(job_id: str) -> dict:
    cancelled = await cancel_job(job_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="job not running")
    return {"cancelled": True, "job_id": job_id}


class SelectVariantRequest(BaseModel):
    index: int   # 1-based; matches the SSE payload's `index` field.


@app.post("/api/research/{job_id}/select_variant")
async def select_variant_route(job_id: str, req: SelectVariantRequest) -> dict:
    """Resolve the user's variant pick. The job pauses after a1 and
    publishes `awaiting_variant_choice` over SSE; the frontend POSTs here
    with the chosen index (1-4) to resume."""
    ok, msg = await select_variant(job_id, req.index)
    if not ok:
        # 404 for unknown jobs, 400 for index errors / wrong state
        status = 404 if msg == "unknown job_id" else 400
        raise HTTPException(status_code=status, detail=msg)
    return {"job_id": job_id, "chosen_query": msg}


@app.get("/api/research/{job_id}/result")
async def research_result(job_id: str) -> dict:
    """Return the final Backend2Report for a finished job. If the job is
    still running, returns 202 + partial state. If unknown, 404.
    """
    rec = await get_job(job_id)
    state: dict[str, Any] | None = None

    if rec is not None and rec.final_state is not None:
        state = rec.final_state
    else:
        # Try the SQLite checkpoint (covers resumed runs + restarts)
        async with open_async_checkpointer() as saver:
            tup = await saver.aget_tuple(
                {"configurable": {"thread_id": job_id}}
            )
            if tup is not None:
                state = (tup.checkpoint or {}).get("channel_values", {}) or {}

    if state is None:
        raise HTTPException(status_code=404, detail="unknown job_id")

    if rec and rec.task and not rec.task.done():
        # In-flight — surface partial state with status code 202
        report = runstate_to_backend2_report(state)
        report["_status"] = "running"
        return report

    if rec and rec.error:
        return {
            "_status": "error",
            "error": rec.error,
            **runstate_to_backend2_report(state),
        }

    return {"_status": "complete", **runstate_to_backend2_report(state)}


# ── History (read-only over SQLite checkpoints) ───────────────────────────

@app.get("/api/research/history")
async def history_list(limit: int = 50) -> list[dict]:
    """List checkpointed runs. Reads directly from the AsyncSqliteSaver DB
    via the existing `list_checkpointed_runs` helper.
    """
    raw = list_checkpointed_runs(limit=limit)
    out: list[dict] = []
    # Each raw item only has summary fields. To enrich (word_count,
    # grounding_score, etc.) we need to load the full state per thread.
    async with open_async_checkpointer() as saver:
        for r in raw:
            tid = r["thread_id"]
            try:
                tup = await saver.aget_tuple(
                    {"configurable": {"thread_id": tid}}
                )
                state = (tup.checkpoint or {}).get("channel_values", {}) or {} if tup else {}
            except Exception:
                state = {}
            out.append(history_summary_from_state(
                thread_id=tid,
                latest_node=r.get("latest_node", ""),
                ts=r.get("ts"),
                state=state,
            ))
    return out


@app.get("/api/research/history/{thread_id}")
async def history_detail(thread_id: str) -> dict:
    """Return the full Backend2Report for a thread_id from the checkpoint DB."""
    async with open_async_checkpointer() as saver:
        tup = await saver.aget_tuple(
            {"configurable": {"thread_id": thread_id}}
        )
    if tup is None:
        raise HTTPException(status_code=404, detail="unknown thread_id")
    state = (tup.checkpoint or {}).get("channel_values", {}) or {}
    return runstate_to_backend2_report(state)


@app.delete("/api/research/history/{thread_id}")
async def history_delete(thread_id: str) -> dict:
    """Delete a checkpointed run from the SQLite DB."""
    async with open_async_checkpointer() as saver:
        try:
            await saver.adelete_thread(thread_id)
        except Exception as exc:
            _log.warning("history.delete_failed",
                         thread_id=thread_id, error=str(exc)[:200])
            return {"deleted": False, "id": thread_id, "error": str(exc)[:200]}
    return {"deleted": True, "id": thread_id}


# ── Diagnostic ────────────────────────────────────────────────────────────

@app.get("/api/_meta")
async def meta() -> dict:
    return {
        "backend": "backend2",
        "checkpoint_db": _checkpoint_db_path(),
        "cors_origins": _CORS_ORIGINS,
    }
