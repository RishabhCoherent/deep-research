"""In-memory job store for research agent threads."""

import asyncio
import json
import uuid
import threading
import queue
import logging
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ResearchJob:
    job_id: str
    thread: threading.Thread
    progress_queue: queue.Queue
    result_holder: dict
    created_at: datetime = field(default_factory=datetime.now)


_research_jobs: dict[str, ResearchJob] = {}
_lock = threading.Lock()


def create_research_job(thread: threading.Thread, progress_queue: queue.Queue,
                        result_holder: dict) -> str:
    """Register a new research job. Returns job_id."""
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _research_jobs[job_id] = ResearchJob(
            job_id=job_id,
            thread=thread,
            progress_queue=progress_queue,
            result_holder=result_holder,
        )
    return job_id


def get_research_job(job_id: str) -> ResearchJob | None:
    """Look up a research job by ID."""
    with _lock:
        return _research_jobs.get(job_id)


def cleanup_stale_research(max_age_seconds: int = 7200):
    """Remove research jobs older than max_age_seconds."""
    now = datetime.now()
    with _lock:
        stale = [
            jid for jid, job in _research_jobs.items()
            if (now - job.created_at).total_seconds() > max_age_seconds
        ]
        for jid in stale:
            del _research_jobs[jid]


def run_research_thread(topic: str, max_layer: int,
                        progress_queue: queue.Queue, result_holder: dict):
    """Thread target: runs the multi-layer research agent."""
    try:

        from research_agent.runner import run_all_layers

        def progress_callback(layer, status, message):
            event = json.dumps({
                "layer": layer,
                "status": status,
                "message": message,
            })
            progress_queue.put((f"layer_{status}", event))

        report = asyncio.run(run_all_layers(
            topic=topic,
            max_layer=max_layer,
            progress_callback=progress_callback,
        ))

        # Serialize the report
        layers = []
        for r in report.results:
            layers.append({
                "layer": r.layer,
                "word_count": r.word_count,
                "source_count": len(r.sources),
                "elapsed_seconds": round(r.elapsed_seconds, 1),
                "content": r.content,
                "metadata": r.metadata,
            })

        evaluations = []
        for ev in report.evaluations:
            raw = getattr(ev, "_raw_scores", {})
            evaluations.append({
                "layer": ev.layer,
                "factual_density": ev.factual_density,
                "source_diversity": ev.source_diversity,
                "specificity_score": ev.specificity_score,
                "framework_usage": ev.framework_usage,
                "insight_depth": ev.insight_depth,
                "contrarian_views": ev.contrarian_views,
                "word_count": ev.word_count,
                "elapsed_seconds": round(ev.elapsed_seconds, 1),
                "scores": raw,
            })

        result_holder["success"] = True
        result_holder["report"] = {
            "topic": report.topic,
            "layers": layers,
            "evaluations": evaluations,
            "summary": report.summary,
        }

        # Auto-save to persistent history
        try:
            from backend.history_manager import save_research
            save_research(result_holder["report"])
        except Exception as save_err:
            logger.warning(f"Failed to auto-save research history: {save_err}")

        progress_queue.put(("done", json.dumps({"success": True})))

    except Exception as e:
        logger.error(f"Research thread failed: {e}")
        result_holder["success"] = False
        result_holder["error"] = str(e)
        progress_queue.put(("done", json.dumps({
            "success": False,
            "error": str(e),
        })))
