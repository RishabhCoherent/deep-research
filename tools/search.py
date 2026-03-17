"""
Web search tools: Tavily (primary) → SearXNG → DuckDuckGo (fallbacks).

Tavily is a search engine built for AI agents — returns clean, relevant snippets
with semantic ranking. SearXNG and DuckDuckGo serve as free fallbacks.
"""

import asyncio
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Persistent ThreadPoolExecutor to avoid "cannot schedule after shutdown" errors
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="search_")

# Default SearXNG URL (local Docker instance)
_SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8888")


# ─── Tavily API key rotation ────────────────────────────────────────────────

_tavily_keys: list[str] = []
_tavily_key_index = 0


def _get_tavily_keys() -> list[str]:
    """Load Tavily API keys from env (supports comma-separated rotation)."""
    global _tavily_keys
    if not _tavily_keys:
        multi = os.getenv("TAV_API_KEYS", "")
        if multi:
            _tavily_keys = [k.strip() for k in multi.split(",") if k.strip()]
        else:
            single = os.getenv("TAVILY_API_KEY") or os.getenv("TAV_API_KEY", "")
            if single:
                _tavily_keys = [single.strip()]
    return _tavily_keys


def _next_tavily_key() -> str | None:
    """Get the next Tavily key (round-robin rotation)."""
    global _tavily_key_index
    keys = _get_tavily_keys()
    if not keys:
        return None
    key = keys[_tavily_key_index % len(keys)]
    _tavily_key_index += 1
    return key


# ─── Tavily Search ──────────────────────────────────────────────────────────


async def search_tavily(query: str, max_results: int = 5,
                        search_depth: str = "basic") -> list[dict]:
    """Search using Tavily API — built for AI agent research.

    Returns semantically relevant results with clean snippets.
    search_depth: "basic" (fast, cheap) or "advanced" (deeper, 2x cost).
    """
    from tavily import TavilyClient

    api_key = _next_tavily_key()
    if not api_key:
        logger.warning("No Tavily API key available")
        return []

    def _sync_search():
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            max_results=max_results,
            search_depth=search_depth,
            include_answer=False,
        )
        results = []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
                "source": "tavily",
            })
        return results

    try:
        return await asyncio.get_event_loop().run_in_executor(_executor, _sync_search)
    except Exception as e:
        logger.warning(f"Tavily search failed: {e}")
        return []


# ─── SearXNG Search ─────────────────────────────────────────────────────────


async def search_searxng(query: str, max_results: int = 8,
                         categories: str = "general") -> list[dict]:
    """Search using a local SearXNG instance (JSON API)."""
    import httpx

    url = f"{_SEARXNG_URL}/search"
    params = {
        "q": query,
        "format": "json",
        "categories": categories,
        "language": "en",
        "pageno": 1,
        "time_range": "year",
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


# ─── DuckDuckGo Search ──────────────────────────────────────────────────────


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


# ─── Availability checks ────────────────────────────────────────────────────


def _searxng_available() -> bool:
    """Quick check if SearXNG is reachable."""
    try:
        import httpx
        resp = httpx.get(f"{_SEARXNG_URL}/healthz", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


def _tavily_available() -> bool:
    """Check if Tavily API key is configured."""
    return bool(_get_tavily_keys())


# ─── Relevance filter ─────────────────────────────────────────────────────


# Domains that frequently pollute analytical/research queries
_GARBAGE_DOMAINS = {
    "zhihu.com", "flyporter.com", "aecf.org", "quora.com",
    "reddit.com/r/gaming", "fandom.com",
}

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "for", "to", "by",
    "is", "at", "it", "as", "with", "from", "that", "this", "are", "was",
    "be", "has", "have", "had", "not", "but", "what", "how", "why", "when",
    "where", "which", "who", "will", "can", "do", "does", "its", "vs",
    "site", "com", "org", "gov", "net", "market", "analysis", "impact",
    "global", "industry", "report", "trend", "forecast", "growth",
}


def _is_relevant(result: dict, query: str, min_matches: int = 2) -> bool:
    """Check if a search result is relevant to the query.

    Extracts meaningful keywords from the query (ignoring stopwords)
    and checks if at least `min_matches` appear in the result title or snippet.
    Applied to ALL search results including Tavily.
    """
    url = result.get("url", "").lower()

    # Block known garbage domains
    for domain in _GARBAGE_DOMAINS:
        if domain in url:
            return False

    words = re.findall(r'[a-zA-Z]{3,}', query.lower())
    keywords = [w for w in words if w not in _STOPWORDS and not w.isdigit()]

    if len(keywords) < 2:
        return True

    text = (result.get("title", "") + " " + result.get("snippet", "")).lower()
    matches = sum(1 for kw in keywords if kw in text)
    return matches >= min(min_matches, len(keywords))


# ─── Unified search ─────────────────────────────────────────────────────────


async def search(query: str, max_results: int = 8,
                 include_news: bool = True) -> list[dict]:
    """Unified search: Tavily (primary) → SearXNG → DuckDuckGo.

    Returns list of {title, url, snippet, source}.
    All results are relevance-filtered to avoid garbage (listicles, unrelated sites).
    """
    results = []

    # 1. Try Tavily first (best quality) — use advanced depth for better semantic matching
    if _tavily_available():
        raw_tavily = await search_tavily(query, max_results=max_results,
                                         search_depth="advanced")
        # Filter even Tavily results — it still returns "best phones" listicles for analytical queries
        results = [r for r in raw_tavily if _is_relevant(r, query)]
        if results:
            logger.info(f"Tavily returned {len(results)} relevant results "
                        f"(from {len(raw_tavily)} raw) for: {query[:60]}")

    # 2. Fallback to SearXNG if Tavily unavailable or returned nothing useful
    if not results:
        raw_searxng = await search_searxng(query, max_results)
        results = [r for r in raw_searxng if _is_relevant(r, query)]
        if results:
            logger.info(f"SearXNG returned {len(results)} relevant results "
                        f"(from {len(raw_searxng)} raw)")

    # 3. Fallback to DuckDuckGo if still nothing
    if len(results) < 2:
        ddg_results = await search_duckduckgo(query, max_results)
        ddg_relevant = [r for r in ddg_results if _is_relevant(r, query)]
        if len(ddg_relevant) > len(results):
            results = ddg_relevant
            logger.info(f"DuckDuckGo returned {len(results)} relevant results")
        elif ddg_results and not results:
            # Last resort — return unfiltered DDG results
            results = ddg_results

    # 4. Optionally add news results
    if include_news:
        news = await search_searxng_news(query, max_results=3)
        if not news:
            news = await search_duckduckgo_news(query, max_results=3)
        results.extend([r for r in news if _is_relevant(r, query)])

    return results


# ─── Query enhancement helpers ───────────────────────────────────────────────

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
