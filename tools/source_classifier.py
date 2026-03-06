"""
LLM-based source classification — identifies market research firms dynamically.

Two-layer approach:
1. Hardcoded BANNED_DOMAINS in citation.py catches known competitors instantly (free)
2. This module uses gpt-4o-mini to classify remaining sources as primary vs competitor

Domain-level caching ensures each domain is classified at most once per session.
"""

import json
import logging
from urllib.parse import urlparse

from config import get_llm
from tools.citation import BANNED_DOMAINS

logger = logging.getLogger(__name__)

# Domain-level cache: domain → "primary" | "competitor"
# Persists for the lifetime of the process (one report generation run)
_domain_cache: dict[str, str] = {}

# Pre-seed cache with known primary domains (never need LLM classification)
_KNOWN_PRIMARY_DOMAINS = {
    "reuters.com", "bloomberg.com", "wsj.com", "ft.com", "cnbc.com",
    "bbc.com", "bbc.co.uk", "nytimes.com", "economist.com", "forbes.com",
    "businesswire.com", "prnewswire.com", "globenewswire.com",
    "sec.gov", "fda.gov", "who.int", "nih.gov", "cdc.gov", "epa.gov",
    "energy.gov", "eia.gov", "bls.gov", "census.gov", "trade.gov",
    "usda.gov", "osha.gov", "clinicaltrials.gov",
    "worldbank.org", "imf.org", "europa.eu", "ema.europa.eu",
    "nature.com", "sciencedirect.com", "springer.com", "wiley.com",
    "ieee.org", "mdpi.com", "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov",
    "wikipedia.org", "linkedin.com", "youtube.com",
}

# Tier 1: Gold-standard sources whose data should be preferred when numbers conflict.
# These are the most cited, most reliable industry trackers and news outlets.
TIER1_DOMAINS = {
    # Premier industry trackers
    "idc.com", "counterpointresearch.com", "canalys.com", "omdia.com",
    "techinsights.com",
    # Data platforms
    "statista.com",
    # NOTE: StatCounter (gs.statcounter.com) intentionally excluded from TIER-1.
    # It measures web TRAFFIC/USAGE share, not industry shipment/revenue market share.
    # Treating StatCounter as TIER-1 causes market share numbers to be wrong
    # (e.g., Apple 31% usage share vs 20% shipment share).
    # Major financial / business news
    "reuters.com", "bloomberg.com", "wsj.com", "ft.com", "cnbc.com",
    "nytimes.com", "economist.com", "forbes.com",
    # Government / intl orgs
    "sec.gov", "worldbank.org", "imf.org", "bls.gov", "census.gov",
    "trade.gov",
    # Major tech news (often cite primary tracker data)
    "techcrunch.com", "theverge.com", "arstechnica.com", "wired.com",
    "gsmarena.com", "appleinsider.com", "macrumors.com",
    "androidheadlines.com",
    # Academic
    "nature.com", "sciencedirect.com",
    # Press releases (company-sourced)
    "businesswire.com", "prnewswire.com", "globenewswire.com",
}


def get_source_tier(url: str) -> int:
    """Return credibility tier for a URL. 1 = most reliable, 3 = unknown.

    Tier 1: Major industry trackers, news outlets, government sources.
    Tier 2: Known primary domains (general news, tech blogs, etc.).
    Tier 3: Everything else (unknown aggregator sites, SEO content farms).
    """
    domain = _extract_domain(url)
    # Check tier 1 first
    for t1 in TIER1_DOMAINS:
        if t1 in domain or domain in t1:
            return 1
    # Check known primary domains (tier 2)
    for kp in _KNOWN_PRIMARY_DOMAINS:
        if kp in domain or domain in kp:
            return 2
    # Check banned (competitor) — still tier 3
    for banned in BANNED_DOMAINS:
        if banned in domain or domain in banned:
            return 3
    # Unknown = tier 3
    return 3

_CLASSIFIER_PROMPT = """Classify each source as "primary" or "competitor".

"primary" = government agency, news outlet, company website or filing, academic journal,
            press release service, trade association, international organization,
            encyclopedia, general information site, e-commerce, social media,
            industry blog, technology site

"competitor" = market research firm, market analysis provider, market intelligence company,
               consulting firm that publishes and SELLS market research reports,
               any company whose main business is selling market size/forecast reports

Return ONLY a valid JSON object mapping each number to "primary" or "competitor".
No explanation, no markdown, just the JSON.

Sources:
{sources}"""


def _extract_domain(url: str) -> str:
    """Extract the registerable domain from a URL."""
    try:
        host = urlparse(url).hostname or ""
        host = host.lower().replace("www.", "")
        return host
    except Exception:
        return ""


def _get_cached(domain: str) -> str | None:
    """Check if domain is already classified."""
    if domain in _domain_cache:
        return _domain_cache[domain]
    # Check known primary domains
    if domain in _KNOWN_PRIMARY_DOMAINS:
        _domain_cache[domain] = "primary"
        return "primary"
    # Check hardcoded banned domains
    for banned in BANNED_DOMAINS:
        if banned in domain or domain in banned:
            _domain_cache[domain] = "competitor"
            return "competitor"
    return None


async def classify_sources(results: list[dict]) -> dict[str, str]:
    """Classify search results as 'primary' or 'competitor'.

    Uses domain-level caching + LLM batch classification.

    Args:
        results: list of {url, title, ...} dicts from search

    Returns:
        {url: "primary" | "competitor"} for all input URLs
    """
    classifications = {}
    uncached = []  # (index, url, domain, title)

    for r in results:
        url = r.get("url", "")
        if not url:
            continue
        domain = _extract_domain(url)
        cached = _get_cached(domain)
        if cached:
            classifications[url] = cached
        else:
            title = r.get("title", "")
            uncached.append((len(uncached), url, domain, title))

    # If everything was cached, no LLM call needed
    if not uncached:
        return classifications

    # Batch classify uncached domains with LLM
    try:
        source_lines = []
        for idx, url, domain, title in uncached:
            source_lines.append(f"{idx + 1}. {domain} — \"{title}\"")
        sources_text = "\n".join(source_lines)

        llm = get_llm("organizer")  # gpt-4o-mini, cheapest
        response = llm.invoke([
            {"role": "system", "content": "You classify web sources. Respond with only valid JSON."},
            {"role": "user", "content": _CLASSIFIER_PROMPT.format(sources=sources_text)},
        ])

        # Parse JSON response
        text = response.content.strip()
        # Handle markdown code blocks
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        result_map = json.loads(text)

        # Apply classifications and cache domains
        for idx, url, domain, title in uncached:
            key = str(idx + 1)
            classification = result_map.get(key, "primary")
            # Normalize to "primary" or "competitor"
            if "compet" in classification.lower():
                classification = "competitor"
            else:
                classification = "primary"

            _domain_cache[domain] = classification
            classifications[url] = classification

            if classification == "competitor":
                logger.info(f"LLM classified as competitor: {domain} — \"{title}\"")

    except Exception as e:
        logger.warning(f"Source classification failed: {e}. Defaulting uncached to primary.")
        # On failure, allow all uncached through (conservative — don't block good sources)
        for idx, url, domain, title in uncached:
            classifications[url] = "primary"

    return classifications


def get_cache_stats() -> dict:
    """Return cache statistics for debugging."""
    primary = sum(1 for v in _domain_cache.values() if v == "primary")
    competitor = sum(1 for v in _domain_cache.values() if v == "competitor")
    return {
        "total_cached": len(_domain_cache),
        "primary": primary,
        "competitor": competitor,
    }
