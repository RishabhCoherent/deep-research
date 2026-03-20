"""JSON file-based research history storage."""

import json
import os
import threading
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

BACKEND_ROOT = str(Path(__file__).resolve().parent)
HISTORY_DIR = os.path.join(BACKEND_ROOT, "data", "research_history")

_write_lock = threading.Lock()


def _ensure_dir():
    os.makedirs(HISTORY_DIR, exist_ok=True)


def _make_id(topic: str) -> str:
    """Generate a unique ID from timestamp + sanitized topic."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in topic)
    safe = safe[:40].strip().replace(" ", "_").lower()
    return f"{timestamp}_{safe}"


def _compute_avg_score(report: dict) -> float:
    """Compute average score of the LAST (highest) layer only."""
    evaluations = report.get("evaluations", [])
    if not evaluations:
        return 0.0
    # Find the evaluation with the highest layer number
    last_ev = max(evaluations, key=lambda ev: ev.get("layer", 0))
    scores = []
    for val in last_ev.get("scores", {}).values():
        if isinstance(val, dict) and "score" in val:
            scores.append(val["score"])
    return round(sum(scores) / len(scores), 1) if scores else 0.0


def save_research(report: dict) -> str:
    """Save a completed research report. Returns the history ID."""
    _ensure_dir()
    history_id = _make_id(report.get("topic", "unknown"))

    layers = report.get("layers", [])

    envelope = {
        "id": history_id,
        "saved_at": datetime.now().isoformat(),
        "topic": report.get("topic", ""),
        "layer_count": len(layers),
        "total_words": sum(l.get("word_count", 0) for l in layers),
        "total_sources": sum(l.get("source_count", 0) for l in layers),
        "avg_score": _compute_avg_score(report),
        "report": report,
    }

    path = os.path.join(HISTORY_DIR, f"{history_id}.json")
    with _write_lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved research history: {path}")
    return history_id


def list_history() -> list[dict]:
    """Return all history entries (metadata only, no full report)."""
    _ensure_dir()
    entries = []
    for fname in os.listdir(HISTORY_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(HISTORY_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries.append({
                "id": data["id"],
                "saved_at": data["saved_at"],
                "topic": data["topic"],
                "layer_count": data["layer_count"],
                "total_words": data["total_words"],
                "total_sources": data["total_sources"],
                "avg_score": data.get("avg_score", 0),
            })
        except Exception as e:
            logger.warning(f"Skipping corrupt history file {fname}: {e}")
    entries.sort(key=lambda x: x["saved_at"], reverse=True)
    return entries


def get_history(history_id: str) -> dict | None:
    """Load a single history entry (including full report)."""
    # Sanitize to prevent path traversal
    safe_id = os.path.basename(history_id)
    path = os.path.join(HISTORY_DIR, f"{safe_id}.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        logger.error(f"Failed to load history {history_id}: {e}")
        return None


def migrate_scores():
    """One-time migration: recompute avg_score and remap old dimension keys for all history entries."""
    _ensure_dir()

    # Map old evaluation score keys → new keys
    _KEY_REMAP = {
        "source_traceability": "source_grounding",
        "clarity": "analytical_depth",
        "actionability": "insight_quality",
    }
    # Keys to remove entirely
    _KEYS_DROP = {"data_accuracy"}

    updated = 0
    for fname in os.listdir(HISTORY_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(HISTORY_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            changed = False

            # Remap evaluation score keys
            for ev in data.get("report", {}).get("evaluations", []):
                scores = ev.get("scores", {})
                for old_key, new_key in _KEY_REMAP.items():
                    if old_key in scores and new_key not in scores:
                        scores[new_key] = scores.pop(old_key)
                        changed = True
                for drop_key in _KEYS_DROP:
                    if drop_key in scores:
                        del scores[drop_key]
                        changed = True

            # Recompute avg_score
            new_score = _compute_avg_score(data.get("report", {}))
            if data.get("avg_score") != new_score:
                data["avg_score"] = new_score
                changed = True

            if changed:
                with _write_lock:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                updated += 1
                logger.info(f"Migrated {fname}: remapped keys, avg_score={new_score}")
        except Exception as e:
            logger.warning(f"Skipping {fname} during migration: {e}")
    logger.info(f"Score migration complete: {updated} entries updated")
    return updated


def delete_history(history_id: str) -> bool:
    """Delete a history entry. Returns True if deleted."""
    safe_id = os.path.basename(history_id)
    path = os.path.join(HISTORY_DIR, f"{safe_id}.json")
    if not os.path.isfile(path):
        return False
    try:
        with _write_lock:
            os.remove(path)
        logger.info(f"Deleted research history: {history_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete history {history_id}: {e}")
        return False
