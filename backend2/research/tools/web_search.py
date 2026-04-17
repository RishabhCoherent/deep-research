"""web_search tool: Tavily news search with per-node call counter and disk cache.

Separate from research_search (advanced) — this targets topic="news" with a
recency window, used exclusively by Agent 5 sub-agents.
Hard cap: 15 news calls per crew run (reset via reset_news_counter()).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from langchain_core.tools import tool

from research.core.config import settings
from research.core.errors import ToolError

_CACHE_DIR = Path.home() / ".research" / "cache" / "news"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_PER_NODE_LIMIT = 15  # hard cap across all Agent 5 sub-agents

_news_call_count: int = 0


def reset_news_counter() -> None:
    """Reset the per-node news call counter. Call before each crew run."""
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
    """Search for recent news using Tavily news search.

    Uses topic='news' with a recency window. Hard-capped at 15 calls per run.

    Args:
        query:       The news search query string.
        days:        Look-back window in days (default 90).
        max_results: Number of results to return (default 5, max 10).

    Returns:
        JSON: {results: [{url, title, snippet, published, score}], calls_used, from_cache?}
        On cap: {error, results: [], calls_used}
    """
    global _news_call_count

    if _news_call_count >= _PER_NODE_LIMIT:
        return json.dumps({
            "error": f"News search budget exhausted ({_PER_NODE_LIMIT} calls used). Stop searching.",
            "results": [],
            "calls_used": _news_call_count,
        })

    today = date.today().isoformat()
    cache_key = _cache_key(query, days, today)
    cached = _load_cache(cache_key)
    if cached is not None:
        return json.dumps({"results": cached, "calls_used": _news_call_count, "from_cache": True})

    if not settings.tavily_api_key:
        return json.dumps({
            "error": "TAVILY_API_KEY not set. Set it in .env to run live searches.",
            "results": [],
        })

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=settings.tavily_api_key)
        max_results = min(max(1, max_results), 10)
        response = client.search(
            query=query,
            topic="news",
            days=days,
            search_depth="basic",
            max_results=max_results,
        )
        results = [
            {
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "snippet": r.get("content", ""),
                "score": r.get("score", 0.0),
                "published": r.get("published_date"),
            }
            for r in response.get("results", [])
        ]
    except Exception as exc:
        return json.dumps({"error": str(exc), "results": []})

    _news_call_count += 1
    _save_cache(cache_key, results)

    return json.dumps({
        "results": results,
        "calls_used": _news_call_count,
    })
