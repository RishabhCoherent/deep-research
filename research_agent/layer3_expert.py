"""
Layer 3 — Expert Agent (Agentic): Critique → Research → Synthesize → C-Suite Review → Refine.

Mimics what a 25-year veteran strategic advisor does:
1. Expert Critique: Reads Layer 2 with extreme skepticism — finds hidden assumptions,
   second-order effects, cross-industry parallels, and blind spots
2. Assumption Research: Executes targeted searches for contrarian evidence and historical parallels
3. Expert Synthesis: Writes strategic-grade analysis with assumption audits
4. C-Suite Review: Scores against "would a Fortune 500 CEO approve this?" bar
5. Refine: Addresses CEO feedback with substance (up to 2 more iterations)

What it adds over Layer 2:
- Assumption auditing (what's being taken for granted, with validity ratings)
- Second-order effects (cascading impacts most analysts miss)
- Cross-industry parallels (pattern recognition from decades of experience)
- Contrarian view (bear cases backed by evidence, not strawmen)
- Signal identification (what to watch, what to ignore)
- C-Suite quality gate (decision-ready strategic analysis)
- Iterative self-improvement loop
"""

from __future__ import annotations

import json
import logging
import time

from config import get_llm
from tools.search import search
from tools.scraper import scrape_url
from tools.source_classifier import get_source_tier
from research_agent.types import ResearchResult, Source
from research_agent.prompts import (
    LAYER3_SYSTEM, LAYER3_USER,
    LAYER3_EXPERT_CRITIQUE, LAYER3_CSUITE_REVIEW, LAYER3_REFINE,
)
from research_agent.utils import extract_json
from research_agent.cost import track
from research_agent.agent_loop import run_agent_loop, EvalResult

logger = logging.getLogger(__name__)


# ─── Existing helpers (unchanged) ────────────────────────────────────────────


def _infer_publisher(url: str) -> str:
    """Extract publisher name from URL domain."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        host = host.replace("www.", "")
        return host.split(".")[0].capitalize() if host else "Unknown"
    except Exception:
        return "Unknown"


async def _search_and_gather(queries: list[str], scrape_top: int = 5) -> list[Source]:
    """Execute searches and gather results with optional scraping."""
    all_sources: list[Source] = []
    urls_seen: set[str] = set()

    for query in queries:
        try:
            results = await search(query, max_results=4, include_news=True)
        except Exception as e:
            logger.warning(f"[Layer 3] Search failed for '{query}': {e}")
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
                tier=get_source_tier(url),
            ))

    # Scrape top sources by tier
    scrape_candidates = sorted(all_sources, key=lambda s: s.tier)[:scrape_top * 3]
    scraped_count = 0
    for source in scrape_candidates:
        if scraped_count >= scrape_top:
            break
        try:
            page = await scrape_url(source.url)
            if page and page.get("content"):
                source.scraped_content = page["content"][:4000]
                scraped_count += 1
        except Exception:
            pass

    return all_sources


def _build_context(sources: list[Source], max_chars: int = 8000) -> str:
    """Build context string from sources, sorted by credibility tier."""
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

    return "\n---\n".join(parts) if parts else "No additional research data."


# ─── State shared across agent loop iterations ───────────────────────────────

_l3_layer2_content: str = ""
_l3_expert_critique: dict = {}


# ─── Agent loop callbacks ────────────────────────────────────────────────────


async def _l3_plan(topic: str, context: str) -> dict:
    """Expert critique of Layer 2, generating research queries for each finding."""
    llm = get_llm("planner")  # Best model for expert-level critique

    messages = [
        {"role": "system", "content": "You are a 25-year industry veteran. Return valid JSON only."},
        {"role": "user", "content": LAYER3_EXPERT_CRITIQUE.format(
            topic=topic,
            layer2_content=_l3_layer2_content[:5000],
        )},
    ]

    queries = []
    try:
        response = llm.invoke(messages)
        track("L3 expert critique", response)
        critique = extract_json(response.content.strip())

        if isinstance(critique, dict):
            _l3_expert_critique.clear()
            _l3_expert_critique.update(critique)

            # Extract queries from all critique categories
            for assumption in critique.get("assumptions", []):
                q = assumption.get("query", "")
                if q:
                    queries.append(q)

            for effect in critique.get("second_order_effects", []):
                q = effect.get("query", "")
                if q:
                    queries.append(q)

            for parallel in critique.get("cross_industry_parallels", []):
                q = parallel.get("query", "")
                if q:
                    queries.append(q)

            blind_spot = critique.get("biggest_blind_spot", {})
            if isinstance(blind_spot, dict) and blind_spot.get("query"):
                queries.append(blind_spot["query"])

            assumption_count = len(critique.get("assumptions", []))
            logger.info(f"[Layer 3] Expert critique: {assumption_count} assumptions, "
                        f"{len(queries)} research queries")
    except Exception as e:
        logger.warning(f"[Layer 3] Expert critique failed: {e}")
        _l3_expert_critique.clear()

    if not queries:
        # Fallback queries
        queries = [
            f"{topic} risks challenges failure criticism",
            f"{topic} disruptive technology threat alternative",
            f"{topic} hidden assumptions industry blind spots",
            f"{topic} historical parallels similar market",
        ]

    return {"queries": queries}


async def _l3_research(queries: list[str], existing_sources: list[Source]) -> tuple[list[Source], str]:
    """Execute searches focused on contrarian evidence and cross-industry parallels."""
    existing_urls = {s.url for s in existing_sources}

    new_sources = await _search_and_gather(queries, scrape_top=5)
    truly_new = [s for s in new_sources if s.url not in existing_urls]

    all_for_context = existing_sources + truly_new
    context = _build_context(all_for_context)
    logger.info(f"[Layer 3] Research: {len(truly_new)} new sources")

    return truly_new, context


async def _l3_draft(topic: str, context: str, previous_draft: str) -> str:
    """Write or refine the expert strategic report."""
    llm = get_llm("writer")  # Creative expert voice

    if not previous_draft:
        # First draft — use existing expert synthesis prompt
        messages = [
            {"role": "system", "content": LAYER3_SYSTEM},
            {"role": "user", "content": LAYER3_USER.format(
                topic=topic,
                layer2_content=_l3_layer2_content,
                expert_research=context if context else "No expert research data available.",
            )},
        ]
    else:
        # Refinement — use refine prompt with CEO feedback
        messages = [
            {"role": "system", "content": LAYER3_SYSTEM},
            {"role": "user", "content": LAYER3_REFINE.format(
                topic=topic,
                draft=previous_draft,
                weaknesses="See the additional research data for areas that need improvement.",
                new_context=context,
                layer2_content=_l3_layer2_content[:3000],
            )},
        ]

    try:
        response = llm.invoke(messages)
        track("L3 draft" if not previous_draft else "L3 refine", response)
        return response.content.strip()
    except Exception as e:
        logger.error(f"[Layer 3] Draft failed: {e}")
        return previous_draft or f"Error: {e}"


async def _l3_evaluate(draft: str, topic: str) -> EvalResult:
    """C-Suite review — would a Fortune 500 CEO approve this report?"""
    llm = get_llm("reviewer")

    messages = [
        {"role": "system", "content": "You are a demanding Fortune 500 CEO. Return valid JSON only."},
        {"role": "user", "content": LAYER3_CSUITE_REVIEW.format(topic=topic, draft=draft)},
    ]

    try:
        response = llm.invoke(messages)
        track("L3 C-suite review", response)
        result = extract_json(response.content.strip())

        if isinstance(result, dict):
            return EvalResult(
                overall_score=float(result.get("overall", 5.0)),
                dimension_scores=result.get("scores", {}),
                weaknesses=result.get("weaknesses", []),
                suggested_queries=result.get("suggested_queries", []),
            )
    except Exception as e:
        logger.warning(f"[Layer 3] C-suite review failed: {e}")

    return EvalResult(overall_score=5.0, weaknesses=["C-suite review failed"], suggested_queries=[])


# ─── Main entry point ────────────────────────────────────────────────────────


async def run(topic: str, layer2_result: ResearchResult, progress_callback=None) -> ResearchResult:
    """Run Layer 3: agentic expert analysis with assumption auditing and C-suite review."""
    logger.info(f"[Layer 3] Expert agent starting for: {topic}")
    start = time.time()

    # Store Layer 2 content for callbacks to access
    global _l3_layer2_content, _l3_expert_critique
    _l3_layer2_content = layer2_result.content
    _l3_expert_critique = {}

    draft, sources, iterations = await run_agent_loop(
        topic=topic,
        layer=3,
        plan_fn=_l3_plan,
        research_fn=_l3_research,
        draft_fn=_l3_draft,
        evaluate_fn=_l3_evaluate,
        max_iterations=3,
        convergence_threshold=8.0,
        existing_sources=list(layer2_result.sources),
        progress_callback=progress_callback,
    )

    elapsed = time.time() - start
    final_score = iterations[-1].eval_score if iterations else 0
    logger.info(f"[Layer 3] Done in {elapsed:.1f}s — {len(draft.split())} words, "
                f"{len(sources)} sources, {len(iterations)} iterations, "
                f"final score: {final_score:.1f}/10")

    return ResearchResult(
        layer=3,
        topic=topic,
        content=draft,
        sources=sources,
        metadata={
            "method": "agentic_expert_analysis",
            "iterations": len(iterations),
            "final_score": final_score,
            "iteration_history": [
                {"iteration": it.iteration, "score": it.eval_score,
                 "weaknesses": it.weaknesses}
                for it in iterations
            ],
            "expert_critique": {
                "assumptions": len(_l3_expert_critique.get("assumptions", [])),
                "second_order_effects": len(_l3_expert_critique.get("second_order_effects", [])),
                "cross_industry_parallels": len(_l3_expert_critique.get("cross_industry_parallels", [])),
                "has_blind_spot": bool(_l3_expert_critique.get("biggest_blind_spot")),
            },
            "sources_found": len(sources),
            "sources_scraped": sum(1 for s in sources if s.scraped_content),
        },
        elapsed_seconds=elapsed,
    )
