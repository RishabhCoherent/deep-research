"""FastAPI backend — thin layer over existing Python extraction + generation code."""

import asyncio
import json
import os
import sys
import tempfile
import threading
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse

# Ensure project root is on sys.path so existing imports work
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from backend.models import (
    ExtractionResponse, ExtractionSummary, SectionPlanSummary,
    GenerateRequest, GenerateResponse, HealthResponse,
    ResearchRequest, ResearchResponse,
)
from backend.job_manager import create_job, get_job, cleanup_stale
from backend.research_manager import (
    create_research_job, get_research_job, cleanup_stale_research,
    run_research_thread,
)
from backend.history_manager import list_history, get_history, delete_history

from extractors.toc_extractor import extract_toc
from extractors.me_extractor import extract_me
from report.mapper import map_sections
from ui.generation import start_generation, drain_queue
from config import has_openai, has_searxng

logger = logging.getLogger(__name__)

app = FastAPI(title="Deep Research API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ──────────────────────────────────────────────────────────────────


@app.get("/api/health", response_model=HealthResponse)
def health():
    return HealthResponse(openai=has_openai(), searxng=has_searxng())


# ─── Extraction ──────────────────────────────────────────────────────────────


def _build_summary(toc: dict, me_data: dict) -> ExtractionSummary:
    """Build extraction summary from toc + me_data (mirrors ui/extraction.py:105)."""
    sections = toc.get("sections", [])
    sheets = me_data.get("data_sheets", [])
    plans = map_sections(toc, me_data)

    plan_summaries = []
    for p in sorted(plans, key=lambda x: x.section_number):
        plan_summaries.append(SectionPlanSummary(
            number=p.section_number,
            type=p.section_type,
            title=(p.title[:70] if p.title else "(no title)"),
        ))

    return ExtractionSummary(
        report_title=toc.get("report_title", "Unknown"),
        subtitle=toc.get("subtitle", ""),
        section_count=len(sections),
        sheet_count=len(sheets),
        sheets=sheets,
        plans=plan_summaries,
    )


@app.post("/api/extract/files", response_model=ExtractionResponse)
async def extract_files(
    pptx: UploadFile = File(...),
    xlsx: UploadFile = File(...),
):
    """Extract TOC + ME data from uploaded PPTX and XLSX files."""
    tmpdir = tempfile.mkdtemp()
    try:
        pptx_path = os.path.join(tmpdir, pptx.filename or "toc.pptx")
        xlsx_path = os.path.join(tmpdir, xlsx.filename or "me.xlsx")

        with open(pptx_path, "wb") as f:
            f.write(await pptx.read())
        with open(xlsx_path, "wb") as f:
            f.write(await xlsx.read())

        toc_data = extract_toc(pptx_path)
        me_data = extract_me(xlsx_path)

        combined = {
            "extracted_at": datetime.now().isoformat(),
            "source_files": {
                "pptx": pptx.filename or "toc.pptx",
                "xlsx": xlsx.filename or "me.xlsx",
            },
            "toc": toc_data,
            "me_data": me_data,
        }

        summary = _build_summary(toc_data, me_data)
        return ExtractionResponse(extracted_data=combined, summary=summary)

    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/extract/json", response_model=ExtractionResponse)
async def extract_json(file: UploadFile = File(...)):
    """Load and validate a pre-extracted JSON file."""
    try:
        content = await file.read()
        data = json.loads(content)

        if "toc" not in data:
            raise ValueError("JSON missing 'toc' key")
        if "me_data" not in data:
            raise ValueError("JSON missing 'me_data' key")

        summary = _build_summary(data["toc"], data["me_data"])
        return ExtractionResponse(extracted_data=data, summary=summary)

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"JSON extraction failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/extract/json-path", response_model=ExtractionResponse)
async def extract_json_from_path(json_path: str):
    """Load and validate a pre-extracted JSON from a local file path."""
    json_path = json_path.strip().strip('"').strip("'")

    if not os.path.isfile(json_path):
        raise HTTPException(status_code=400, detail=f"JSON file not found: {json_path}")

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "toc" not in data:
            raise ValueError("JSON missing 'toc' key")
        if "me_data" not in data:
            raise ValueError("JSON missing 'me_data' key")

        summary = _build_summary(data["toc"], data["me_data"])
        return ExtractionResponse(extracted_data=data, summary=summary)

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"JSON path extraction failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/extract/paths", response_model=ExtractionResponse)
async def extract_from_paths(pptx_path: str, xlsx_path: str):
    """Extract from local file paths (for development convenience)."""
    pptx_path = pptx_path.strip().strip('"').strip("'")
    xlsx_path = xlsx_path.strip().strip('"').strip("'")

    if not os.path.isfile(pptx_path):
        raise HTTPException(status_code=400, detail=f"PPTX file not found: {pptx_path}")
    if not os.path.isfile(xlsx_path):
        raise HTTPException(status_code=400, detail=f"XLSX file not found: {xlsx_path}")

    try:
        toc_data = extract_toc(pptx_path)
        me_data = extract_me(xlsx_path)

        combined = {
            "extracted_at": datetime.now().isoformat(),
            "source_files": {
                "pptx": os.path.basename(pptx_path),
                "xlsx": os.path.basename(xlsx_path),
            },
            "toc": toc_data,
            "me_data": me_data,
        }

        summary = _build_summary(toc_data, me_data)
        return ExtractionResponse(extracted_data=combined, summary=summary)

    except Exception as e:
        logger.error(f"Path extraction failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ─── Generation ──────────────────────────────────────────────────────────────


@app.post("/api/generate", response_model=GenerateResponse)
async def generate_report(req: GenerateRequest):
    """Start report generation in a background thread."""
    cleanup_stale()

    try:
        thread, progress_queue, result_holder = start_generation(
            req.extracted_data,
            skip_content=req.skip_content,
            topic_override=req.topic_override,
        )
        job_id = create_job(thread, progress_queue, result_holder)
        return GenerateResponse(job_id=job_id)

    except Exception as e:
        logger.error(f"Generation start failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/generate/{job_id}/progress")
async def generation_progress(job_id: str):
    """SSE stream of generation progress events."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_stream():
        heartbeat_counter = 0
        while True:
            messages = drain_queue(job.progress_queue)

            for msg_type, msg_text in messages:
                if msg_type == "done":
                    # Send final result
                    if job.result_holder.get("success"):
                        output_path = job.result_holder["output_path"]
                        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
                        final = json.dumps({
                            "type": "done",
                            "success": True,
                            "file_size": file_size,
                        })
                    else:
                        final = json.dumps({
                            "type": "done",
                            "success": False,
                            "error": job.result_holder.get("error", "Unknown error"),
                        })
                    yield f"event: done\ndata: {final}\n\n"
                    return
                else:
                    event_data = json.dumps({"type": msg_type, "message": msg_text})
                    yield f"event: {msg_type}\ndata: {event_data}\n\n"

            # Check if thread died unexpectedly
            if job.thread and not job.thread.is_alive() and not messages:
                if job.result_holder.get("success") is not None:
                    # Thread finished but we haven't seen "done" — send it now
                    if job.result_holder.get("success"):
                        output_path = job.result_holder["output_path"]
                        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
                        final = json.dumps({"type": "done", "success": True, "file_size": file_size})
                    else:
                        final = json.dumps({"type": "done", "success": False, "error": job.result_holder.get("error", "Unknown")})
                    yield f"event: done\ndata: {final}\n\n"
                    return
                else:
                    yield f"event: done\ndata: {json.dumps({'type': 'done', 'success': False, 'error': 'Process terminated unexpectedly'})}\n\n"
                    return

            # Heartbeat every ~15 seconds (0.3s * 50 = 15s)
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


@app.get("/api/generate/{job_id}/download")
async def download_report(job_id: str):
    """Download the generated .docx report."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.result_holder.get("success"):
        raise HTTPException(status_code=400, detail="Report generation not complete or failed")

    output_path = job.result_holder.get("output_path", "")
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="Report file not found")

    filename = os.path.basename(output_path)
    return FileResponse(
        path=output_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# ─── Research Agent ───────────────────────────────────────────────────────────


# ─── Research History (must be before {job_id} routes) ────────────────────────


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
    return entry


@app.delete("/api/research/history/{history_id}")
async def research_history_delete(history_id: str):
    """Delete a saved research result."""
    deleted = delete_history(history_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="History entry not found")
    return {"deleted": True, "id": history_id}


@app.post("/api/research", response_model=ResearchResponse)
async def start_research(req: ResearchRequest):
    """Start multi-layer research in a background thread."""
    cleanup_stale_research()

    try:
        import queue as q
        progress_queue = q.Queue()
        result_holder: dict = {}

        thread = threading.Thread(
            target=run_research_thread,
            args=(req.topic, req.max_layer,
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

            # Check if thread died
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


# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.api:app", host="0.0.0.0", port=8000, reload=True)
