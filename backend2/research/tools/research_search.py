"""research_search tool: Tavily advanced search with per-node call counter and disk cache."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from langchain_core.tools import tool

from research.core.config import settings
from research.core.errors import ToolError

_CACHE_DIR = Path.home() / ".research" / "cache" / "tavily"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_PER_NODE_LIMIT = 8  # hard cap for Agent 3 (overridable)

_node_call_count: int = 0


def reset_node_counter() -> None:
    """Reset the per-node Tavily call counter. Call before each crew run."""
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
    """Search the web using Tavily advanced search.

    Tracks per-node call count. Returns an empty list with an error message
    once the 8-call hard cap is reached (so the agent can stop gracefully).

    Args:
        query: The search query string.
        max_results: Number of results to return (default 5, max 10).

    Returns:
        JSON array of {url, title, snippet, score, published} dicts.
    """
    global _node_call_count

    if _node_call_count >= _PER_NODE_LIMIT:
        return json.dumps({
            "error": f"Tavily budget exhausted ({_PER_NODE_LIMIT} calls used). Stop searching.",
            "results": [],
            "calls_used": _node_call_count,
        })

    today = date.today().isoformat()
    cache_key = _cache_key(query, "advanced", today)
    cached = _load_cache(cache_key)
    if cached is not None:
        return json.dumps({"results": cached, "calls_used": _node_call_count, "from_cache": True})

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
            search_depth="advanced",
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

    _node_call_count += 1
    _save_cache(cache_key, results)

    return json.dumps({
        "results": results,
        "calls_used": _node_call_count,
    })
