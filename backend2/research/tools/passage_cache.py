"""SQLite-backed passage cache.

Persists scraped passage content keyed by URL so the same page is never
re-fetched across multiple research runs within the TTL window.

DB location : ~/.research/cache/passages.db
Default TTL : 3 days  (configurable per call)
"""
from __future__ import annotations

import sqlite3
import structlog
from datetime import datetime, timedelta
from pathlib import Path

log = structlog.get_logger(__name__)

_DB_PATH         = Path.home() / ".research" / "cache" / "passages.db"
_DEFAULT_TTL_DAYS = 3

_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# ── DB helpers ─────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB_PATH))
    con.execute("""
        CREATE TABLE IF NOT EXISTS passages (
            url          TEXT PRIMARY KEY,
            date_fetched TEXT NOT NULL,
            title        TEXT,
            content      TEXT,
            published    TEXT,
            tier         TEXT
        )
    """)
    con.commit()
    return con


# ── Public API ─────────────────────────────────────────────────────────────

def get_cached_passage(url: str, max_age_days: int = _DEFAULT_TTL_DAYS) -> dict | None:
    """Return a cached fetch result dict if it exists and is within *max_age_days*.

    The returned dict has keys: url, title, content, published, success, tier.
    Returns None when not cached, expired, or content is empty.
    """
    try:
        con = _conn()
        row = con.execute(
            "SELECT title, content, published, tier, date_fetched FROM passages WHERE url = ?",
            (url,),
        ).fetchone()
        con.close()

        if not row:
            return None
        title, content, published, tier, date_fetched = row
        if not content:
            return None

        age = datetime.now() - datetime.fromisoformat(date_fetched)
        if age > timedelta(days=max_age_days):
            return None

        return {
            "url":       url,
            "title":     title or "",
            "content":   content,
            "published": published,
            "success":   True,
            "tier":      f"cache:{tier or 'unknown'}",
        }
    except Exception as exc:
        log.debug("[passage_cache] get error %s: %s", url[:80], exc)
        return None


def save_passage(url: str, result: dict) -> None:
    """Persist a successful fetch result to the passage cache.

    No-op if result is unsuccessful or has no content.
    """
    if not result.get("success") or not result.get("content"):
        return
    try:
        con = _conn()
        con.execute(
            """INSERT OR REPLACE INTO passages
               (url, date_fetched, title, content, published, tier)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                url,
                datetime.now().isoformat(),
                result.get("title", ""),
                result.get("content", ""),
                result.get("published"),
                result.get("tier", "unknown"),
            ),
        )
        con.commit()
        con.close()
    except Exception as exc:
        log.debug("[passage_cache] save error %s: %s", url[:80], exc)


def cache_stats() -> dict:
    """Return basic stats about the passage cache (for debugging/monitoring)."""
    try:
        con = _conn()
        total  = con.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
        recent = con.execute(
            "SELECT COUNT(*) FROM passages WHERE date_fetched >= datetime('now', '-1 day')"
        ).fetchone()[0]
        size_mb = _DB_PATH.stat().st_size / (1024 * 1024) if _DB_PATH.exists() else 0
        con.close()
        return {
            "total_passages":  total,
            "fetched_today":   recent,
            "db_size_mb":      round(size_mb, 2),
            "db_path":         str(_DB_PATH),
        }
    except Exception:
        return {"total_passages": 0, "fetched_today": 0, "db_size_mb": 0, "db_path": str(_DB_PATH)}


def evict_expired(max_age_days: int = _DEFAULT_TTL_DAYS) -> int:
    """Delete passages older than *max_age_days*. Returns count deleted."""
    try:
        con = _conn()
        cur = con.execute(
            "DELETE FROM passages WHERE date_fetched < datetime('now', ?)",
            (f"-{max_age_days} days",),
        )
        deleted = cur.rowcount
        con.commit()
        con.close()
        return deleted
    except Exception:
        return 0
