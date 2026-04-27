"""Topic -> source documents via SearXNG + SmartCrawler.

Wraps the working SmartCrawler search tool from backend2 (which uses the local
Docker SearXNG instance on :8888 and fetches article content via trafilatura +
optional bot-bypass).  Isolated here so claim_clustering has exactly one
dependency on backend2/ and can be re-pointed at a different search backend
later without touching the rest of the pipeline.

Returns SourceDocument objects carrying URL, title, full_text, domain tier,
publication date. The extractor reads full_text to pull claims.
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

# Ensure backend2 is importable regardless of where this module is executed.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_BACKEND2_ROOT = os.path.join(_REPO_ROOT, "backend2")
if _BACKEND2_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND2_ROOT)


@dataclass
class SourceDocument:
    """One fetched source ready for claim extraction."""
    url: str
    title: str
    snippet: str
    full_text: str
    domain: str
    tier: str = "unknown"        # government / analyst_firm / blog / ...
    published: Optional[str] = None
    rank: int = 0                # position in the search results (1 = top)
    # Schema.org / OpenGraph / microdata extracted from raw HTML when available.
    # Keys are the original schema.org property names (name, about, description,
    # datePublished, keywords, ...). Empty when site doesn't publish structured
    # data. The extractor uses this as high-confidence framing input.
    structured_metadata: dict = field(default_factory=dict)

    @property
    def has_content(self) -> bool:
        return bool(self.full_text and len(self.full_text) >= 400)


# ── Schema.org / structured-metadata pre-pass ───────────────────────────────

# Tiny in-process cache so re-runs on the same URL don't re-fetch HTML.
_METADATA_CACHE: dict[str, dict] = {}

# Schema.org @types most relevant to market-research framing. We pull from
# any of these (in priority order).
_USEFUL_TYPES = (
    "Report", "Dataset", "Article", "NewsArticle",
    "ScholarlyArticle", "Product", "WebPage",
)

# Property names we keep from a JSON-LD/og: block. Trim everything else.
_USEFUL_PROPS = {
    "name", "headline", "about", "description", "keywords",
    "datePublished", "dateModified", "author", "publisher",
    "mainEntity", "isPartOf", "industry", "category",
    # OpenGraph
    "og:title", "og:description", "og:type", "og:site_name",
}


def _flatten_for_metadata(data) -> dict:
    """Pull useful keys out of a possibly-nested JSON-LD / dict structure."""
    out: dict = {}
    if isinstance(data, dict):
        for k, v in data.items():
            kk = str(k).split(":")[-1] if ":" in str(k) else str(k)  # drop @
            if kk in _USEFUL_PROPS or k in _USEFUL_PROPS:
                if isinstance(v, (str, int, float)):
                    out[kk] = str(v)[:300]
                elif isinstance(v, dict):
                    nested = _flatten_for_metadata(v)
                    if nested:
                        out[kk] = "; ".join(f"{a}={b}" for a, b in nested.items() if isinstance(b, str))[:300]
                elif isinstance(v, list) and v:
                    pieces = []
                    for item in v[:5]:
                        if isinstance(item, str):
                            pieces.append(item)
                        elif isinstance(item, dict):
                            n = _flatten_for_metadata(item)
                            pieces.append(n.get("name") or n.get("headline") or "")
                    out[kk] = "; ".join(p for p in pieces if p)[:300]
    return out


def _extract_structured_metadata(url: str, *, timeout: float = 6.0) -> dict:
    """Lightweight pre-pass: fetch URL, parse JSON-LD/og:/microdata via extruct.

    Returns a flat dict of {schema_property -> string value}. Empty if the
    site doesn't publish structured data or the fetch fails. Cached
    in-process by URL.
    """
    if url in _METADATA_CACHE:
        return _METADATA_CACHE[url]

    out: dict = {}
    try:
        import httpx
        import extruct
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                _METADATA_CACHE[url] = out
                return out
            html_text = resp.text[:300_000]   # cap pathologically big pages

        data = extruct.extract(
            html_text, base_url=url,
            syntaxes=["json-ld", "opengraph", "microdata"],
            errors="ignore",
        )

        # JSON-LD blocks (priority — most info-rich for B2B research)
        for block in data.get("json-ld") or []:
            if not isinstance(block, dict):
                continue
            t = block.get("@type") or block.get("type")
            if isinstance(t, list):
                t = next((x for x in t if x in _USEFUL_TYPES), t[0] if t else "")
            if t and t not in _USEFUL_TYPES and t not in ("Organization", "BreadcrumbList"):
                continue
            flat = _flatten_for_metadata(block)
            for k, v in flat.items():
                # Don't overwrite — keep the first useful value per key
                out.setdefault(k, v)

        # OpenGraph
        for block in data.get("opengraph") or []:
            if not isinstance(block, dict):
                continue
            props = block.get("properties") or []
            if isinstance(props, list):
                for prop in props:
                    if isinstance(prop, (list, tuple)) and len(prop) == 2:
                        k, v = prop
                        if k in _USEFUL_PROPS and isinstance(v, str):
                            out.setdefault(k.split(":")[-1], v[:300])

        # Microdata as last resort
        for block in data.get("microdata") or []:
            if isinstance(block, dict):
                flat = _flatten_for_metadata(block.get("properties", block))
                for k, v in flat.items():
                    out.setdefault(k, v)

    except Exception:
        # Network error, parse error, missing dep — silently skip
        pass

    _METADATA_CACHE[url] = out
    return out


def _populate_structured_metadata(sources: list["SourceDocument"], *,
                                   max_workers: int = 8) -> None:
    """In-place: fetch + parse schema.org for every source in parallel.

    Each fetch is bounded by `_extract_structured_metadata`'s timeout. Failures
    leave `structured_metadata` empty, which is the safe no-op state.
    """
    if not sources:
        return
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_extract_structured_metadata, s.url): s
            for s in sources
        }
        for fut in as_completed(futures):
            src = futures[fut]
            try:
                src.structured_metadata = fut.result() or {}
            except Exception:
                src.structured_metadata = {}


# ── Source-tier classification ──────────────────────────────────────────────

# Minimal tier lookup. Extended later by migrating the richer mapping from
# backend2/research/pipeline/authority.yaml.
_TIER_BY_DOMAIN = {
    # government
    "europa.eu": "government", "ec.europa.eu": "government",
    "sec.gov": "government", "doe.gov": "government", "energy.gov": "government",
    "treasury.gov": "government",
    # multilateral
    "oecd.org": "multilateral", "worldbank.org": "multilateral",
    "imf.org": "multilateral", "un.org": "multilateral",
    # industry bodies / standards
    "iea.org": "industry_body", "irena.org": "industry_body",
    "jpr.com": "industry_body", "semi.org": "industry_body",
    "gsmarena.com": "industry_body",
    # tier-1 media
    "bloomberg.com": "tier1_media", "ft.com": "tier1_media",
    "wsj.com": "tier1_media", "reuters.com": "tier1_media",
    "economist.com": "tier1_media", "nytimes.com": "tier1_media",
    # analyst firms (non-banned — BEWARE the ban list before citing)
    "statista.com": "analyst_firm", "idc.com": "analyst_firm",
    "gartner.com": "analyst_firm", "bnef.com": "analyst_firm",
    "mckinsey.com": "analyst_firm", "bcg.com": "analyst_firm",
    # trade press
    "electrek.co": "trade_press", "tomshardware.com": "trade_press",
    "theverge.com": "trade_press", "techcrunch.com": "trade_press",
    "engadget.com": "trade_press", "arstechnica.com": "trade_press",
}


def classify_tier(url: str) -> str:
    """Lookup tier by longest matching domain suffix."""
    host = urlparse(url).netloc.lower().lstrip("www.")
    # exact match
    if host in _TIER_BY_DOMAIN:
        return _TIER_BY_DOMAIN[host]
    # suffix fallback
    for domain, tier in _TIER_BY_DOMAIN.items():
        if host.endswith("." + domain) or host == domain:
            return tier
    return "blog"


# ── Public API ──────────────────────────────────────────────────────────────

def search_topic(topic: str, *, max_sources: int = 15, news_only: bool = False) -> list[SourceDocument]:
    """Run one SmartCrawler search and return enriched SourceDocument list.

    Splits the budget across:
      - general search (default: 2/3 of max_sources)
      - news search    (default: 1/3 of max_sources) when news_only=False

    When news_only=True, all hits come from the news backend.
    """
    from research.tools.smartcrawler_search import (  # type: ignore
        search_with_smartcrawler, is_smartcrawler_available,
    )

    if not is_smartcrawler_available():
        raise RuntimeError(
            "SmartCrawler unavailable: start SearXNG Docker on :8888 "
            "(docker-compose up -d) or install the ddgs package."
        )

    docs: list[SourceDocument] = []
    seen_urls: set[str] = set()

    def _ingest(results: list[dict]) -> None:
        for r in results:
            url = (r.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            full = r.get("full_text") or r.get("snippet") or ""
            docs.append(SourceDocument(
                url=url,
                title=r.get("title") or url,
                snippet=(r.get("snippet") or "")[:400],
                full_text=full,
                domain=urlparse(url).netloc.lower().lstrip("www."),
                tier=classify_tier(url),
                published=r.get("published"),
                rank=len(docs) + 1,
            ))

    if news_only:
        _ingest(search_with_smartcrawler(topic, max_results=max_sources, news_only=True))
    else:
        general_budget = max(1, int(max_sources * 2 / 3))
        news_budget    = max(1, max_sources - general_budget)
        _ingest(search_with_smartcrawler(topic, max_results=general_budget, news_only=False))
        _ingest(search_with_smartcrawler(topic, max_results=news_budget, news_only=True))

    final = docs[:max_sources]
    _populate_structured_metadata(final)
    return final


# ── Cap-before-scrape architecture (Phase A → rank → Phase C) ───────────────

def _discover_urls_one_query(query: str, max_per_query: int) -> list[dict]:
    """PHASE A — URL discovery for one query. Hits SearXNG only, no scraping.

    Returns list of {url, title, snippet, score, query, search_rank} where
    search_rank is the position within this query's results (1 = top).
    """
    from research.tools.searxng import search_searxng  # type: ignore
    raw = search_searxng(query, max_results=max_per_query) or []
    out: list[dict] = []
    for i, r in enumerate(raw):
        url = (r.get("url") or "").strip()
        if not url:
            continue
        out.append({
            "url":         url,
            "title":       r.get("title") or url,
            "snippet":     r.get("snippet") or "",
            "score":       float(r.get("score") or 0.0),
            "query":       query,
            "search_rank": i + 1,   # 1-based position
            "published":   r.get("published"),
        })
    return out


def _discover_urls_parallel(queries: list[str], max_per_query: int = 12,
                             max_query_workers: int = 8) -> list[dict]:
    """PHASE A (parallel) — discover URLs across many queries simultaneously.

    SearXNG metadata calls are cheap (~100-500ms each), so all queries can run
    in parallel without saturating the local Docker instance. Returns all URL
    records (with duplicates across queries — dedupe happens in ranking step).
    """
    if not queries:
        return []
    all_records: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_query_workers) as pool:
        futures = {
            pool.submit(_discover_urls_one_query, q, max_per_query): q
            for q in queries
        }
        for fut in as_completed(futures):
            q = futures[fut]
            try:
                records = fut.result()
            except Exception as exc:
                print(f"[search/discover] {q!r} failed: {exc}")
                continue
            all_records.extend(records)
    return all_records


# Tier-priority order (lower = keep first when capping)
_TIER_PRIORITY = {
    "government": 0, "multilateral": 1, "industry_body": 2,
    "tier1_media": 3, "analyst_firm": 4, "trade_press": 5,
    "blog": 6, "unknown": 7,
}


def _rank_and_cap_urls(records: list[dict], max_sources: int) -> list[dict]:
    """PHASE B — dedupe URLs across queries, rank, take top N.

    Ranking criteria (in order, lower is better):
      1. Domain tier (gov > analyst > blog)
      2. Cross-query agreement (URL appeared from MORE queries = more relevant)
      3. Best (lowest) search_rank across the queries that returned it
      4. Best score across queries

    A URL that appeared from 4 different queries with rank=2 in one of them
    will outrank a URL that appeared from 1 query at rank=1.
    """
    # Dedupe by URL, accumulating (queries seen, best rank, best score)
    by_url: dict[str, dict] = {}
    for r in records:
        url = r["url"]
        if url not in by_url:
            by_url[url] = {
                "url": url,
                "title": r.get("title") or url,
                "snippet": (r.get("snippet") or "")[:400],
                "domain": urlparse(url).netloc.lower().lstrip("www."),
                "tier": classify_tier(url),
                "published": r.get("published"),
                "queries_hit": {r["query"]},
                "best_rank": r.get("search_rank") or 999,
                "best_score": r.get("score") or 0.0,
            }
        else:
            agg = by_url[url]
            agg["queries_hit"].add(r["query"])
            agg["best_rank"] = min(agg["best_rank"], r.get("search_rank") or 999)
            agg["best_score"] = max(agg["best_score"], r.get("score") or 0.0)

    # Convert to sortable list, score by (tier, -agreement, rank)
    candidates = list(by_url.values())
    candidates.sort(key=lambda c: (
        _TIER_PRIORITY.get(c["tier"], 9),
        -len(c["queries_hit"]),     # more queries = better, so negate
        c["best_rank"],
        -c["best_score"],
    ))
    return candidates[:max_sources]


def _scrape_one_url(url: str, pw_budget) -> dict:
    """PHASE C — single-URL scrape via SmartCrawler's tier escalation."""
    from research.tools.smartcrawler_search import _fetch_and_extract  # type: ignore
    try:
        return _fetch_and_extract(url, pw_budget=pw_budget)
    except Exception as exc:
        return {"url": url, "title": "", "content": "",
                "published": None, "success": False, "tier": "error",
                "error": str(exc)}


def _scrape_urls_parallel(url_records: list[dict], *,
                          max_workers: int = 8,
                          playwright_budget: int = 30) -> list[SourceDocument]:
    """PHASE C — scrape only the curated URL list, in parallel.

    Uses SmartCrawler's `_fetch_and_extract` for each URL (httpx → scrapling →
    Playwright tiers). PlaywrightBudget bounds the number of headless browser
    instances spawned across the entire batch.
    """
    if not url_records:
        return []
    try:
        from research.tools.bot_bypass import PlaywrightBudget  # type: ignore
        pw_budget = PlaywrightBudget(playwright_budget)
    except Exception:
        pw_budget = None

    docs: list[SourceDocument] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_scrape_one_url, rec["url"], pw_budget): rec
            for rec in url_records
        }
        for fut in as_completed(futures):
            rec = futures[fut]
            try:
                scraped = fut.result()
            except Exception:
                scraped = {"url": rec["url"], "content": "", "title": "",
                           "success": False, "tier": "error"}
            content = scraped.get("content") or rec.get("snippet") or ""
            docs.append(SourceDocument(
                url=rec["url"],
                title=scraped.get("title") or rec.get("title") or rec["url"],
                snippet=(rec.get("snippet") or content[:400] or "")[:400],
                full_text=content,
                domain=rec["domain"],
                tier=rec["tier"],
                published=scraped.get("published") or rec.get("published"),
                rank=0,   # filled below in original-order
            ))

    # Preserve original ranking order from _rank_and_cap_urls
    rank_map = {rec["url"]: i + 1 for i, rec in enumerate(url_records)}
    docs.sort(key=lambda d: rank_map.get(d.url, 999))
    for i, d in enumerate(docs):
        d.rank = i + 1
    return docs


def search_multiple_queries(
    queries: list[str], *, max_per_query: int = 12, max_query_workers: int = 8,
    max_sources: int = 25, scrape_workers: int = 8, playwright_budget: int = 30,
) -> list[SourceDocument]:
    """Cap-before-scrape pipeline across multiple search queries.

    Phase A (parallel SearXNG discovery):
      Run every query against SearXNG in parallel, collect URL+metadata.
      Cheap (~5-10s for 30+ queries) — no page content fetched yet.

    Phase B (rank + cap):
      Dedupe URLs across queries, rank by (tier, cross-query agreement,
      search rank, score), take top `max_sources`.

    Phase C (parallel scrape on the curated set):
      For only the kept URLs, run SmartCrawler's tier-escalation scraper.
      We pay full scrape cost only on URLs that survive ranking.

    Phase D (schema.org pre-pass):
      For the kept sources, fetch JSON-LD/og: metadata in parallel.

    This avoids the previous architecture's waste of scraping ~5-9× more
    URLs than were retained.
    """
    if not queries:
        return []

    # Phase A — discover URL universe across all queries
    records = _discover_urls_parallel(
        queries, max_per_query=max_per_query, max_query_workers=max_query_workers,
    )
    print(f"[search] Phase A: {len(records)} raw URL hits across "
          f"{len(queries)} queries -> {len({r['url'] for r in records})} unique")

    # Phase B — rank + cap before any expensive scraping
    kept = _rank_and_cap_urls(records, max_sources=max_sources)
    print(f"[search] Phase B: kept top {len(kept)} URLs by tier+frequency+rank "
          f"(would have scraped {len({r['url'] for r in records})} otherwise)")

    # Phase C — scrape only the kept set
    docs = _scrape_urls_parallel(
        kept, max_workers=scrape_workers, playwright_budget=playwright_budget,
    )
    n_with_content = sum(1 for d in docs if d.has_content)
    print(f"[search] Phase C: scraped {len(docs)} URLs, "
          f"{n_with_content} with substantive text")

    # Phase D — schema.org metadata pre-pass on the kept sources
    _populate_structured_metadata(docs)
    n_with_md = sum(1 for d in docs if d.structured_metadata)
    print(f"[search] Phase D: schema.org metadata found on {n_with_md}/{len(docs)} URLs")

    return docs
