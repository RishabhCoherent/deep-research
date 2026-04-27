"""DuckDuckGo search helpers — synchronous, no API key, no Docker required.

Used as a free fallback in smartcrawler_search when SearXNG is unavailable.
Requires the `ddgs` package (pip install ddgs).

Returns the same {url, title, snippet, score, published} shape as searxng.py
so callers need zero format changes.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def is_ddg_available() -> bool:
    """True if the ddgs package is importable (no network check needed)."""
    try:
        from ddgs import DDGS  # noqa: F401
        return True
    except ImportError:
        return False


def search_ddg(query: str, max_results: int = 5) -> list[dict]:
    """General DuckDuckGo web search (synchronous).

    Returns list of {url, title, snippet, score, published} — same shape
    as SearXNG results so callers need no format conversion.
    """
    try:
        from ddgs import DDGS

        results: list[dict] = []
        with DDGS() as ddgs:
            raw = ddgs.text(query, max_results=max_results)
            for r in raw:
                url = r.get("href", "")
                if not url:
                    continue
                results.append({
                    "url":       url,
                    "title":     r.get("title", ""),
                    "snippet":   r.get("body", ""),
                    "score":     0.5,
                    "published": None,
                })
        log.debug("DDG returned %d results for: %s", len(results), query[:60])
        return results

    except Exception as exc:
        log.debug("DDG general search failed: %s", exc)
        return []


def search_ddg_news(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo news search (synchronous).

    Returns list of {url, title, snippet, score, published}.
    """
    try:
        from ddgs import DDGS

        results: list[dict] = []
        with DDGS() as ddgs:
            raw = ddgs.news(query, max_results=max_results)
            for r in raw:
                url = r.get("url") or r.get("link", "")
                if not url:
                    continue
                results.append({
                    "url":       url,
                    "title":     r.get("title", ""),
                    "snippet":   r.get("body", ""),
                    "score":     0.5,
                    "published": r.get("date"),
                })
        log.debug("DDG news returned %d results for: %s", len(results), query[:60])
        return results

    except Exception as exc:
        log.debug("DDG news search failed: %s", exc)
        return []
