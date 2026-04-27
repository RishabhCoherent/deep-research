"""Open-access fallback for paywalled fetches.

When `hybrid_scrape` returns a 403 / paywall stub for a URL, this module tries
to find an OA mirror of the same content:

  1. PubMed URL  -> resolve to PMC ID -> fetch PMC OA full text
  2. DOI URL     -> unpaywall.org API -> OA URL -> re-fetch
  3. Preprint candidates (medRxiv / bioRxiv / arXiv / SSRN / OSF) pass through
     unchanged (already OA, no fallback needed)

If no fallback yields substantive text, returns the original (failed) result
so the caller can drop the URL.

Public:
  open_access_fetch(url, primary_result, hybrid_scrape_fn) -> dict

Cost: zero LLM calls. unpaywall + PMC/PubMed E-utilities are free public APIs.
Wall time: typically +2-6s per fallback attempt (parallel-safe).
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Awaitable, Callable
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


# Heuristic: a "paywall stub" is a successful fetch (status 200) that returns
# very little text AND contains paywall-tell words. Distinct from hard 403s.
_PAYWALL_TELLS = (
    "subscribe", "subscription", "purchase", "buy this article",
    "log in to view", "access denied", "for full access",
    "register to read", "members only", "create an account",
    "free trial", "$"  # last is weak; bounded by length check below
)
_PAYWALL_STUB_MAX_CHARS = 800
_PAYWALL_TIMEOUT = 8.0   # per HTTP call inside the fallback chain


def _looks_paywalled(scrape_result: dict) -> bool:
    """Heuristic: did `hybrid_scrape` return a paywall block instead of content?"""
    if not scrape_result:
        return True
    if not scrape_result.get("success"):
        return True
    text = (scrape_result.get("content") or "").lower()
    if not text:
        return True
    if len(text) >= _PAYWALL_STUB_MAX_CHARS:
        return False   # substantial body — likely real content
    return any(tell in text for tell in _PAYWALL_TELLS)


# ── PubMed → PMC OA fallback ──────────────────────────────────────────────

_PUBMED_RE = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/?", re.I)
_NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


async def _pubmed_to_pmc_url(url: str, client: httpx.AsyncClient) -> str | None:
    """Given a PubMed URL `pubmed.ncbi.nlm.nih.gov/{pmid}/`, query NCBI's
    elink API to find the PMC (free full text) ID, and return the canonical
    PMC URL. Returns None if no PMC mirror exists for this PMID.
    """
    m = _PUBMED_RE.search(url)
    if not m:
        return None
    pmid = m.group(1)
    try:
        # elink: pubmed -> pmc maps a PubMed ID to its PMC ID (if any)
        r = await client.get(
            f"{_NCBI_BASE}/elink.fcgi",
            params={"dbfrom": "pubmed", "db": "pmc", "id": pmid, "retmode": "json"},
            timeout=_PAYWALL_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        # elink response has linksets[].linksetdbs[].links[]
        linksets = data.get("linksets") or []
        for ls in linksets:
            for db in ls.get("linksetdbs") or []:
                if db.get("dbto") != "pmc":
                    continue
                links = db.get("links") or []
                if links:
                    pmc_id = str(links[0])
                    return f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/"
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.debug(f"[open_access] pubmed->pmc lookup failed for {pmid}: {exc}")
    return None


# ── DOI → unpaywall fallback ─────────────────────────────────────────────

_DOI_RE = re.compile(
    r"(?:doi\.org/|/doi/)(10\.\d{4,9}/[^\s/?#]+)", re.I
)
_UNPAYWALL_BASE = "https://api.unpaywall.org/v2"
_UNPAYWALL_EMAIL = "research@example.com"   # required by unpaywall TOS;
                                             # any valid-looking email works


async def _doi_to_oa_url(url: str, client: httpx.AsyncClient) -> str | None:
    """Given a URL containing a DOI, query unpaywall.org for the best OA
    location. Returns None if no OA version exists.
    """
    m = _DOI_RE.search(url)
    if not m:
        return None
    doi = m.group(1).rstrip(".,);")
    try:
        r = await client.get(
            f"{_UNPAYWALL_BASE}/{doi}",
            params={"email": _UNPAYWALL_EMAIL},
            timeout=_PAYWALL_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        best = data.get("best_oa_location") or {}
        # Prefer the HTML / landing-page URL if available, else PDF
        for key in ("url_for_landing_page", "url", "url_for_pdf"):
            candidate = best.get(key)
            if candidate:
                return candidate
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.debug(f"[open_access] unpaywall lookup failed for {doi}: {exc}")
    return None


# ── Preprint passthrough ─────────────────────────────────────────────────

_PREPRINT_HOSTS = (
    "medrxiv.org", "biorxiv.org", "arxiv.org", "ssrn.com", "osf.io",
    "psyarxiv.com", "engrxiv.org", "chemrxiv.org",
)


def _is_preprint_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return any(host.endswith(p) for p in _PREPRINT_HOSTS)


# ── Public entry ─────────────────────────────────────────────────────────

ScrapeFn = Callable[[str], Awaitable[dict]]


async def open_access_fetch(
    url: str,
    primary_result: dict,
    hybrid_scrape_fn: ScrapeFn,
) -> dict:
    """If `primary_result` looks paywalled, try OA mirrors and re-fetch.

    Returns the BETTER of (primary_result, fallback_result). "Better" =
    longer substantive content. If no fallback yields anything, returns the
    original primary_result so the caller can drop normally.
    """
    if not _looks_paywalled(primary_result):
        return primary_result
    if _is_preprint_url(url):
        # Already OA — primary fetch's failure is the real failure. No fallback.
        return primary_result

    async with httpx.AsyncClient(follow_redirects=True) as client:
        candidates: list[str] = []

        # PubMed -> PMC
        pmc_url = await _pubmed_to_pmc_url(url, client)
        if pmc_url:
            candidates.append(pmc_url)

        # DOI -> unpaywall
        doi_url = await _doi_to_oa_url(url, client)
        if doi_url and doi_url not in candidates:
            candidates.append(doi_url)

    if not candidates:
        return primary_result

    primary_text = (primary_result.get("content") or "")
    best_result = primary_result
    best_len = len(primary_text)

    for candidate_url in candidates:
        try:
            r = await hybrid_scrape_fn(candidate_url)
        except Exception as exc:
            logger.debug(f"[open_access] fallback fetch failed: {candidate_url} -> {exc}")
            continue
        if not r or not r.get("success"):
            continue
        text_len = len(r.get("content") or "")
        if text_len > best_len + 200:   # require meaningful improvement
            best_result = r
            best_len = text_len
            # Stamp on the result that we used a fallback (audit signal)
            best_result["method"] = (best_result.get("method", "") or "") + "+oa_fallback"
            logger.info(f"[open_access] OA fallback yielded {text_len} chars "
                        f"from {candidate_url[:80]}")
            break   # first improvement is enough

    return best_result
