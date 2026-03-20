"""
Citation validation and banned-source enforcement.

Two-layer defense:
1. Programmatic check at citation creation time (researcher)
2. Programmatic check at review time (reviewer)
"""

# Research firms whose data we can USE but must never CITE
BANNED_SOURCES = {
    # Major market research competitors
    "grand view research", "grandviewresearch",
    "allied market research", "alliedmarketresearch",
    "mordor intelligence", "mordorintelligence",
    "fortune business insights", "fortunebusinessinsights",
    "marketsandmarkets", "markets and markets",
    "emergen research", "emergenresearch",
    "precedence research", "precedenceresearch",
    "transparency market research", "transparencymarketresearch",
    "report ocean", "reportocean",
    "data bridge", "databridgemarketresearch",
    "vantage market research", "vantagemarketresearch",
    "coherent market insights", "coherentmarketinsights",
    "polaris market research", "polarismarketresearch",
    "stellarmr", "stellar market research",
    "straits research", "straitsresearch",
    "verified market research", "verifiedmarketresearch",
    "zion market research", "zionmarketresearch",
    "imarcgroup", "imarc group",
    "global market insights", "globalmarketinsights",
    "research and markets", "researchandmarkets",
    "frost & sullivan", "frost sullivan",
    "technavio",
    "inkwood research",
    "maximize market research",
    "the insight partners", "theinsightpartners",
    "exactitude consultancy",
    "meticulous research",
    "custom market insights",
    "reports and data", "reportsanddata",
    "futuremarketinsights", "future market insights",
    "industry arc", "industryarc",
    "spherical insights",
    "skyquest",
    "knowledge sourcing intelligence",
    # Additional competitors
    "stratview research", "stratviewresearch",
    "the business research company", "thebusinessresearchcompany",
    "market research future", "marketresearchfuture",
    "acumen research", "acumenresearchandconsulting",
    "expert market research", "expertmarketresearch",
    "adroit market research",
    "quince market insights",
    "bonafide research",
    "astute analytica", "astuteanalytica",
    "market data forecast", "marketdataforecast",
    "p&s intelligence", "psmarketresearch",
    "fact.mr", "factmr",
    "persistence market research", "persistencemarketresearch",
    "renub research",
    "brandessence market research", "brandessenceresearch",
    "indexbox",
    "lucintel",
    "triton market research",
    "cognitive market research",
    "reportsinsights",
    "ken research", "kenresearch",
    "blueweave consulting", "blueweaveconsulting",
    "dataintelo",
    "market.us",
    "valuates reports",
    "360 research reports", "360researchreports",
    "prophecy market insights",
    "global industry analysts",
    "euromonitor",
    "mintel",
    "idc",  # Will only match as standalone in text check
    "gartner",
    "statista",
}

# Fast domain-level blocklist (checked before text-level scan)
BANNED_DOMAINS = {
    "grandviewresearch.com", "alliedmarketresearch.com",
    "mordorintelligence.com", "fortunebusinessinsights.com",
    "marketsandmarkets.com", "emergenresearch.com",
    "precedenceresearch.com", "transparencymarketresearch.com",
    "reportocean.com", "databridgemarketresearch.com",
    "vantagemarketresearch.com", "coherentmarketinsights.com",
    "polarismarketresearch.com", "stellarmr.com",
    "straitsresearch.com", "verifiedmarketresearch.com",
    "zionmarketresearch.com", "imarcgroup.com",
    "gminsights.com", "researchandmarkets.com",
    "frost.com", "technavio.com",
    "inkwoodresearch.com", "maximizemarketresearch.com",
    "theinsightpartners.com", "exactitudeconsultancy.com",
    "meticulousresearch.com", "reportsanddata.com",
    "futuremarketinsights.com", "industryarc.com",
    "sphericalinsights.com", "skyquestt.com",
    "stratviewresearch.com", "thebusinessresearchcompany.com",
    "marketresearchfuture.com", "acumenresearchandconsulting.com",
    "expertmarketresearch.com", "adroitmarketresearch.com",
    "astuteanalytica.com", "marketdataforecast.com",
    "psmarketresearch.com", "factmr.com",
    "persistencemarketresearch.com", "renub.com",
    "brandessenceresearch.com", "lucintel.com",
    "kenresearch.com", "blueweaveconsulting.com",
    "dataintelo.com", "market.us", "valuatesreports.com",
    "360researchreports.com", "prophecymarketinsights.com",
    "globalindustryanalysts.com", "euromonitor.com",
    "mintel.com", "statista.com",
}

ALLOWED_SOURCE_TYPES = {
    "sec_filing",
    "fda_database",
    "ema_database",
    "annual_report",
    "investor_presentation",
    "news_article",            # Reuters, Bloomberg, FT, WSJ, CNBC
    "journal",                 # Peer-reviewed: NEJM, Lancet, Nature, JAMA
    "gov_database",            # WHO, NIH, CDC, CMS, EMA, FDA
    "press_release",           # Company press releases
    "clinical_trial",          # clinicaltrials.gov
    "patent_filing",
    "industry_association",    # ASCO, AACR, ISSCR, etc.
    "company_website",
}


def _is_banned_domain(url: str) -> bool:
    """Fast domain-level check against banned URL patterns."""
    url_lower = url.lower()
    for domain in BANNED_DOMAINS:
        if domain in url_lower:
            return True
    return False


def is_banned_source(url: str, title: str = "", publisher: str = "") -> bool:
    """Check if a source is from a banned research firm.

    Returns True if the source should be BLOCKED.
    """
    # Fast domain check first
    if _is_banned_domain(url):
        return True

    # Text-level check on combined metadata
    combined = f"{url} {title} {publisher}".lower()
    for banned in BANNED_SOURCES:
        if banned in combined:
            return True
    return False


def validate_citation(url: str, title: str = "", publisher: str = "") -> bool:
    """Returns True if the citation is acceptable (not from a banned source)."""
    return not is_banned_source(url, title, publisher)


def generate_citation_id(subsection_id: str, index: int) -> str:
    """Generate a deterministic citation ID."""
    prefix = subsection_id[:3]
    return f"src_{prefix}_{index:03d}"


def check_text_for_banned_citations(text: str) -> list[str]:
    """Scan written text for any mentions of banned research firms.

    Returns list of found banned firm names.
    """
    text_lower = text.lower()
    # Also check a version with spaces removed for URLs
    text_nospace = text_lower.replace(" ", "")
    found = set()
    for banned in BANNED_SOURCES:
        if banned in text_lower or banned in text_nospace:
            # Normalize to the spaced version for dedup
            normalized = banned if " " in banned else banned
            found.add(normalized)
    return list(found)
