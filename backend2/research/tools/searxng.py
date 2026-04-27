"""SearXNG search helpers — synchronous, compatible with LangChain @tool context.

Used as a free fallback in research_search and web_search when Tavily is
unavailable or returns no results. Requires a running SearXNG Docker instance
(default: http://localhost:8888, override via SEARXNG_URL env var).
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx

log = logging.getLogger(__name__)

_TIMEOUT = 10.0


def _get_searxng_url() -> str:
    from research.core.config import settings
    return settings.searxng_url.rstrip("/")


def is_searxng_available() -> bool:
    """Lightweight health check — True if local SearXNG is reachable."""
    try:
        resp = httpx.get(urljoin(_get_searxng_url() + "/", "healthz"), timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


def search_searxng(query: str, max_results: int = 5) -> list[dict]:
    """General SearXNG search (synchronous).

    Returns list of {url, title, snippet, score, published} — same shape
    as Tavily results so callers need no format conversion.
    """
    try:
        params = {
            "q": query,
            "format": "json",
            "categories": "general",
            "language": "en",
            "pageno": 1,
            "time_range": "year",
        }
        resp = httpx.get(
            urljoin(_get_searxng_url() + "/", "search"),
            params=params,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for r in data.get("results", [])[:max_results]:
            results.append({
                "url":       r.get("url", ""),
                "title":     r.get("title", ""),
                "snippet":   r.get("content") or r.get("snippet") or "",
                "score":     float(r.get("score", 0.0)),
                "published": r.get("publishedDate"),
            })
        log.debug(f"SearXNG returned {len(results)} results for: {query[:60]}")
        return results

    except Exception as exc:
        log.debug(f"SearXNG general search failed: {exc}")
        return []


def search_searxng_news(query: str, max_results: int = 5) -> list[dict]:
    """News SearXNG search (synchronous).

    Returns list of {url, title, snippet, score, published}.
    """
    try:
        params = {
            "q": query,
            "format": "json",
            "categories": "news",
            "language": "en",
            "pageno": 1,
        }
        resp = httpx.get(
            urljoin(_get_searxng_url() + "/", "search"),
            params=params,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for r in data.get("results", [])[:max_results]:
            results.append({
                "url":       r.get("url", ""),
                "title":     r.get("title", ""),
                "snippet":   r.get("content") or r.get("snippet") or "",
                "score":     float(r.get("score", 0.0)),
                "published": r.get("publishedDate"),
            })
        log.debug(f"SearXNG news returned {len(results)} results for: {query[:60]}")
        return results

    except Exception as exc:
        log.debug(f"SearXNG news search failed: {exc}")
        return []
