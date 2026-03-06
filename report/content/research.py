"""
Web research coordinator — wraps tools/search.py and tools/scraper.py.

Provides high-level research functions for the content engine.
Prioritizes government, financial, news, and company sources.
Competitor data is used for research context but never cited.
"""

from __future__ import annotations
import asyncio
import logging
from typing import Optional

from tools.search import search
from tools.scraper import scrape_url
from tools.citation import validate_citation, is_banned_source
from tools.source_classifier import classify_sources
from report.content.citations import CitationManager

logger = logging.getLogger(__name__)

# Search suffixes to bias toward primary sources
_PRIMARY_SUFFIXES = [
    'site:gov OR site:org OR annual report OR press release',
    'Reuters OR Bloomberg OR "financial report" OR SEC filing',
]


async def research_queries(
    queries: list[str],
    citation_mgr: CitationManager,
    section_id: str = "gen",
    max_per_query: int = 5,
    scrape_top: int = 2,
) -> list[dict]:
    """Execute search queries and collect results + citations.

    Three-layer filtering:
      1. Hardcoded banned list (instant, free) — catches known competitors
      2. LLM batch classification (gpt-4o-mini) — catches unknown competitors
      3. Publisher name check — final safety net before citation registration
    """
    raw_results = []
    urls_seen = set()

    # Build enhanced query list: original + one primary-source-biased variant
    enhanced_queries = list(queries)
    if queries:
        enhanced_queries.append(f"{queries[0]} {_PRIMARY_SUFFIXES[0]}")

    # ── Phase 1: Collect raw results, tag competitors ────────────────
    for query in enhanced_queries:
        try:
            results = await search(query, max_results=max_per_query, include_news=True)
        except Exception as e:
            logger.warning(f"Search failed for '{query}': {e}")
            results = []

        for r in results:
            url = r.get("url", "")
            if url in urls_seen:
                continue
            urls_seen.add(url)

            title = r.get("title", "")

            # Layer 1: Tag known competitor research firms (keep for research, no citation)
            if is_banned_source(url, title, ""):
                r["_is_competitor"] = True
                logger.debug(f"Competitor source (kept for research, no citation): {url}")

            raw_results.append(r)

    # ── Phase 2: LLM-based classification — tag more competitors ──────
    if raw_results:
        try:
            classifications = await classify_sources(raw_results)
            for r in raw_results:
                url = r.get("url", "")
                if classifications.get(url) == "competitor":
                    r["_is_competitor"] = True
                    logger.info(f"LLM tagged competitor source (no citation): {url}")
        except Exception as e:
            logger.warning(f"LLM source classification failed: {e}. Keeping all results.")

    # ── Phase 3: Register citations only for non-competitor results ───
    all_results = []
    for r in raw_results:
        url = r.get("url", "")
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        source = r.get("source", "")

        if url and title and not r.get("_is_competitor"):
            publisher = _infer_publisher(url, source)

            # Layer 3: Final check — publisher name isn't a competitor
            if is_banned_source("", title, publisher):
                r["_is_competitor"] = True
                logger.debug(f"Competitor by publisher (no citation): {publisher}")
            else:
                date = r.get("date", "")
                cid = citation_mgr.add(
                    url=url, title=title, publisher=publisher,
                    date=date, snippet=snippet, section_id=section_id,
                )
                if cid:
                    r["citation_id"] = cid

        all_results.append(r)

    # ── Phase 4: Scrape top URLs for richer content ───────────────────
    # Scrape both primary and competitor URLs — all data is useful for research
    if scrape_top > 0 and all_results:
        urls_to_scrape = []
        for r in all_results[:scrape_top * 3]:
            url = r.get("url", "")
            if url and not any(url == u for u in urls_to_scrape):
                urls_to_scrape.append(url)
            if len(urls_to_scrape) >= scrape_top:
                break

        scraped = await _scrape_urls(urls_to_scrape)
        for url, content in scraped.items():
            for r in all_results:
                if r.get("url") == url:
                    r["scraped_content"] = content
                    break

    return all_results


async def research_topic(
    topic: str,
    aspects: list[str],
    citation_mgr: CitationManager,
    section_id: str = "gen",
) -> list[dict]:
    """Research a topic from multiple angles."""
    queries = [f"{topic} {aspect}" for aspect in aspects]
    return await research_queries(queries, citation_mgr, section_id)


async def research_company(
    company_name: str,
    topic: str,
    citation_mgr: CitationManager,
    section_id: str = "com",
) -> list[dict]:
    """Research a specific company in the context of the market."""
    queries = [
        f"{company_name} company overview products annual report",
        f"{company_name} {topic} revenue investor presentation",
    ]
    return await research_queries(queries, citation_mgr, section_id, scrape_top=1)


async def research_region(
    region_name: str,
    topic: str,
    citation_mgr: CitationManager,
    section_id: str = "reg",
) -> list[dict]:
    """Research a region's market context."""
    queries = [
        f"{topic} {region_name} market analysis government report",
        f"{region_name} infrastructure development industry growth",
    ]
    return await research_queries(queries, citation_mgr, section_id, scrape_top=1)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _infer_publisher(url: str, source: str) -> str:
    """Infer publisher name from URL domain."""
    url_lower = url.lower()
    known = {
        # News & Financial
        "reuters.com": "Reuters",
        "bloomberg.com": "Bloomberg",
        "wsj.com": "The Wall Street Journal",
        "ft.com": "Financial Times",
        "cnbc.com": "CNBC",
        "bbc.com": "BBC",
        "bbc.co.uk": "BBC",
        "nytimes.com": "The New York Times",
        "economist.com": "The Economist",
        "forbes.com": "Forbes",
        "businesswire.com": "Business Wire",
        "prnewswire.com": "PR Newswire",
        "globenewswire.com": "GlobeNewsWire",
        # Government & Regulatory
        "sec.gov": "U.S. Securities and Exchange Commission",
        "fda.gov": "U.S. Food and Drug Administration",
        "who.int": "World Health Organization",
        "nih.gov": "National Institutes of Health",
        "cdc.gov": "U.S. Centers for Disease Control",
        "epa.gov": "U.S. Environmental Protection Agency",
        "energy.gov": "U.S. Department of Energy",
        "eia.gov": "U.S. Energy Information Administration",
        "bls.gov": "U.S. Bureau of Labor Statistics",
        "census.gov": "U.S. Census Bureau",
        "worldbank.org": "The World Bank",
        "imf.org": "International Monetary Fund",
        "europa.eu": "European Commission",
        "ema.europa.eu": "European Medicines Agency",
        "clinicaltrials.gov": "ClinicalTrials.gov",
        "trade.gov": "U.S. International Trade Administration",
        "usda.gov": "U.S. Department of Agriculture",
        "osha.gov": "U.S. OSHA",
        # Academic & Research
        "nature.com": "Nature",
        "sciencedirect.com": "ScienceDirect",
        "springer.com": "Springer",
        "wiley.com": "Wiley",
        "pubmed.ncbi.nlm.nih.gov": "PubMed",
        "ncbi.nlm.nih.gov": "NCBI / PubMed",
        "ieee.org": "IEEE",
        "mdpi.com": "MDPI",
        # Industry
        "mckinsey.com": "McKinsey & Company",
        "deloitte.com": "Deloitte",
        "pwc.com": "PwC",
        "ey.com": "Ernst & Young",
        "kpmg.com": "KPMG",
        "accenture.com": "Accenture",
    }
    for domain, name in known.items():
        if domain in url_lower:
            return name
    # Extract domain
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        host = host.replace("www.", "")
        return host.split(".")[0].capitalize() if host else source
    except Exception:
        return source


async def _scrape_urls(urls: list[str]) -> dict[str, str]:
    """Scrape multiple URLs in parallel. Returns {url: content}."""
    results = {}

    async def _scrape_one(url):
        try:
            page = await scrape_url(url)
            if page and page.get("content"):
                results[url] = page["content"][:5000]  # Cap for LLM context
        except Exception as e:
            logger.debug(f"Scrape failed for {url}: {e}")

    await asyncio.gather(*[_scrape_one(u) for u in urls], return_exceptions=True)
    return results


def build_research_context(results: list[dict], max_chars: int = 8000) -> str:
    """Format research results into a context string for LLM prompts.

    Competitor data is included for research context but without citation IDs,
    so the LLM can use the information without citing competitor sources.
    """
    parts = []
    total = 0

    # Primary sources first (with citations), then competitor data (no citations)
    sorted_results = sorted(results, key=lambda r: r.get("_is_competitor", False))

    for r in sorted_results:
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        scraped = r.get("scraped_content", "")

        # Prefer scraped content, fall back to snippet
        content = scraped[:2000] if scraped else snippet
        if not content:
            continue

        # Only show citation IDs for non-competitor sources
        if r.get("_is_competitor"):
            entry = f"Background Data: {title}\n{content}\n"
        else:
            cid = r.get("citation_id", "")
            cid_str = f" [{cid}]" if cid else ""
            entry = f"Source: {title}{cid_str}\n{content}\n"

        if total + len(entry) > max_chars:
            break
        parts.append(entry)
        total += len(entry)

    return "\n---\n".join(parts)
