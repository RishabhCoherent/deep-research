"""
Layer 1 — Research Agent (Agentic): Plan → Research → Draft → Self-Evaluate → Refine.

Mimics what a junior research analyst does:
1. Plan: Break topic into sub-areas, generate targeted queries
2. Research: Execute searches, scrape top sources, evaluate coverage
3. Draft: Synthesize into a source-grounded analysis
4. Self-Review: Score quality, identify weaknesses
5. Refine: Do targeted research and improve the draft (up to 2 more iterations)

What it adds over Layer 0:
- Real, current data from the web (not just LLM knowledge)
- Structured research planning with coverage evaluation
- Iterative self-improvement loop
- Source attribution for major claims
"""

from __future__ import annotations

import datetime
import logging
import time

from config import get_llm
from tools.search import search
from tools.scraper import scrape_url
from tools.source_classifier import get_source_tier
from research_agent.types import ResearchResult, Source
from research_agent.prompts import (
    LAYER1_SYSTEM, LAYER1_USER,
    LAYER1_PLAN, LAYER1_COVERAGE_EVAL, LAYER1_SELF_REVIEW, LAYER1_REFINE,
)
from research_agent.utils import extract_json
from research_agent.cost import track
from research_agent.agent_loop import run_agent_loop, EvalResult

logger = logging.getLogger(__name__)


# ─── Existing helpers (unchanged) ────────────────────────────────────────────


async def _search_and_gather(queries: list[str], scrape_top: int = 3) -> list[Source]:
    """Execute searches and gather results with optional scraping."""
    all_sources: list[Source] = []
    urls_seen: set[str] = set()

    for query in queries:
        try:
            results = await search(query, max_results=5, include_news=True)
        except Exception as e:
            logger.warning(f"[Layer 1] Search failed for '{query}': {e}")
            continue

        for r in results:
            url = r.get("url", "")
            if not url or url in urls_seen:
                continue
            urls_seen.add(url)

            all_sources.append(Source(
                url=url,
                title=r.get("title", ""),
                snippet=r.get("snippet", ""),
                publisher=_infer_publisher(url),
                date=r.get("date", ""),
            ))

    # Assign credibility tier to each source
    for source in all_sources:
        source.tier = get_source_tier(source.url)

    # Sort scrape candidates by tier (tier 1 first) so we scrape the best sources
    scrape_candidates = sorted(all_sources, key=lambda s: s.tier)[:scrape_top * 3]
    scraped_count = 0
    for source in scrape_candidates:
        if scraped_count >= scrape_top:
            break
        try:
            page = await scrape_url(source.url)
            if page and page.get("content"):
                source.scraped_content = page["content"][:5000]
                scraped_count += 1
        except Exception as e:
            logger.debug(f"[Layer 1] Scrape failed for {source.url}: {e}")

    tier_counts = {1: 0, 2: 0, 3: 0}
    for s in all_sources:
        tier_counts[s.tier] = tier_counts.get(s.tier, 0) + 1
    logger.info(f"[Layer 1] Source tiers: T1={tier_counts[1]}, T2={tier_counts[2]}, T3={tier_counts[3]}")

    return all_sources


def _build_context(sources: list[Source], max_chars: int = 12000) -> str:
    """Format sources into a context string for the LLM."""
    sorted_sources = sorted(sources, key=lambda s: (getattr(s, 'tier', 3), 0 if s.scraped_content else 1))

    parts = []
    total = 0

    for s in sorted_sources:
        content = s.scraped_content[:2000] if s.scraped_content else s.snippet
        if not content:
            continue

        tier = getattr(s, 'tier', 3)
        tier_label = {1: "TIER-1 HIGH-CREDIBILITY", 2: "TIER-2 RELIABLE", 3: "TIER-3 UNVERIFIED"}[tier]
        entry = f"[{tier_label}] Source: {s.title} ({s.publisher})\n{content}\n"
        if total + len(entry) > max_chars:
            break
        parts.append(entry)
        total += len(entry)

    return "\n---\n".join(parts)


def _infer_publisher(url: str) -> str:
    """Extract publisher name from URL domain."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        host = host.replace("www.", "")
        return host.split(".")[0].capitalize() if host else "Unknown"
    except Exception:
        return "Unknown"


# ─── Agent loop callbacks ────────────────────────────────────────────────────

# Store plan state across iterations (set in _l1_plan, read in _l1_evaluate)
_plan_sub_areas: list[str] = []


async def _l1_plan(topic: str, context: str) -> dict:
    """Plan research sub-areas and generate queries for each."""
    current_year = datetime.datetime.now().year
    llm = get_llm("planner")

    messages = [
        {"role": "system", "content": "You are a market research planner. Return valid JSON only."},
        {"role": "user", "content": LAYER1_PLAN.format(topic=topic, current_year=current_year)},
    ]

    try:
        response = llm.invoke(messages)
        track("L1 plan", response)
        plan = extract_json(response.content.strip())
        if isinstance(plan, dict) and "sub_areas" in plan:
            queries = []
            sub_area_names = []
            for sa in plan["sub_areas"]:
                sub_area_names.append(sa.get("name", ""))
                for q in sa.get("queries", []):
                    queries.append(q)
            _plan_sub_areas.clear()
            _plan_sub_areas.extend(sub_area_names)
            logger.info(f"[Layer 1] Plan: {len(sub_area_names)} sub-areas, {len(queries)} queries")
            return {"queries": queries, "sub_areas": sub_area_names}
    except Exception as e:
        logger.warning(f"[Layer 1] Planning failed: {e}")

    # Fallback
    _plan_sub_areas.clear()
    return {"queries": [
        f"{topic} market size growth forecast {current_year}",
        f"{topic} key trends developments {current_year}",
        f"{topic} major companies competitive landscape",
        f"{topic} challenges risks constraints",
        f"{topic} technology innovation outlook {current_year}",
    ], "sub_areas": []}


async def _l1_research(queries: list[str], existing_sources: list[Source]) -> tuple[list[Source], str]:
    """Execute searches, gather sources, build context."""
    existing_urls = {s.url for s in existing_sources}

    new_sources = await _search_and_gather(queries, scrape_top=5)
    # Deduplicate against existing
    truly_new = [s for s in new_sources if s.url not in existing_urls]

    all_for_context = existing_sources + truly_new
    context = _build_context(all_for_context)
    logger.info(f"[Layer 1] Research: {len(truly_new)} new sources")
    return truly_new, context


async def _l1_draft(topic: str, context: str, previous_draft: str) -> str:
    """Write or refine the research report."""
    llm = get_llm("writer")

    if not previous_draft:
        # First draft — use existing synthesis prompt
        messages = [
            {"role": "system", "content": LAYER1_SYSTEM},
            {"role": "user", "content": LAYER1_USER.format(
                topic=topic,
                research_context=context if context else "No research data available.",
            )},
        ]
    else:
        # Refinement — use refine prompt (weaknesses are embedded in context by the loop)
        messages = [
            {"role": "system", "content": LAYER1_SYSTEM},
            {"role": "user", "content": LAYER1_REFINE.format(
                topic=topic,
                draft=previous_draft,
                weaknesses="See the additional research data for areas that need improvement.",
                new_context=context,
            )},
        ]

    try:
        response = llm.invoke(messages)
        track("L1 draft" if not previous_draft else "L1 refine", response)
        return response.content.strip()
    except Exception as e:
        logger.error(f"[Layer 1] Draft failed: {e}")
        return previous_draft or f"Error: {e}"


async def _l1_evaluate(draft: str, topic: str) -> EvalResult:
    """Self-review the draft and identify weaknesses."""
    llm = get_llm("reviewer")

    messages = [
        {"role": "system", "content": "You are a harsh but fair research editor. Return valid JSON only."},
        {"role": "user", "content": LAYER1_SELF_REVIEW.format(topic=topic, draft=draft)},
    ]

    try:
        response = llm.invoke(messages)
        track("L1 self-review", response)
        result = extract_json(response.content.strip())

        if isinstance(result, dict):
            return EvalResult(
                overall_score=float(result.get("overall", 5.0)),
                dimension_scores=result.get("scores", {}),
                weaknesses=result.get("weaknesses", []),
                suggested_queries=result.get("suggested_queries", []),
            )
    except Exception as e:
        logger.warning(f"[Layer 1] Self-review failed: {e}")

    # Fallback: assume mediocre score to force one more iteration
    return EvalResult(overall_score=5.0, weaknesses=["Self-review failed"], suggested_queries=[])


# ─── Main entry point ────────────────────────────────────────────────────────


async def run(topic: str, progress_callback=None) -> ResearchResult:
    """Run Layer 1: agentic web research with planning and self-evaluation."""
    logger.info(f"[Layer 1] Agentic research agent starting for: {topic}")
    start = time.time()

    draft, sources, iterations = await run_agent_loop(
        topic=topic,
        layer=1,
        plan_fn=_l1_plan,
        research_fn=_l1_research,
        draft_fn=_l1_draft,
        evaluate_fn=_l1_evaluate,
        max_iterations=3,
        convergence_threshold=7.0,
        progress_callback=progress_callback,
    )

    elapsed = time.time() - start
    final_score = iterations[-1].eval_score if iterations else 0
    logger.info(f"[Layer 1] Done in {elapsed:.1f}s — {len(draft.split())} words, "
                f"{len(sources)} sources, {len(iterations)} iterations, "
                f"final score: {final_score:.1f}/10")

    return ResearchResult(
        layer=1,
        topic=topic,
        content=draft,
        sources=sources,
        metadata={
            "method": "agentic_research",
            "iterations": len(iterations),
            "final_score": final_score,
            "iteration_history": [
                {"iteration": it.iteration, "score": it.eval_score,
                 "weaknesses": it.weaknesses}
                for it in iterations
            ],
            "sources_found": len(sources),
            "sources_scraped": sum(1 for s in sources if s.scraped_content),
        },
        elapsed_seconds=elapsed,
    )
