"""research_search tool: SmartCrawler search (SearXNG + content fetch) with per-node call counter and disk cache.

Search priority:
  1. SmartCrawler (SearXNG + tiered content fetch) — free, full-text enriched
  2. Tavily advanced search        — paid fallback if TAVILY_API_KEY is set
  3. Raw SearXNG snippets          — last resort (no content fetch)
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from pathlib import Path

from langchain_core.tools import tool

from research.core.config import settings
from research.core.errors import ToolError
from research.tools.tavily_pool import tavily_pool
from research.tools.searxng import search_searxng, is_searxng_available
from research.tools.smartcrawler_search import search_with_smartcrawler, is_smartcrawler_available

log = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".research" / "cache" / "research_search"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_PER_NODE_LIMIT = 35  # hard cap for Agent 3 (overridable)

_node_call_count: int = 0


def reset_node_counter() -> None:
    """Reset the per-node search call counter. Call before each crew run."""
    global _node_call_count
    _node_call_count = 0


def get_node_call_count() -> int:
    return _node_call_count


def set_node_limit(n: int) -> None:
    """Override the per-node hard cap (useful in tests)."""
    global _PER_NODE_LIMIT
    _PER_NODE_LIMIT = n


def _cache_key(query: str, depth: str, today: str) -> str:
    raw = f"{query}|{depth}|{today}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _load_cache(key: str) -> list | None:
    path = _CACHE_DIR / (key + ".json")
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _save_cache(key: str, results: list) -> None:
    path = _CACHE_DIR / (key + ".json")
    try:
        path.write_text(json.dumps(results, default=str, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


@tool
def research_search(query: str, max_results: int = 5) -> str:
    """Search the web for research information.

    Uses SmartCrawler (SearXNG + content fetch) as primary backend;
    falls back to Tavily if a key is configured, then to raw SearXNG snippets.
    Tracks per-node call count and returns an error JSON once the hard cap
    is reached so the agent can stop gracefully.

    Args:
        query: The search query string.
        max_results: Number of results to return (default 5, max 10).

    Returns:
        JSON: {results: [{url, title, snippet, score, published}], calls_used}
    """
    global _node_call_count

    if _node_call_count >= _PER_NODE_LIMIT:
        return json.dumps({
            "error": f"Search budget exhausted ({_PER_NODE_LIMIT} calls used). Stop searching.",
            "results": [],
            "calls_used": _node_call_count,
        })

    today = date.today().isoformat()
    cache_key = _cache_key(query, "advanced", today)
    cached = _load_cache(cache_key)
    if cached is not None:
        return json.dumps({"results": cached, "calls_used": _node_call_count, "from_cache": True})

    max_results = min(max(1, max_results), 10)
    results: list[dict] = []

    # ── Primary: SmartCrawler (SearXNG + tiered content fetch) ───────────────
    if is_smartcrawler_available():
        try:
            results = search_with_smartcrawler(query, max_results=max_results, news_only=False)
        except Exception as exc:
            log.debug(f"SmartCrawler failed, trying Tavily: {exc}")

    # ── Secondary: Tavily advanced search (paid fallback) ────────────────────
    if not results and tavily_pool.available:
        try:
            response = tavily_pool.search(
                query=query,
                search_depth="advanced",
                max_results=max_results,
            )
            results = [
                {
                    "url":       r.get("url", ""),
                    "title":     r.get("title", ""),
                    "snippet":   r.get("content", ""),
                    "score":     r.get("score", 0.0),
                    "published": r.get("published_date"),
                }
                for r in response.get("results", [])
            ]
        except Exception as exc:
            log.debug(f"Tavily failed, trying raw SearXNG: {exc}")

    # ── Tertiary: raw SearXNG snippets (no content fetch) ────────────────────
    if not results:
        try:
            results = search_searxng(query, max_results=max_results)
        except Exception as exc:
            log.debug(f"Raw SearXNG also failed: {exc}")

    if not results:
        no_smartcrawler = not is_smartcrawler_available()
        no_tavily = not tavily_pool.available
        no_searxng = not is_searxng_available()
        if no_smartcrawler and no_tavily and no_searxng:
            return json.dumps({
                "error": (
                    "No search backends available. "
                    "Start SearXNG (docker-compose up -d from repo root) "
                    "or set TAVILY_API_KEY in .env."
                ),
                "results": [],
            })
        return json.dumps({"results": [], "calls_used": _node_call_count})

    _node_call_count += 1
    _save_cache(cache_key, results)

    return json.dumps({
        "results": results,
        "calls_used": _node_call_count,
    })
