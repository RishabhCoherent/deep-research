"""In-memory job store for report generation threads."""

import uuid
import threading
import queue
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class Job:
    job_id: str
    thread: threading.Thread
    progress_queue: queue.Queue
    result_holder: dict
    created_at: datetime = field(default_factory=datetime.now)


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def create_job(thread: threading.Thread, progress_queue: queue.Queue,
               result_holder: dict) -> str:
    """Register a new generation job. Returns job_id."""
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = Job(
            job_id=job_id,
            thread=thread,
            progress_queue=progress_queue,
            result_holder=result_holder,
        )
    return job_id


def get_job(job_id: str) -> Job | None:
    """Look up a job by ID."""
    with _lock:
        return _jobs.get(job_id)


def cleanup_stale(max_age_seconds: int = 3600):
    """Remove jobs older than max_age_seconds."""
    now = datetime.now()
    with _lock:
        stale = [
            jid for jid, job in _jobs.items()
            if (now - job.created_at).total_seconds() > max_age_seconds
        ]
        for jid in stale:
            del _jobs[jid]
