"""
Web search tools: SearXNG (primary) + DuckDuckGo (fallback).

SearXNG is a free, self-hosted metasearch engine. Run it locally via:
    docker compose up -d
"""

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Persistent ThreadPoolExecutor to avoid "cannot schedule after shutdown" errors
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="search_")

# Default SearXNG URL (local Docker instance)
_SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8888")


async def search_searxng(query: str, max_results: int = 8, categories: str = "general") -> list[dict]:
    """Search using a local SearXNG instance (JSON API).

    No API keys required. Aggregates results from Google, Bing, DuckDuckGo, etc.
    """
    import httpx

    url = f"{_SEARXNG_URL}/search"
    params = {
        "q": query,
        "format": "json",
        "categories": categories,
        "language": "en",
        "pageno": 1,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        results = []
        for r in data.get("results", [])[:max_results]:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
                "source": "searxng",
            })
        return results

    except Exception as e:
        logger.warning(f"SearXNG search failed: {e}")
        return []


async def search_searxng_news(query: str, max_results: int = 5) -> list[dict]:
    """Search SearXNG news category for recent developments."""
    import httpx

    url = f"{_SEARXNG_URL}/search"
    params = {
        "q": query,
        "format": "json",
        "categories": "news",
        "language": "en",
        "pageno": 1,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        results = []
        for r in data.get("results", [])[:max_results]:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
                "date": r.get("publishedDate", ""),
                "source": "searxng_news",
            })
        return results

    except Exception as e:
        logger.debug(f"SearXNG news search failed: {e}")
        return []


async def search_duckduckgo(query: str, max_results: int = 8) -> list[dict]:
    """Search using DuckDuckGo (ddgs). Free fallback, no API key needed."""
    try:
        from ddgs import DDGS

        def _sync_search():
            ddgs = DDGS()
            raw = ddgs.text(query, max_results=max_results)
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                    "source": "duckduckgo",
                }
                for r in raw
            ]

        return await asyncio.get_event_loop().run_in_executor(_executor, _sync_search)
    except ImportError:
        try:
            from duckduckgo_search import DDGS

            def _sync_search_old():
                ddgs = DDGS()
                raw = ddgs.text(query, max_results=max_results)
                return [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", ""),
                        "source": "duckduckgo",
                    }
                    for r in raw
                ]

            return await asyncio.get_event_loop().run_in_executor(_executor, _sync_search_old)
        except Exception as e:
            logger.debug(f"DuckDuckGo search failed: {e}")
            return []
    except Exception as e:
        logger.debug(f"DuckDuckGo search failed: {e}")
        return []


async def search_duckduckgo_news(query: str, max_results: int = 5) -> list[dict]:
    """Search DuckDuckGo news for recent developments."""
    try:
        from ddgs import DDGS

        def _sync_news():
            ddgs = DDGS()
            raw = ddgs.news(query, max_results=max_results)
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("body", ""),
                    "date": r.get("date", ""),
                    "source": "duckduckgo_news",
                }
                for r in raw
            ]

        return await asyncio.get_event_loop().run_in_executor(_executor, _sync_news)
    except ImportError:
        try:
            from duckduckgo_search import DDGS

            def _sync_news_old():
                ddgs = DDGS()
                raw = ddgs.news(query, max_results=max_results)
                return [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("body", ""),
                        "date": r.get("date", ""),
                        "source": "duckduckgo_news",
                    }
                    for r in raw
                ]

            return await asyncio.get_event_loop().run_in_executor(_executor, _sync_news_old)
        except Exception as e:
            logger.debug(f"DuckDuckGo news search failed: {e}")
            return []
    except Exception as e:
        logger.debug(f"DuckDuckGo news search failed: {e}")
        return []


def _searxng_available() -> bool:
    """Quick check if SearXNG is reachable."""
    try:
        import httpx
        resp = httpx.get(f"{_SEARXNG_URL}/healthz", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


async def search(query: str, max_results: int = 8, include_news: bool = True) -> list[dict]:
    """Unified search: SearXNG first, DuckDuckGo fallback.

    Returns list of {title, url, snippet, source}.
    """
    results = []

    # Try SearXNG first (aggregates Google, Bing, DuckDuckGo, etc.)
    results = await search_searxng(query, max_results)

    # Fallback to DuckDuckGo if SearXNG returned nothing
    if not results:
        results = await search_duckduckgo(query, max_results)

    # Optionally add news results
    if include_news:
        news = await search_searxng_news(query, max_results=3)
        if not news:
            news = await search_duckduckgo_news(query, max_results=3)
        results.extend(news)

    return results


# Smart query suffixes to bias toward primary sources
PRIMARY_SOURCE_SUFFIXES = [
    'site:sec.gov OR site:fda.gov',
    'site:who.int OR site:nih.gov',
    'annual report OR investor presentation OR 10-K filing',
    'Reuters OR Bloomberg OR "press release"',
    'site:clinicaltrials.gov',
]


def enhance_query_for_primary_sources(query: str, suffix_index: int = 0) -> str:
    """Add a suffix to bias search results toward primary sources."""
    if suffix_index < len(PRIMARY_SOURCE_SUFFIXES):
        return f"{query} {PRIMARY_SOURCE_SUFFIXES[suffix_index]}"
    return query
