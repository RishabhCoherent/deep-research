"""SmartCrawler search: URL discovery + tiered web-content extraction.

Drop-in Tavily replacement that works entirely with free components:

  URL discovery (primary):  SearXNG Docker instance (http://localhost:8888)
                            → best content quality, requires docker-compose up -d
  URL discovery (fallback): DuckDuckGo via ddgs package (no Docker, no API key)
                            → automatic fallback when SearXNG is unavailable
  Tier 1 (content fetch):   httpx + full browser headers
  Tier 2 (content fetch):   scrapling AsyncFetcher (curl_cffi Chrome TLS)
                            → bypasses Cloudflare / Akamai / Shopify gates
  Tier 3 (content fetch):   scrapling DynamicFetcher (headless Playwright)
                            → bounded by PlaywrightBudget; SPA-only fallback
  Extract:                  trafilatura → regex tag-strip fallback
  Tiers 2 & 3 are optional: install via `pip install "scrapling[fetchers]"`
  and `playwright install chromium`. Missing deps → tier silently no-ops.

Returns [{url, title, snippet, score, published, full_text}] — a superset of
the Tavily response shape.  Callers that only read url/title/snippet/score/
published need zero changes.

Key differences vs Tavily:
  + Free — no API key, no quota
  + snippet = up to 800 chars of clean article text (vs ~200-char Tavily blurb)
  + full_text field with up to 8 000 chars of extracted content
  + Works without Docker (DDG fallback)
  - Slower than Tavily (~3-7 s per search vs ~1-2 s) due to per-URL fetching
  - Cloudflare pages require scrapling (Tier 2); JS-SPAs require Playwright (Tier 3)

URL discovery quality ranking (from benchmark):
  SearXNG > DDG  (SearXNG wins on full_text length, snippet quality, latency)
  DDG is used automatically when SearXNG Docker is not running.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import re
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Full browser headers — same validated set used in smartcrawler.py Tier-0
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Upgrade-Insecure-Requests": "1",
}

# Cloudflare / bot-gate challenge patterns — same regex as smartcrawler.py
_CF_RE = re.compile(
    r"just a moment|cf-browser-verification|enable javascript"
    r"|human verification|attention required",
    re.I,
)

_FETCH_TIMEOUT   = 12.0   # seconds per URL fetch
_MAX_WORKERS     = 5      # parallel URL fetches
_SNIPPET_LEN     = 800    # chars returned in the `snippet` field
_FULL_TEXT_LEN   = 8_000  # chars returned in the `full_text` field

_CACHE_DIR = Path.home() / ".research" / "cache" / "smartcrawler"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_key(query: str, news: bool, today: str) -> str:
    mode = "news" if news else "general"
    return hashlib.sha256(f"{query}|{mode}|{today}".encode()).hexdigest()


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
        path.write_text(
            json.dumps(results, default=str, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


# ── Per-URL fetch + extract ───────────────────────────────────────────────────

def _httpx_fetch(url: str) -> str:
    """Tier 1: httpx + browser headers. verify-then-retry on SSL failure."""
    import httpx
    import ssl as _ssl

    def _get(verify: bool) -> "httpx.Response":
        with httpx.Client(
            headers=_BROWSER_HEADERS,
            timeout=_FETCH_TIMEOUT,
            follow_redirects=True,
            verify=verify,
        ) as client:
            return client.get(url)

    try:
        resp = _get(verify=True)
    except (_ssl.SSLError, httpx.ConnectError) as exc:
        # Some marketing sites mis-serve intermediate certs; fall back to
        # verify=False since we only read public HTML (no secrets exchanged).
        if "ssl" in str(exc).lower() or "certificate" in str(exc).lower():
            try:
                resp = _get(verify=False)
            except Exception as exc2:
                log.debug("[smartcrawler_search] httpx SSL fallback failed %s: %s", url[:80], exc2)
                return ""
        else:
            return ""
    except Exception as exc:
        log.debug("[smartcrawler_search] httpx error %s: %s", url[:80], exc)
        return ""

    if resp.status_code != 200 or len(resp.content) < 500:
        return ""
    html = resp.text
    if _CF_RE.search(html[:2_000]):
        log.debug("[smartcrawler_search] Tier-1 CF-blocked: %s", url[:80])
        return ""
    return html


def _fetch_and_extract(url: str, pw_budget: object | None = None) -> dict:
    """Fetch a URL through the tier cascade and extract article text.

    Tier cascade:
      1. httpx + browser headers          (smartcrawler_search.py)
      2. scrapling curl_cffi (TLS)        (bot_bypass.scrapling_fetch)
      3. scrapling DynamicFetcher (JS)    (bot_bypass.playwright_fetch, bounded)

    Returns {"url", "title", "content", "published", "success", "tier"}.
    Never raises — all errors swallowed to DEBUG.
    """
    from research.tools import bot_bypass

    html = ""
    tier = "none"

    # Tier 1: httpx
    html = _httpx_fetch(url)
    if html:
        tier = "httpx"

    # Tier 2: scrapling curl_cffi (only if Tier 1 returned nothing)
    if not html:
        html = bot_bypass.scrapling_fetch(url, timeout=15)
        if html and not bot_bypass._looks_blocked(html):
            tier = "scrapling"
        elif html:
            html = ""  # still blocked — force escalation

    # Tier 3: Playwright (budget-bounded; only if Tiers 1-2 failed)
    if not html and pw_budget is not None:
        html = bot_bypass.playwright_fetch(url, pw_budget, timeout=20)
        if html:
            tier = "playwright"

    if not html:
        return {
            "url": url, "title": "", "content": "", "published": None,
            "success": False, "tier": "none",
        }

    # ── Extraction: trafilatura → regex strip fallback ──────────────────
    title = ""
    published = None
    text = ""
    try:
        import trafilatura

        text = trafilatura.extract(
            html,
            url=url,
            include_tables=True,
            favor_precision=True,
            deduplicate=True,
            no_fallback=False,
        ) or ""
        meta = trafilatura.extract_metadata(html, default_url=url)
        if meta:
            title = meta.title or ""
            published = str(meta.date)[:10] if meta.date else None
    except Exception as exc:
        log.debug("[smartcrawler_search] trafilatura error %s: %s", url[:80], exc)

    if text and len(text) > 100:
        return {
            "url": url,
            "title": title,
            "content": text[:_FULL_TEXT_LEN],
            "published": published,
            "success": True,
            "tier": tier,
        }

    # Regex tag-strip fallback
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    fallback_title = title_m.group(1).strip() if title_m else title
    stripped = re.sub(
        r"<(script|style|nav|footer|header|aside|form)[^>]*>.*?</\1>",
        " ", html, flags=re.IGNORECASE | re.DOTALL,
    )
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()

    if len(stripped) > 100:
        return {
            "url": url,
            "title": fallback_title,
            "content": stripped[:_FULL_TEXT_LEN],
            "published": None,
            "success": True,
            "tier": tier,
        }

    return {
        "url": url, "title": "", "content": "", "published": None,
        "success": False, "tier": tier,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def is_smartcrawler_available() -> bool:
    """True if any URL-discovery backend is available (SearXNG OR DDG).

    SearXNG requires Docker; DDG requires only the ddgs package.
    Returns True if either is reachable/importable.
    """
    try:
        from research.tools.searxng import is_searxng_available
        if is_searxng_available():
            return True
    except Exception:
        pass
    try:
        from research.tools.ddg import is_ddg_available
        return is_ddg_available()
    except Exception:
        return False


def search_with_smartcrawler(
    query: str,
    max_results: int = 5,
    news_only: bool = False,
    use_cache: bool = True,
    playwright_budget: int = 3,
) -> list[dict]:
    """Search the web using URL discovery + smartcrawler content fetching.

    Pipeline:
      1a. SearXNG discovers candidate URLs (primary — best quality)
      1b. DDG discovers candidate URLs if SearXNG is unavailable (free fallback)
      2.  ThreadPoolExecutor fetches up to 2× max_results URLs concurrently
      3.  trafilatura extracts clean article text; httpx regex strips as fallback
      4.  Results are merged: fetched content enriches seed metadata

    Args:
        query:       Search query string.
        max_results: Number of enriched results to return (default 5, max 10).
        news_only:   If True, use news category (recency-focused).
        use_cache:   Cache results keyed by (query, mode, today). Default True.
        playwright_budget: Max Playwright (Tier 3) renders for this search call.
                     Each render is ~5-20s and CPU-heavy; 3 is a safe ceiling.
                     Set to 0 to disable the Playwright tier entirely.

    Returns:
        List of dicts with keys: url, title, snippet, score, published, full_text.
        Empty list if both SearXNG and DDG are unavailable.
    """
    today = date.today().isoformat()
    max_results = min(max(1, max_results), 10)

    if use_cache:
        key = _cache_key(query, news_only, today)
        cached = _load_cache(key)
        if cached is not None:
            log.debug("[smartcrawler_search] cache hit: %s", query[:60])
            return cached

    # ── Step 1: URL discovery — SearXNG primary, DDG fallback ───────────
    seed_count = max(max_results * 2, 8)  # fetch more than needed; filter after
    seed: list[dict] = []
    backend_used = "none"

    # 1a. Try SearXNG (higher quality — requires Docker)
    try:
        from research.tools.searxng import (
            search_searxng,
            search_searxng_news,
            is_searxng_available,
        )
        if is_searxng_available():
            try:
                seed = (
                    search_searxng_news(query, max_results=seed_count)
                    if news_only
                    else search_searxng(query, max_results=seed_count)
                )
                if seed:
                    backend_used = "searxng"
            except Exception as exc:
                log.debug("[smartcrawler_search] SearXNG query failed: %s", exc)
    except ImportError:
        pass

    # 1b. Fallback to DDG (no Docker, no API key — always available)
    if not seed:
        try:
            from research.tools.ddg import search_ddg, search_ddg_news, is_ddg_available
            if is_ddg_available():
                try:
                    seed = (
                        search_ddg_news(query, max_results=seed_count)
                        if news_only
                        else search_ddg(query, max_results=seed_count)
                    )
                    if seed:
                        backend_used = "ddg"
                except Exception as exc:
                    log.debug("[smartcrawler_search] DDG query failed: %s", exc)
        except ImportError:
            pass

    if not seed:
        log.debug(
            "[smartcrawler_search] all URL discovery backends failed for: %s", query[:60]
        )
        return []

    log.debug("[smartcrawler_search] using backend=%s for: %s", backend_used, query[:60])

    # ── Step 2: Parallel content fetch with tier cascade ────────────────
    from research.tools.bot_bypass import PlaywrightBudget

    urls = [r["url"] for r in seed if r.get("url")][:seed_count]
    fetched: dict[str, dict] = {}
    pw_budget = PlaywrightBudget(playwright_budget)

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=_MAX_WORKERS, thread_name_prefix="sc_fetch_"
    ) as pool:
        future_to_url = {
            pool.submit(_fetch_and_extract, u, pw_budget): u for u in urls
        }
        done, _ = concurrent.futures.wait(future_to_url, timeout=45)
        for fut in done:
            url = future_to_url[fut]
            try:
                fetched[url] = fut.result()
            except Exception:
                fetched[url] = {
                    "url": url, "title": "", "content": "", "published": None,
                    "success": False, "tier": "none",
                }

    # ── Step 3: Merge + format ────────────────────────────────────────────
    enriched: list[dict] = []
    for seed_item in seed:
        url = seed_item.get("url", "")
        if not url:
            continue
        fetch = fetched.get(url, {})

        content = fetch.get("content", "") if fetch.get("success") else ""
        snippet = content[:_SNIPPET_LEN] if content else seed_item.get("snippet", "")
        title = fetch.get("title") or seed_item.get("title", "")
        published = fetch.get("published") or seed_item.get("published")

        enriched.append({
            "url":       url,
            "title":     title,
            "snippet":   snippet,
            "score":     seed_item.get("score", 0.5),
            "published": published,
            "full_text": content,
            "tier":      fetch.get("tier", "none"),
        })
        if len(enriched) >= max_results:
            break

    log.debug(
        "[smartcrawler_search] %d results (news=%s, backend=%s) for: %s",
        len(enriched), news_only, backend_used, query[:60],
    )

    if use_cache and enriched:
        key = _cache_key(query, news_only, today)
        _save_cache(key, enriched)

    return enriched
