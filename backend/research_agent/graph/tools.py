"""
Tool factory for LangGraph research agents.

Creates search_web, scrape_page, assess_source, and (optionally) record_finding
tools with closures over a shared AgentContext.
"""

from __future__ import annotations

import logging
import re as _re

from langchain_core.tools import tool

from research_agent.models import Source, AgentContext, EvidenceLedger, ClaimMap
from research_agent.cost import track
from research_agent.utils import infer_publisher, format_tier
from tools.search import search
from tools.scraper import scrape_url
from tools.source_classifier import get_source_tier
from tools.citation import is_banned_source, check_text_for_banned_citations

logger = logging.getLogger(__name__)


# ─── Source-text validation ───────────────────────────────────────────────────


def _validate_finding_against_source(finding: str, source_text: str) -> bool:
    """Check that key entities and numbers in a finding appear in the source text.

    Uses keyword/number matching — not LLM. Returns True if the finding
    is reasonably grounded in the source, False if it appears to be inferred.

    Strategy: Split tokens into "specific" (proper nouns, large numbers, acronyms)
    and "generic" (years, small numbers). Require that at least 1 specific token
    matches AND overall ratio >= 50%. This prevents topic-keyword false positives.
    """
    if not source_text or len(source_text.strip()) < 50:
        return False

    source_lower = source_text.lower()

    specific_tokens = []  # Proper nouns, large numbers, acronyms — must match
    generic_tokens = []   # Years, small numbers — easy to match by coincidence

    # Extract numbers — classify as specific (>= 4 digits or decimal) or generic
    numbers = _re.findall(r'\d[\d,\.]*', finding)
    for n in numbers:
        clean = n.rstrip('.,')
        if not clean:
            continue
        # Years (2020-2030) are generic — they appear in any article on the same topic
        digits_only = clean.replace(',', '').replace('.', '')
        if _re.match(r'^20[12]\d$', digits_only):
            generic_tokens.append(clean)
        # Large numbers (4+ digits) or decimals are specific
        elif len(digits_only) >= 4 or '.' in clean:
            specific_tokens.append(clean)
        else:
            generic_tokens.append(clean)

    # Extract multi-word proper nouns (e.g., "Dixon Technologies", "Tamil Nadu")
    proper_nouns = _re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', finding)
    for pn in proper_nouns:
        specific_tokens.append(pn.lower())

    # Extract acronyms (e.g., "BMW", "SPECS", "PLI", "EU")
    acronyms = _re.findall(r'\b[A-Z]{2,}[a-z]*\b', finding)
    # Filter out very common acronyms that appear in any EV/geopolitics article
    _COMMON_ACRONYMS = {'EV', 'EVS', 'US', 'EU', 'UK', 'GDP', 'USD', 'CEO', 'AI'}
    for acr in acronyms:
        if acr in _COMMON_ACRONYMS:
            generic_tokens.append(acr.lower())
        else:
            specific_tokens.append(acr.lower())

    all_tokens = specific_tokens + generic_tokens

    if not all_tokens:
        return len(finding.split()) < 15

    # Word-boundary matching for numbers
    def _token_in_source(token: str, source: str) -> bool:
        if _re.match(r'^\d[\d,\.]*$', token):
            pattern = r'(?<!\d)' + _re.escape(token) + r'(?!\d)'
            return bool(_re.search(pattern, source))
        return token in source

    specific_matches = sum(1 for t in specific_tokens if _token_in_source(t, source_lower))
    generic_matches = sum(1 for t in generic_tokens if _token_in_source(t, source_lower))
    total_matches = specific_matches + generic_matches
    total_ratio = total_matches / len(all_tokens) if all_tokens else 0

    logger.info(
        f"[validate_finding] specific={specific_matches}/{len(specific_tokens)}, "
        f"generic={generic_matches}/{len(generic_tokens)}, "
        f"total={total_ratio:.0%}. "
        f"Specific: {specific_tokens[:6]}, Generic: {generic_tokens[:4]}"
    )

    # Must have at least 1 specific token match AND overall ratio >= 50%
    if specific_tokens and specific_matches == 0:
        return False
    return total_ratio >= 0.5


# ─── Tool factory ─────────────────────────────────────────────────────────────


def make_tools(ctx: AgentContext, ledger: EvidenceLedger | None = None, claim_map: ClaimMap | None = None) -> list:
    """Create LangChain tools with closures over shared AgentContext.

    Args:
        ctx: Shared agent context for source/tool tracking
        ledger: Optional evidence ledger for expert pipeline (enables record_finding tool)
        claim_map: Optional claim map for expert pipeline (enables coverage tracking)
    """

    @tool
    async def search_web(query: str) -> str:
        """Search the web for current data, trends, and insights. Returns titles,
        URLs, and snippets from top results. Use targeted queries with specific
        terms and the current year."""
        # ── Deduplication ─────────────────────────────────────────────
        normalized = query.lower().strip()
        if normalized in ctx.searched_queries:
            return "Already searched this exact query. Try a DIFFERENT query with new keywords."
        # Similarity check — reject if 80%+ word overlap with a previous query
        new_words = set(normalized.split())
        for prev in ctx.searched_queries:
            prev_words = set(prev.split())
            union = new_words | prev_words
            if union and len(new_words & prev_words) / len(union) >= 0.8:
                return "Too similar to a previous search. Use substantially different terms."
        ctx.searched_queries.add(normalized)

        if ctx.tool_call_count >= ctx.max_tool_calls:
            return (
                "BUDGET EXCEEDED. Write your final report now — start directly "
                "with ## headings. No preamble, no explanation."
            )
        ctx.tool_call_count += 1

        try:
            results = await search(query, max_results=5, include_news=True)
        except Exception as e:
            ctx.tool_calls_log.append({
                "tool": "search_web", "query": query, "results": 0, "hits": [],
            })
            return f"Search failed: {e}. Try a different query."

        if not results:
            ctx.tool_calls_log.append({
                "tool": "search_web", "query": query, "results": 0, "hits": [],
            })
            return "No results found. Try a different query."

        # Filter out competitor market research firms and Wikipedia
        results = [
            r for r in results
            if not is_banned_source(r.get("url", ""), r.get("title", ""))
            and "wikipedia.org" not in r.get("url", "").lower()
        ]
        if not results:
            ctx.tool_calls_log.append({
                "tool": "search_web", "query": query, "results": 0, "hits": [],
            })
            return "No usable results (all from competitor research firms). Try a different query."

        parts = []
        new_count = 0
        for r in results:
            url = r.get("url", "")
            if not url:
                continue
            title = r.get("title", "")
            snippet = r.get("snippet", "")

            if url not in ctx.urls_seen:
                ctx.urls_seen.add(url)
                ctx.sources.append(Source(
                    url=url, title=title, snippet=snippet,
                    publisher=infer_publisher(url),
                    date=r.get("date", ""),
                    tier=get_source_tier(url),
                ))
                new_count += 1

            tier = get_source_tier(url)
            tier_label = format_tier(tier, short=True)
            parts.append(f"[{tier_label}] {title}\n  {snippet[:200]}")

        hit_data = [
            {"title": r.get("title", ""), "snippet": r.get("snippet", "")[:200],
             "url": r.get("url", "")}
            for r in results if r.get("url")
        ][:3]
        ctx.tool_calls_log.append({
            "tool": "search_web", "query": query,
            "results": len(results), "hits": hit_data,
        })

        # Auto-record search snippets as evidence (if ledger available).
        # This ensures evidence accumulates even if the agent forgets to call record_finding.
        if ledger is not None:
            from research_agent.models import Evidence
            for r in results:
                snippet = r.get("snippet", "").strip()
                url = r.get("url", "")
                title = r.get("title", "")
                # Only record snippets with substantial content (>80 chars)
                if len(snippet) > 80:
                    # Infer section from query — the plan prompt names sections in queries
                    section = query  # Will be matched fuzzy in compose
                    ledger.add(Evidence(
                        claim_id=section,
                        fact=snippet[:500],
                        source_url=url,
                        source_title=title,
                        source_tier=get_source_tier(url),
                        evidence_type="confirms",
                        confidence="medium",
                        raw_snippet=snippet[:300],
                    ))

        return f"{len(results)} results ({new_count} new):\n\n" + "\n\n".join(parts)

    @tool
    async def scrape_page(url: str) -> str:
        """Scrape full text content from a web page. Use on the most promising
        search results to get detailed data, statistics, or analysis."""
        if ctx.tool_call_count >= ctx.max_tool_calls:
            return "BUDGET EXCEEDED. Write your final report now."

        # Block scraping competitor research firm pages and Wikipedia
        if is_banned_source(url):
            return "BLOCKED: This is a competitor market research firm. Do not use this source. Try a different URL."
        if "wikipedia.org" in url.lower():
            return "BLOCKED: Wikipedia is not a credible source for market research. Use news outlets, company filings, or industry publications instead."

        ctx.tool_call_count += 1

        try:
            page = await scrape_url(url)
        except Exception as e:
            return f"Scrape failed: {e}"

        if not page or not page.get("content"):
            return "Could not extract content (paywall or JS required)."

        content = page["content"][:6000]

        # Update existing source or create new one
        for s in ctx.sources:
            if s.url == url:
                s.scraped_content = page["content"][:8000]
                break
        else:
            if url not in ctx.urls_seen:
                ctx.urls_seen.add(url)
                ctx.sources.append(Source(
                    url=url, title=page.get("title", ""),
                    snippet=content[:200],
                    scraped_content=page["content"][:8000],
                    publisher=infer_publisher(url),
                    tier=get_source_tier(url),
                ))

        ctx.tool_calls_log.append({"tool": "scrape_page", "url": url})
        tier_label = format_tier(get_source_tier(url), short=True)
        return (
            f"[{tier_label}] Content from {infer_publisher(url)} "
            f"({len(content)} chars):\n\n{content}"
        )

    @tool
    async def assess_source(url: str) -> str:
        """Check credibility tier of a source URL. Returns T1 (gold-standard),
        T2 (reliable), or T3 (unverified)."""
        tier = get_source_tier(url)
        labels = {
            1: "TIER-1 HIGH-CREDIBILITY. Prefer this data when numbers conflict.",
            2: "TIER-2 RELIABLE. Generally trustworthy.",
            3: "TIER-3 UNVERIFIED. Cross-check against T1/T2 sources.",
        }
        return f"{infer_publisher(url)}: {labels[tier]}"

    tools_list = [search_web, scrape_page, assess_source]

    # Add record_finding tool for expert pipeline (evidence tracking)
    if ledger is not None:
        from research_agent.models import Evidence

        @tool
        async def record_finding(section: str, finding: str, evidence_type: str, confidence: str) -> str:
            """Record a research finding for a report section. Call this after every
            useful data point you find from search or scrape.

            Args:
                section: Which report section this supports (e.g., "Market Overview")
                finding: What you found — specific data, numbers, facts
                evidence_type: "confirms", "contradicts", "extends", or "quantifies"
                confidence: "high", "medium", or "low"
            """
            # Get source info from most recent scrape/search
            source_url = ""
            source_title = ""
            source_tier = 3
            source_text = ""
            for tc in reversed(ctx.tool_calls_log):
                if tc.get("tool") == "scrape_page":
                    source_url = tc.get("url", "")
                    for s in ctx.sources:
                        if s.url == source_url:
                            source_title = s.title
                            source_tier = s.tier
                            source_text = s.scraped_content or s.snippet or ""
                            break
                    break
                elif tc.get("tool") == "search_web":
                    hits = tc.get("hits", [])
                    if hits:
                        source_url = hits[0].get("url", "")
                        source_title = hits[0].get("title", "")
                        source_text = hits[0].get("snippet", "")
                    break

            # Source-text validation — only strict for scraped pages (long text).
            # Search snippets are too short for reliable token matching.
            if len(source_text) > 500:
                validated = _validate_finding_against_source(finding, source_text)
                if not validated:
                    logger.info(
                        f"[record_finding] Finding not fully grounded in scraped text. "
                        f"section={section}, confidence='medium', type='inferred'. "
                        f"Finding: {finding[:100]}..."
                    )
                    confidence = "medium"
                    evidence_type = "inferred"

            evidence = Evidence(
                claim_id=section,  # Use section name as the grouping key
                fact=finding,
                source_url=source_url,
                source_title=source_title,
                source_tier=source_tier,
                evidence_type=evidence_type,
                confidence=confidence,
            )
            ledger.add(evidence)

            # NOTE: record_finding does NOT increment tool_call_count — it's bookkeeping
            total_findings = len(ledger.entries)
            sections_with_evidence = len({e.claim_id for e in ledger.entries})

            ctx.tool_calls_log.append({
                "tool": "record_finding",
                "section": section,
                "evidence_type": evidence_type,
            })

            return (
                f"Recorded. Total findings: {total_findings}. "
                f"Sections with evidence: {sections_with_evidence}."
            )

        tools_list.append(record_finding)

    return tools_list
