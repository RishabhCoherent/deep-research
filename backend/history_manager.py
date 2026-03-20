"""Research history storage — PostgreSQL (production) with JSON file fallback (local dev)."""

import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _compute_avg_score(report: dict) -> float:
    """Compute average score of the LAST (highest) layer only."""
    evaluations = report.get("evaluations", [])
    if not evaluations:
        return 0.0
    last_ev = max(evaluations, key=lambda ev: ev.get("layer", 0))
    scores = []
    for val in last_ev.get("scores", {}).values():
        if isinstance(val, dict) and "score" in val:
            scores.append(val["score"])
    return round(sum(scores) / len(scores), 1) if scores else 0.0


def _make_id(topic: str) -> str:
    """Generate a unique ID from timestamp + sanitized topic."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in topic)
    safe = safe[:40].strip().replace(" ", "_").lower()
    return f"{timestamp}_{safe}"


def _use_db() -> bool:
    """Check if PostgreSQL is configured."""
    return bool(os.getenv("DATABASE_URL"))


# ─── PostgreSQL Implementation ──────────────────────────────────────────────


def _db_save(report: dict) -> str:
    from database import SessionLocal, ResearchHistory, init_db
    init_db()

    history_id = _make_id(report.get("topic", "unknown"))
    layers = report.get("layers", [])

    row = ResearchHistory(
        id=history_id,
        saved_at=datetime.now(),
        topic=report.get("topic", ""),
        layer_count=len(layers),
        total_words=sum(l.get("word_count", 0) for l in layers),
        total_sources=sum(l.get("source_count", 0) for l in layers),
        avg_score=_compute_avg_score(report),
        report=report,
    )

    with SessionLocal() as session:
        session.add(row)
        session.commit()

    logger.info(f"Saved research history to DB: {history_id}")
    return history_id


def _db_list() -> list[dict]:
    from database import SessionLocal, ResearchHistory, init_db
    init_db()

    with SessionLocal() as session:
        rows = session.query(ResearchHistory).order_by(
            ResearchHistory.saved_at.desc()
        ).all()
        return [
            {
                "id": r.id,
                "saved_at": r.saved_at.isoformat(),
                "topic": r.topic,
                "layer_count": r.layer_count,
                "total_words": r.total_words,
                "total_sources": r.total_sources,
                "avg_score": r.avg_score or 0,
            }
            for r in rows
        ]


def _db_get(history_id: str) -> dict | None:
    from database import SessionLocal, ResearchHistory, init_db
    init_db()

    with SessionLocal() as session:
        row = session.query(ResearchHistory).filter_by(id=history_id).first()
        if not row:
            return None
        return {
            "id": row.id,
            "saved_at": row.saved_at.isoformat(),
            "topic": row.topic,
            "layer_count": row.layer_count,
            "total_words": row.total_words,
            "total_sources": row.total_sources,
            "avg_score": row.avg_score or 0,
            "report": row.report,
        }


def _db_delete(history_id: str) -> bool:
    from database import SessionLocal, ResearchHistory, init_db
    init_db()

    with SessionLocal() as session:
        row = session.query(ResearchHistory).filter_by(id=history_id).first()
        if not row:
            return False
        session.delete(row)
        session.commit()
        logger.info(f"Deleted research history from DB: {history_id}")
        return True


# ─── JSON File Fallback (local dev without DATABASE_URL) ────────────────────

import threading
from pathlib import Path

_BACKEND_ROOT = str(Path(__file__).resolve().parent)
_HISTORY_DIR = os.path.join(_BACKEND_ROOT, "data", "research_history")
_write_lock = threading.Lock()


def _ensure_dir():
    os.makedirs(_HISTORY_DIR, exist_ok=True)


def _file_save(report: dict) -> str:
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

    path = os.path.join(_HISTORY_DIR, f"{history_id}.json")
    with _write_lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved research history to file: {path}")
    return history_id


def _file_list() -> list[dict]:
    _ensure_dir()
    entries = []
    for fname in os.listdir(_HISTORY_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(_HISTORY_DIR, fname)
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


def _file_get(history_id: str) -> dict | None:
    safe_id = os.path.basename(history_id)
    path = os.path.join(_HISTORY_DIR, f"{safe_id}.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load history {history_id}: {e}")
        return None


def _file_delete(history_id: str) -> bool:
    safe_id = os.path.basename(history_id)
    path = os.path.join(_HISTORY_DIR, f"{safe_id}.json")
    if not os.path.isfile(path):
        return False
    try:
        with _write_lock:
            os.remove(path)
        logger.info(f"Deleted research history file: {history_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete history {history_id}: {e}")
        return False


# ─── Public API (auto-selects DB or file based on DATABASE_URL) ─────────────


def save_research(report: dict) -> str:
    return _db_save(report) if _use_db() else _file_save(report)


def list_history() -> list[dict]:
    return _db_list() if _use_db() else _file_list()


def get_history(history_id: str) -> dict | None:
    return _db_get(history_id) if _use_db() else _file_get(history_id)


def delete_history(history_id: str) -> bool:
    return _db_delete(history_id) if _use_db() else _file_delete(history_id)
