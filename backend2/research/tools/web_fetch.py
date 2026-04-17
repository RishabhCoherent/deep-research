"""web_fetch tool: httpx GET + trafilatura extraction with disk cache."""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from langchain_core.tools import tool

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

try:
    import trafilatura
    _HAS_TRAFILATURA = True
except ImportError:
    _HAS_TRAFILATURA = False

_CACHE_DIR = Path.home() / ".research" / "cache" / "web"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_TIMEOUT_SECONDS = 10
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_MAX_TEXT_CHARS = 20_000       # stored in Passage / disk cache
_AGENT_CONTEXT_CHARS = 4_000  # returned to the LLM to prevent context blowup in 3b

_ROBOTS_CACHE: dict[str, bool] = {}


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def _load_cache(url: str) -> dict | None:
    path = _CACHE_DIR / (_cache_key(url) + ".json")
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _save_cache(url: str, data: dict) -> None:
    path = _CACHE_DIR / (_cache_key(url) + ".json")
    try:
        path.write_text(json.dumps(data, default=str, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _is_allowed(url: str) -> bool:
    """Lightweight robots.txt check (cached per host)."""
    parsed = urlparse(url)
    host = f"{parsed.scheme}://{parsed.netloc}"
    if host in _ROBOTS_CACHE:
        return _ROBOTS_CACHE[host]
    try:
        rp = RobotFileParser()
        rp.set_url(f"{host}/robots.txt")
        rp.read()
        allowed = rp.can_fetch("*", url)
    except Exception:
        allowed = True
    _ROBOTS_CACHE[host] = allowed
    return allowed


def _fetch_raw(url: str) -> dict:
    """Fetch URL and extract text. Returns dict with url/title/publisher/text."""
    if not _HAS_HTTPX:
        return {"url": url, "error": "httpx not installed", "text": ""}

    headers = {"User-Agent": "ResearchBot/1.0 (analyst-research; +https://example.com/bot)"}
    try:
        with httpx.Client(timeout=_TIMEOUT_SECONDS, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            raw_html = resp.content[:_MAX_BYTES].decode("utf-8", errors="replace")
    except Exception as exc:
        return {"url": url, "error": str(exc), "text": ""}

    if _HAS_TRAFILATURA:
        meta = trafilatura.extract(raw_html, include_comments=False,
                                   include_tables=True, with_metadata=True,
                                   output_format="json", favor_recall=True)
        if meta:
            try:
                obj = json.loads(meta)
                return {
                    "url": url,
                    "title": obj.get("title"),
                    "publisher": obj.get("sitename"),
                    "published": obj.get("date"),
                    "text": (obj.get("text") or "")[:_MAX_TEXT_CHARS],
                }
            except Exception:
                pass
        text = trafilatura.extract(raw_html) or ""
        return {"url": url, "title": None, "publisher": None,
                "published": None, "text": text[:_MAX_TEXT_CHARS]}

    # Fallback: strip tags naively
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = re.sub(r"\s+", " ", text).strip()[:_MAX_TEXT_CHARS]
    return {"url": url, "title": None, "publisher": None, "published": None, "text": text}


@tool
def web_fetch(url: str) -> str:
    """Fetch a URL and return extracted text with metadata.

    Respects robots.txt. Caches results on disk by URL hash.
    Text is truncated at 20,000 characters.

    Args:
        url: The full URL to fetch.

    Returns:
        JSON string: {url, title, publisher, published, accessed, text}
        On error: {url, error, text: ""}
    """
    cached = _load_cache(url)
    if cached:
        agent_view = {**cached, "text": cached.get("text", "")[:_AGENT_CONTEXT_CHARS]}
        return json.dumps(agent_view, default=str)

    if not _is_allowed(url):
        result = {"url": url, "error": "robots.txt disallows access", "text": ""}
        return json.dumps(result)

    accessed = datetime.now(timezone.utc).isoformat()
    result = _fetch_raw(url)
    result["accessed"] = accessed

    if result.get("text"):
        _save_cache(url, result)  # full 20K text cached on disk

    # Return truncated text to the LLM to contain context growth
    agent_view = {**result, "text": result.get("text", "")[:_AGENT_CONTEXT_CHARS]}
    return json.dumps(agent_view, default=str)
