"""FastAPI backend for the Deep Research multi-layer pipeline."""

import asyncio
import json
import os
import queue
import threading
import logging
from pathlib import Path

# Configure logging — must be before any getLogger() calls in imported modules
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
# Quiet noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from dotenv import load_dotenv

# Load .env from backend directory (or parent if running from project root)
_here = Path(__file__).resolve().parent
load_dotenv(_here / ".env")
load_dotenv(_here.parent / ".env")  # fallback: project root .env

from models import HealthResponse, ResearchRequest, ResearchResponse
from research_manager import (
    create_research_job, get_research_job, cleanup_stale_research,
    run_research_thread,
)
from history_manager import list_history, get_history, delete_history
from research_agent.utils import strip_preamble
from config import has_openai, has_searxng, has_tavily

logger = logging.getLogger(__name__)

app = FastAPI(title="Deep Research API", version="2.0.0")

# CORS — allow frontend origins (local dev + Vercel production)
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
# Allow Vercel frontend URL from env
_frontend_url = os.getenv("FRONTEND_URL")
if _frontend_url:
    ALLOWED_ORIGINS.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Helpers ────────────────────────────────────────────────────────────────


def drain_queue(progress_queue: queue.Queue) -> list:
    """Drain all messages from the progress queue."""
    messages = []
    while True:
        try:
            msg = progress_queue.get_nowait()
            messages.append(msg)
        except queue.Empty:
            break
    return messages


# ─── Health ─────────────────────────────────────────────────────────────────


_CODE_VERSION = "2026-03-21-v3-metrics-fix"

@app.get("/api/health", response_model=HealthResponse)
def health():
    return HealthResponse(openai=has_openai(), searxng=has_searxng(), tavily=has_tavily())

@app.get("/api/version")
def version():
    return {"version": _CODE_VERSION}


# ─── Research History (must be before {job_id} routes) ──────────────────────


@app.get("/api/research/history")
async def research_history_list():
    """List all saved research results (metadata only)."""
    return list_history()


@app.get("/api/research/history/{history_id}")
async def research_history_get(history_id: str):
    """Get a single saved research result (includes full report)."""
    entry = get_history(history_id)
    if not entry:
        raise HTTPException(status_code=404, detail="History entry not found")
    for layer in entry.get("report", {}).get("layers", []):
        if layer.get("content"):
            layer["content"] = strip_preamble(layer["content"])
    return entry


@app.delete("/api/research/history/{history_id}")
async def research_history_delete(history_id: str):
    """Delete a saved research result."""
    deleted = delete_history(history_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="History entry not found")
    return {"deleted": True, "id": history_id}


# ─── Research Agent ─────────────────────────────────────────────────────────


@app.post("/api/research", response_model=ResearchResponse)
async def start_research(req: ResearchRequest):
    """Start multi-layer research in a background thread."""
    cleanup_stale_research()

    try:
        progress_queue = queue.Queue()
        result_holder: dict = {}

        thread = threading.Thread(
            target=run_research_thread,
            args=(req.topic, req.brief, req.max_layer,
                  progress_queue, result_holder),
            daemon=True,
        )
        thread.start()

        job_id = create_research_job(thread, progress_queue, result_holder)
        return ResearchResponse(job_id=job_id)

    except Exception as e:
        logger.error(f"Research start failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/research/{job_id}/progress")
async def research_progress(job_id: str):
    """SSE stream of research progress events."""
    job = get_research_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Research job not found")

    async def event_stream():
        heartbeat_counter = 0
        while True:
            messages = drain_queue(job.progress_queue)

            for msg_type, msg_data in messages:
                if msg_type == "done":
                    yield f"event: done\ndata: {msg_data}\n\n"
                    return
                else:
                    yield f"event: {msg_type}\ndata: {msg_data}\n\n"

            if job.thread and not job.thread.is_alive() and not messages:
                if job.result_holder.get("success") is not None:
                    done_data = json.dumps({
                        "success": job.result_holder.get("success", False),
                        "error": job.result_holder.get("error"),
                    })
                    yield f"event: done\ndata: {done_data}\n\n"
                    return
                else:
                    yield f"event: done\ndata: {json.dumps({'success': False, 'error': 'Process terminated unexpectedly'})}\n\n"
                    return

            heartbeat_counter += 1
            if heartbeat_counter >= 50:
                yield f"event: heartbeat\ndata: {{}}\n\n"
                heartbeat_counter = 0

            await asyncio.sleep(0.3)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/research/{job_id}/result")
async def research_result(job_id: str):
    """Get the final research comparison report."""
    job = get_research_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Research job not found")

    if job.result_holder.get("success") is None:
        raise HTTPException(status_code=202, detail="Research still in progress")

    if not job.result_holder.get("success"):
        raise HTTPException(
            status_code=500,
            detail=job.result_holder.get("error", "Research failed"),
        )

    return job.result_holder["report"]


# ─── Run ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    is_dev = os.getenv("ENV", "production") != "production"
    uvicorn.run("api:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=is_dev)
