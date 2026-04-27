"""web_search tool: SmartCrawler news search (SearXNG news + content fetch) with per-node call counter and disk cache.

Separate from research_search — this targets recent news with a recency
window, used exclusively by Agent 5 sub-agents.
Search priority:
  1. SmartCrawler news (SearXNG news category + content fetch) — free
  2. Tavily news search  — paid fallback if TAVILY_API_KEY is set
  3. Raw SearXNG news snippets — last resort
Hard cap: 25 news calls per crew run (reset via reset_news_counter()).
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
from research.tools.searxng import search_searxng_news, is_searxng_available
from research.tools.smartcrawler_search import search_with_smartcrawler, is_smartcrawler_available

log = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".research" / "cache" / "web_search"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_PER_NODE_LIMIT = 25  # hard cap across all Agent 5 sub-agents

_news_call_count: int = 0


def reset_news_counter() -> None:
    """Reset the per-node news search call counter. Call before each crew run."""
    global _news_call_count
    _news_call_count = 0


def get_news_call_count() -> int:
    return _news_call_count


def set_news_limit(n: int) -> None:
    """Override the per-node hard cap (useful in tests)."""
    global _PER_NODE_LIMIT
    _PER_NODE_LIMIT = n


def _cache_key(query: str, days: int, today: str) -> str:
    raw = f"{query}|news|{days}|{today}"
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
def web_search(query: str, days: int = 90, max_results: int = 5) -> str:
    """Search for recent news articles.

    Uses SmartCrawler news (SearXNG news category + content fetch) as primary;
    falls back to Tavily news if a key is configured, then to raw SearXNG news.
    Hard-capped at 25 calls per run.

    Args:
        query:       The news search query string.
        days:        Look-back window in days (default 90, used by Tavily fallback).
        max_results: Number of results to return (default 5, max 10).

    Returns:
        JSON: {results: [{url, title, snippet, published, score}], calls_used, from_cache?}
        On cap: {error, results: [], calls_used}
    """
    global _news_call_count

    if _news_call_count >= _PER_NODE_LIMIT:
        return json.dumps({
            "error": f"News search budget exhausted ({_PER_NODE_LIMIT} calls used). Stop searching.",  # noqa: E501
            "results": [],
            "calls_used": _news_call_count,
        })

    today = date.today().isoformat()
    cache_key = _cache_key(query, days, today)
    cached = _load_cache(cache_key)
    if cached is not None:
        return json.dumps({"results": cached, "calls_used": _news_call_count, "from_cache": True})

    max_results = min(max(1, max_results), 10)
    results: list[dict] = []

    # ── Primary: SmartCrawler news (SearXNG news + content fetch) ───────────
    if is_smartcrawler_available():
        try:
            results = search_with_smartcrawler(query, max_results=max_results, news_only=True)
        except Exception as exc:
            log.debug(f"SmartCrawler news failed, trying Tavily: {exc}")

    # ── Secondary: Tavily news search (paid fallback) ─────────────────────
    if not results and tavily_pool.available:
        try:
            response = tavily_pool.search(
                query=query,
                topic="news",
                days=days,
                search_depth="basic",
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
            log.debug(f"Tavily news failed, trying raw SearXNG: {exc}")

    # ── Tertiary: raw SearXNG news snippets (no content fetch) ────────────
    if not results:
        try:
            results = search_searxng_news(query, max_results=max_results)
        except Exception as exc:
            log.debug(f"Raw SearXNG news also failed: {exc}")

    if not results:
        no_smartcrawler = not is_smartcrawler_available()
        no_tavily = not tavily_pool.available
        no_searxng = not is_searxng_available()
        if no_smartcrawler and no_tavily and no_searxng:
            return json.dumps({
                "error": (
                    "No news search backends available. "
                    "Start SearXNG (docker-compose up -d from repo root) "
                    "or set TAVILY_API_KEY in .env."
                ),
                "results": [],
                "calls_used": _news_call_count,
            })
        return json.dumps({"results": [], "calls_used": _news_call_count})

    _news_call_count += 1
    _save_cache(cache_key, results)

    return json.dumps({
        "results": results,
        "calls_used": _news_call_count,
    })
