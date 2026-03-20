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


def run_research_thread(topic: str, brief: str, max_layer: int,
                        progress_queue: queue.Queue, result_holder: dict):
    """Thread target: runs the multi-layer research agent."""
    try:

        from research_agent import run_all_layers

        def progress_callback(layer, status, message):
            event = json.dumps({
                "layer": layer,
                "status": status,
                "message": message,
            })
            progress_queue.put((f"layer_{status}", event))

        report = asyncio.run(run_all_layers(
            topic=topic,
            brief=brief,
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

        # Capture cost breakdown from the global tracker
        from research_agent.cost import get_tracker
        cost_data = get_tracker().to_dict()

        # Serialize pairwise layer comparisons
        layer_comparisons = []
        for lc in report.layer_comparisons:
            claim_pairs = []
            for cp in (lc.claim_pairs or []):
                claim_pairs.append({
                    "category": cp.category,
                    "baseline": cp.baseline,
                    "improved": cp.improved,
                    "tags": cp.tags,
                    "source": cp.source,
                })
            layer_comparisons.append({
                "from_layer": lc.from_layer,
                "to_layer": lc.to_layer,
                "improvements": lc.improvements,
                "score_delta": lc.score_delta,
                "key_evidence": lc.key_evidence,
                "overall_verdict": lc.overall_verdict,
                "claim_pairs": claim_pairs,
            })

        # Serialize claim journey (showcase transformation across all layers)
        claim_journey = None
        if report.claim_journey:
            cj = report.claim_journey
            claim_journey = {
                "category": cj.category,
                "topic_sentence": cj.topic_sentence,
                "overall_narrative": cj.overall_narrative,
                "selection_reason": cj.selection_reason,
                "snapshots": [
                    {
                        "layer": s.layer,
                        "claim_text": s.claim_text,
                        "data_points": s.data_points,
                        "sources_cited": s.sources_cited,
                        "quality_tags": s.quality_tags,
                        "transformation_steps": [
                            {
                                "action": ts.action,
                                "query": ts.query,
                                "source_title": ts.source_title,
                                "source_url": ts.source_url,
                                "data_point_added": ts.data_point_added,
                                "why_it_matters": ts.why_it_matters,
                            }
                            for ts in s.transformation_steps
                        ],
                    }
                    for s in cj.snapshots
                ],
            }

        result_holder["success"] = True
        result_holder["report"] = {
            "topic": report.topic,
            "layers": layers,
            "evaluations": evaluations,
            "summary": report.summary,
            "layer_comparisons": layer_comparisons,
            "claim_journey": claim_journey,
            "cost": cost_data,
            "hallucination_reduction": report.hallucination_reduction,
            "outcome_efficiency": report.outcome_efficiency,
            "relevancy": report.relevancy,
        }

        # Auto-save to persistent history
        try:
            from history_manager import save_research
            save_research(result_holder["report"])
        except Exception as save_err:
            logger.warning(f"Failed to auto-save research history: {save_err}")

        progress_queue.put(("done", json.dumps({"success": True})))

    except Exception as e:
        import traceback
        logger.error(f"Research thread failed: {e}\n{traceback.format_exc()}")
        result_holder["success"] = False
        result_holder["error"] = str(e)
        progress_queue.put(("done", json.dumps({
            "success": False,
            "error": str(e),
        })))
