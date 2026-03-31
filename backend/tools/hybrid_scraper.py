"""
Tools for the Analyst Agent.

Two categories:
1. DATA GATHERING — search, scrape (with hybrid fallback chain), assess source
2. ANALYST THINKING — formulate hypothesis, evaluate evidence, resolve contradiction,
   mark gap, form judgment, check progress

All tools operate on a shared ResearchBoard via closures.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from langchain_core.tools import tool

from models.analyst import (
    AnalystEvidence, Contradiction, AnalystJudgment, Hypothesis, ResearchBoard,
)
from models.pipeline import Source
from tools.search import search
from tools.source_classifier import get_source_tier
from tools.citation import is_banned_source

logger = logging.getLogger(__name__)

_scrape_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="scrape_")


# ═══════════════════════════════════════════════════════════════════════════════
# HYBRID SCRAPER — Tavily Extract → Trafilatura → aiohttp+BS4 → snippet fallback
# ═══════════════════════════════════════════════════════════════════════════════

# File extensions that can't be scraped as HTML
_BINARY_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".gz", ".tar", ".7z", ".exe", ".bin",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".mp4", ".mp3", ".wav",
}


async def hybrid_scrape(url: str) -> dict:
    """Scrape a URL using a multi-method fallback chain.

    Returns: {"url", "title", "content", "method", "success"}
    """
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in _BINARY_EXTENSIONS):
        return {"url": url, "title": "", "content": "", "method": "skipped_binary", "success": False}

    # Method 1: Trafilatura (best article extraction, fast)
    result = await _scrape_trafilatura(url)
    if result["success"]:
        return result

    # Method 2: aiohttp + BeautifulSoup (simple HTML)
    result = await _scrape_aiohttp(url)
    if result["success"]:
        return result

    # Method 3: Failed — return empty
    logger.warning(f"[Scraper] All methods failed for {url}")
    return {"url": url, "title": "", "content": "", "method": "all_failed", "success": False}


async def _scrape_trafilatura(url: str) -> dict:
    """Use trafilatura for article extraction — best for news/research sites."""
    try:
        import trafilatura

        def _sync_extract():
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return None
            text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=True,
                favor_precision=True,
                deduplicate=True,
            )
            # Also get metadata for title
            metadata = trafilatura.extract_metadata(downloaded)
            title = metadata.title if metadata and metadata.title else ""
            return text, title

        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(_scrape_executor, _sync_extract),
            timeout=20.0,
        )

        if result and result[0] and len(result[0]) > 100:
            text, title = result
            logger.info(f"[Scraper] Trafilatura success: {url[:60]} ({len(text)} chars)")
            return {
                "url": url,
                "title": title,
                "content": text[:20000],
                "method": "trafilatura",
                "success": True,
            }

    except asyncio.TimeoutError:
        logger.debug(f"[Scraper] Trafilatura timeout: {url[:60]}")
    except Exception as e:
        logger.debug(f"[Scraper] Trafilatura failed for {url[:60]}: {e}")

    return {"url": url, "title": "", "content": "", "method": "trafilatura_failed", "success": False}


async def _scrape_aiohttp(url: str) -> dict:
    """Fallback: aiohttp + BeautifulSoup for simple HTML pages."""
    try:
        import aiohttp
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
                ssl=False,  # Skip SSL verification for more sites
            ) as resp:
                if resp.status != 200:
                    return {"url": url, "title": "", "content": "", "method": f"aiohttp_{resp.status}", "success": False}

                content_type = resp.headers.get("Content-Type", "")
                if content_type and "text/html" not in content_type and "text/plain" not in content_type:
                    return {"url": url, "title": "", "content": "", "method": "aiohttp_not_html", "success": False}

                html = await resp.text(errors="replace")

        soup = BeautifulSoup(html, "html.parser")
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            element.decompose()

        title = soup.title.string if soup.title else ""

        # Try article/main first, then fall back to all content
        content_tags = soup.find_all(["article", "main"])
        if not content_tags:
            content_tags = soup.find_all(["div", "section", "p"])

        text_parts = []
        for tag in content_tags:
            text = tag.get_text(strip=True)
            if len(text) > 50:
                text_parts.append(text)

        content = "\n\n".join(text_parts)[:20000]

        if len(content) > 100:
            logger.info(f"[Scraper] aiohttp+BS4 success: {url[:60]} ({len(content)} chars)")
            return {"url": url, "title": title or "", "content": content, "method": "aiohttp", "success": True}

    except Exception as e:
        logger.debug(f"[Scraper] aiohttp failed for {url[:60]}: {e}")

    return {"url": url, "title": "", "content": "", "method": "aiohttp_failed", "success": False}


def _infer_publisher(url: str) -> str:
    """Extract publisher name from URL domain."""
    try:
        domain = urlparse(url).netloc.lower()
        domain = re.sub(r'^www\.', '', domain)
        parts = domain.split('.')
        if len(parts) >= 2:
            return parts[-2].capitalize()
    except Exception:
        pass
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL FACTORY — Creates all tools with closures over shared ResearchBoard
# ═══════════════════════════════════════════════════════════════════════════════

def make_analyst_tools(board: ResearchBoard, sources: list[Source]) -> list:
    """Create all analyst tools with closures over shared state.

    Args:
        board: The central ResearchBoard (mutated by tools)
        sources: Shared source list (for pipeline integration)
    """

    urls_seen: set[str] = set()

    # ── DATA GATHERING ────────────────────────────────────────────────────

    @tool
    async def search_web(query: str) -> str:
        """Search the web for data, trends, and insights. Returns titles, URLs, and
        snippets. Write targeted queries with specific terms, company names, and years."""
        if board.tool_calls_used >= board.tool_calls_budget:
            return "BUDGET EXHAUSTED. Call check_progress() to see your status, then wrap up."
        board.tool_calls_used += 1
        board.searches_done += 1

        try:
            results = await search(query, max_results=6, include_news=True)
        except Exception as e:
            return f"Search failed: {e}. Try a different query."

        if not results:
            return "No results found. Try different terms."

        # Filter banned sources
        results = [
            r for r in results
            if not is_banned_source(r.get("url", ""), r.get("title", ""))
            and "wikipedia.org" not in r.get("url", "").lower()
        ]
        if not results:
            return "No usable results (filtered out competitor firms). Try different terms."

        parts = []
        for r in results:
            url = r.get("url", "")
            if not url:
                continue
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            tier = get_source_tier(url)
            tier_label = {1: "[T1 GOLD]", 2: "[T2 RELIABLE]", 3: "[T3]"}[tier]

            if url not in urls_seen:
                urls_seen.add(url)
                sources.append(Source(
                    url=url, title=title, snippet=snippet[:200],
                    publisher=_infer_publisher(url),
                    date=r.get("date", ""),
                    tier=tier,
                ))

            parts.append(f"{tier_label} {title}\n  URL: {url}\n  {snippet[:300]}")

        return "\n\n".join(parts)

    @tool
    async def scrape_page(url: str) -> str:
        """Scrape full text content from a web page. Use this to get detailed data
        beyond search snippets. Essential for extracting specific numbers and case studies."""
        if board.tool_calls_used >= board.tool_calls_budget:
            return "BUDGET EXHAUSTED."
        board.tool_calls_used += 1

        # Check if banned
        if is_banned_source(url, ""):
            return "This is a competitor research firm URL. Skip it."

        result = await hybrid_scrape(url)

        if result["success"]:
            board.scrapes_done += 1
            content = result["content"]

            # Update source with scraped content
            for s in sources:
                if s.url == url:
                    s.scraped_content = content[:8000]
                    break

            # Return content with source info
            tier = get_source_tier(url)
            tier_label = {1: "T1 GOLD", 2: "T2 RELIABLE", 3: "T3"}[tier]
            return (
                f"[{tier_label}] Scraped {len(content)} chars via {result['method']}\n"
                f"Title: {result.get('title', 'Unknown')}\n\n"
                f"{content[:8000]}"
            )
        else:
            board.scrapes_failed += 1
            return f"Scrape failed ({result['method']}). Try a different URL or use search snippets."

    # ── ANALYST THINKING TOOLS ────────────────────────────────────────────

    @tool
    def formulate_hypothesis(sub_question_id: str, hypothesis: str, reasoning: str) -> str:
        """Record what you EXPECT to find before researching a sub-question.
        This helps you evaluate whether search results actually answer the question."""
        sq = None
        for q in board.framework.sub_questions:
            if q.id == sub_question_id:
                sq = q
                break
        if not sq:
            return f"Sub-question {sub_question_id} not found."

        sq.hypothesis = hypothesis
        board.hypotheses.append(Hypothesis(
            sub_question_id=sub_question_id,
            hypothesis=hypothesis,
            reasoning=reasoning,
        ))
        sq.status = "researching"
        return f"Hypothesis recorded for {sub_question_id}. Now search to confirm or refute."

    @tool
    def evaluate_evidence(
        sub_question_id: str,
        finding: str,
        source_url: str,
        source_title: str,
        source_tier: int,
        contradicts_existing: bool = False,
    ) -> str:
        """Record and evaluate a research finding. Use this after every search/scrape
        to capture what you found. Set contradicts_existing=True if this conflicts
        with earlier findings for the same sub-question."""
        sq = None
        for q in board.framework.sub_questions:
            if q.id == sub_question_id:
                sq = q
                break
        if not sq:
            return f"Sub-question {sub_question_id} not found."

        ev = AnalystEvidence(
            sub_question_id=sub_question_id,
            fact=finding,
            source_url=source_url,
            source_title=source_title,
            source_tier=min(max(source_tier, 1), 3),
            evidence_type="confirmed" if source_tier <= 2 else "inferred",
            confidence=0.9 if source_tier == 1 else 0.7 if source_tier == 2 else 0.4,
        )
        board.evidence.append(ev)
        sq.evidence_ids.append(ev.id)

        # If this is the first solid evidence, mark as answered
        if sq.status in ("pending", "researching") and ev.confidence >= 0.6:
            sq.status = "answered"
            sq.confidence = ev.confidence
            sq.answer = finding[:500]

        # Handle contradiction
        if contradicts_existing:
            existing_ev = board.evidence_for(sub_question_id)
            if len(existing_ev) >= 2:
                prev = existing_ev[-2]  # The one before this new one
                ct = Contradiction(
                    evidence_a_id=prev.id,
                    evidence_b_id=ev.id,
                    sub_question_id=sub_question_id,
                    description=f"'{prev.fact[:80]}' vs '{finding[:80]}'",
                )
                board.contradictions.append(ct)
                sq.status = "conflicted"
                return (
                    f"Evidence recorded. CONTRADICTION DETECTED: {ct.description}\n"
                    f"Contradiction ID: {ct.id}. Resolve with resolve_contradiction()."
                )

        return (
            f"Evidence recorded: [{ev.id}] for {sub_question_id}. "
            f"Confidence: {ev.confidence:.0%}. "
            f"Sub-question status: {sq.status}. "
            f"Coverage: {board.coverage:.0%}"
        )

    @tool
    def resolve_contradiction(
        contradiction_id: str,
        resolution: str,
        preferred_evidence_id: str,
        reasoning: str,
    ) -> str:
        """Resolve a contradiction between two pieces of evidence. Explain WHY you
        prefer one source over the other (tier, recency, methodology, etc.)."""
        ct = None
        for c in board.contradictions:
            if c.id == contradiction_id:
                ct = c
                break
        if not ct:
            return f"Contradiction {contradiction_id} not found."

        ct.resolution = resolution
        ct.preferred_evidence_id = preferred_evidence_id
        ct.reasoning = reasoning
        ct.resolved = True

        # Update sub-question status back to answered
        for sq in board.framework.sub_questions:
            if sq.id == ct.sub_question_id and sq.status == "conflicted":
                pref_ev = board.evidence_by_id(preferred_evidence_id)
                if pref_ev:
                    sq.status = "answered"
                    sq.confidence = pref_ev.confidence
                    sq.answer = pref_ev.fact[:500]
                break

        return f"Contradiction resolved. Preferred: {preferred_evidence_id}. Reasoning: {reasoning[:100]}"

    @tool
    def mark_gap(sub_question_id: str, severity: str, why_it_matters: str) -> str:
        """Acknowledge that a sub-question cannot be answered with available evidence.
        This is BETTER than hallucinating data.
        severity: 'critical' (undermines argument), 'acceptable' (can work around), 'irrelevant'."""
        sq = None
        for q in board.framework.sub_questions:
            if q.id == sub_question_id:
                sq = q
                break
        if not sq:
            return f"Sub-question {sub_question_id} not found."

        sq.status = "gap"
        sq.answer = f"GAP ({severity}): {why_it_matters}"
        sq.confidence = 0.0
        return (
            f"Gap acknowledged for {sub_question_id} (severity: {severity}). "
            f"This will be flagged in the report rather than hallucinated. "
            f"Coverage: {board.coverage:.0%}"
        )

    @tool
    def form_judgment(
        claim: str,
        conviction: str,
        supporting_evidence_ids: str,
        counter_evidence_ids: str,
        reasoning: str,
    ) -> str:
        """Form an analyst opinion with evidence. Include BOTH supporting and
        counter-evidence for balanced assessment.
        conviction: 'high', 'medium', 'low'.
        evidence_ids: comma-separated evidence IDs."""
        supporting = [x.strip() for x in supporting_evidence_ids.split(",") if x.strip()]
        counter = [x.strip() for x in counter_evidence_ids.split(",") if x.strip()]

        j = AnalystJudgment(
            claim=claim,
            conviction=conviction,
            supporting_evidence=supporting,
            counter_evidence=counter,
            reasoning=reasoning,
        )
        board.judgments.append(j)
        return f"Judgment formed: '{claim}' (conviction: {conviction}). Total judgments: {len(board.judgments)}"

    @tool
    def check_progress() -> str:
        """Check your research progress — coverage, gaps, contradictions, budget.
        Call this after every 3-4 searches to decide whether to continue, pivot, or wrap up."""
        return board.progress_summary()

    return [
        search_web,
        scrape_page,
        formulate_hypothesis,
        evaluate_evidence,
        resolve_contradiction,
        mark_gap,
        form_judgment,
        check_progress,
    ]
