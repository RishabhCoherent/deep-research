"""
Phase 3 — ANALYZE: Verify facts, resolve conflicts, fill gaps, generate insights.

Takes the KnowledgeBase from Phase 2 and:
1. Cross-references key numerical claims (search for corroboration)
2. Resolves conflicting facts (prefer T1/T2 sources)
3. Fills remaining gaps with targeted searches
4. Generates analytical insights that connect facts across sections
5. Produces section impact ratings
"""

from __future__ import annotations

import asyncio
import logging
import time

from config import get_llm
from research_agent.models import ResearchPlan, KnowledgeBase, Fact, ResearchResult, Source
from research_agent.prompts import PHASE3_VERIFY_PROMPT, PHASE3_INSIGHT_PROMPT, get_insight_rules
from research_agent.cost import track
from research_agent.utils import extract_json, get_content
from tools.search import search
from tools.source_classifier import get_source_tier

logger = logging.getLogger(__name__)

MAX_VERIFY_SEARCHES = 10


async def _verify_section_facts(
    section: str, kb: KnowledgeBase, plan: ResearchPlan,
    llm_verify, tool_calls: list[int], notify,
) -> dict:
    """Verify key facts for one section by searching for corroboration."""
    facts = kb.facts_for_section(section)
    if not facts:
        return {"verified": 0, "corrected": 0}

    # Pick the most important facts to verify (T3 sources, numerical claims)
    facts_to_verify = []
    for f in facts:
        val_str = str(f.value) if f.value else ""
        has_number = any(c.isdigit() for c in val_str)
        if f.source_tier >= 3 and has_number:
            facts_to_verify.append(f)
        elif has_number and f.confidence != "high":
            facts_to_verify.append(f)

    if not facts_to_verify:
        return {"verified": len(facts), "corrected": 0}

    # Search for verification data
    verify_query = f"{plan.topic} {section} data statistics 2025 2026"
    verification_data = ""

    if tool_calls[0] < MAX_VERIFY_SEARCHES:
        try:
            results = await search(verify_query, max_results=5, include_news=False)
            tool_calls[0] += 1
            for r in results:
                verification_data += f"- {r.get('title', '')}: {r.get('snippet', '')}\n"
        except Exception as e:
            logger.warning(f"[Phase 3] Verification search failed: {e}")

    if not verification_data:
        return {"verified": 0, "corrected": 0}

    # LLM verification
    facts_text = "\n".join(
        f"[{f.id}] {f.claim} (source: {f.source_title}, tier: T{f.source_tier})"
        for f in facts_to_verify[:8]
    )

    try:
        messages = [
            {"role": "system", "content": "You are a fact-checker. Return ONLY valid JSON."},
            {"role": "user", "content": PHASE3_VERIFY_PROMPT.format(
                topic=plan.topic,
                section=section,
                facts=facts_text,
                verification_data=verification_data,
            )},
        ]
        response = await llm_verify.ainvoke(messages)
        track("P3 verify", response)
        result = extract_json(get_content(response).strip())
    except Exception as e:
        logger.warning(f"[Phase 3] Verification LLM failed: {e}")
        return {"verified": 0, "corrected": 0}

    verified_count = 0
    corrected_count = 0

    if isinstance(result, dict):
        verified_list = result.get("verified", [])
        if not isinstance(verified_list, list):
            verified_list = []
        for v in verified_list:
            if not isinstance(v, dict):
                continue
            status = v.get("status", "")
            if status == "confirmed":
                verified_count += 1
                fact_id = v.get("fact_id", "")
                for f in facts_to_verify:
                    if f.id == fact_id:
                        f.confidence = "high"
            elif status == "corrected":
                corrected_count += 1
                fact_id = v.get("fact_id", "")
                corrected_claim = v.get("corrected_claim", "")
                if corrected_claim:
                    for f in facts_to_verify:
                        if f.id == fact_id:
                            f.claim = corrected_claim
                            f.confidence = "medium"

    return {"verified": verified_count, "corrected": corrected_count}


async def _generate_insights(
    plan: ResearchPlan, kb: KnowledgeBase, llm_analyst,
) -> tuple[list[str], list[str], list[dict]]:
    """Generate analytical insights from the knowledge base."""
    knowledge_text = kb.format_all(plan)

    try:
        messages = [
            {"role": "system", "content": "You are a senior strategic analyst. Return ONLY valid JSON."},
            {"role": "user", "content": PHASE3_INSIGHT_PROMPT.format(
                topic=plan.topic,
                report_type=plan.report_type,
                knowledge=knowledge_text[:18000],
                topic_insight_rules=get_insight_rules(plan.report_type),
            )},
        ]
        response = await llm_analyst.ainvoke(messages)
        track("P3 insights", response)
        result = extract_json(get_content(response).strip())
    except Exception as e:
        logger.warning(f"[Phase 3] Insight generation failed: {e}")
        return [], [], []

    if not isinstance(result, dict):
        return [], [], []

    insights = result.get("insights", [])
    if not isinstance(insights, list):
        insights = []
    contrarian_risks = result.get("contrarian_risks", [])
    if not isinstance(contrarian_risks, list):
        contrarian_risks = []
    section_impacts = result.get("section_impacts", [])
    if not isinstance(section_impacts, list):
        section_impacts = []

    # Normalize impact levels
    normalized_impacts = []
    for si in section_impacts:
        if isinstance(si, dict) and si.get("section"):
            impact = str(si.get("impact", "moderate")).lower()
            if impact not in ("high", "moderate", "low"):
                impact = "moderate"
            normalized_impacts.append({
                "section": si["section"],
                "impact": impact,
                "reason": si.get("reason", ""),
            })

    return (
        [str(i) for i in insights if i],
        [str(r) for r in contrarian_risks if r],
        normalized_impacts,
    )


async def run(
    plan: ResearchPlan,
    kb: KnowledgeBase,
    progress_callback=None,
) -> tuple[KnowledgeBase, list[str], list[str], list[dict], ResearchResult]:
    """
    Verify, analyze, and enrich the knowledge base.

    Returns:
        (kb, insights, contrarian_risks, section_impacts, layer_result)
    """
    start = time.time()
    tool_calls = [0]

    def notify(status: str, msg: str):
        if progress_callback:
            progress_callback(2, status, msg)
        logger.info(f"[Phase 3] {status}: {msg}")

    notify("start", "Verifying and analyzing collected data...")

    llm_verify = get_llm("researcher")  # cheap model for verification
    llm_analyst = get_llm("analyst")     # quality model for insights

    # ── Step 1: Verify facts by section (ALL SECTIONS CONCURRENTLY) ──────
    notify("evaluating", f"Verifying facts across {len(plan.sections)} sections concurrently...")

    sections_with_facts = [
        (s, kb.facts_for_section(s)) for s in plan.sections
        if kb.facts_for_section(s)
    ]

    verify_tasks = [
        _verify_section_facts(section, kb, plan, llm_verify, tool_calls, notify)
        for section, _ in sections_with_facts
    ]
    verify_results = await asyncio.gather(*verify_tasks, return_exceptions=True)

    total_verified = 0
    total_corrected = 0
    verify_queries = []

    for (section, section_facts), result in zip(sections_with_facts, verify_results):
        if isinstance(result, Exception):
            logger.warning(f"[Phase 3] Verification failed for '{section}': {result}")
            result = {"verified": 0, "corrected": 0}
        total_verified += result["verified"]
        total_corrected += result["corrected"]
        verify_queries.append({
            "tool": "verify_claim",
            "query": f"Verify {section} data ({len(section_facts)} facts)",
            "hits": [
                {"title": f.source_title, "snippet": f.claim[:100], "url": f.source_url}
                for f in section_facts[:3]
            ],
        })

    notify("evaluating", f"Verification: {total_verified} confirmed, "
                          f"{total_corrected} corrected")

    # ── Step 2: Gap-filling for thin sections (CONCURRENTLY) ──────────────
    thin_sections = [
        s for s in plan.sections
        if len(kb.facts_for_section(s)) < 2 and tool_calls[0] < MAX_VERIFY_SEARCHES
    ]

    gap_queries = []
    if thin_sections:
        notify("researching", f"Gap-filling {len(thin_sections)} thin sections concurrently...")

        async def _fill_gap(section: str):
            gap_query = f"{plan.topic} {section} data 2025 2026"
            try:
                results = await search(gap_query, max_results=5, include_news=False)
                tool_calls[0] += 1
                for r in results:
                    snippet = r.get("snippet", "")
                    url = r.get("url", "")
                    if snippet and len(snippet) > 50:
                        fact = Fact(
                            id=f"f_gap_{len(kb.facts)}",
                            question_id="gap_fill",
                            section=section,
                            claim=snippet[:300],
                            source_url=url,
                            source_title=r.get("title", ""),
                            source_tier=get_source_tier(url),
                            confidence="medium",
                        )
                        kb.add_fact(fact)
                return {
                    "tool": "search_web",
                    "query": gap_query,
                    "hits": [
                        {"title": r.get("title", ""), "snippet": r.get("snippet", "")[:100],
                         "url": r.get("url", "")}
                        for r in results[:3]
                    ],
                }
            except Exception as e:
                logger.warning(f"[Phase 3] Gap-fill search failed: {e}")
                return None

        gap_results = await asyncio.gather(*[_fill_gap(s) for s in thin_sections])
        gap_queries = [r for r in gap_results if r]

    # ── Step 3: Generate insights ─────────────────────────────────────────
    notify("evaluating", "Generating analytical insights...")
    insights, contrarian_risks, section_impacts = await _generate_insights(
        plan, kb, llm_analyst
    )

    notify("evaluating", f"Generated {len(insights)} insights, "
                          f"{len(contrarian_risks)} contrarian risks, "
                          f"{len(section_impacts)} impact ratings")

    elapsed = time.time() - start
    final_coverage = kb.coverage_score(plan)

    notify("done", f"Analysis complete: {total_verified} verified, "
                    f"{total_corrected} corrected, {len(insights)} insights")

    # ── Build content summary ─────────────────────────────────────────────
    content_lines = [f"## Analysis Summary: {plan.topic}", ""]

    content_lines.append("### Verification Results")
    content_lines.append(f"- Facts verified: {total_verified}")
    content_lines.append(f"- Facts corrected: {total_corrected}")
    content_lines.append(f"- Total facts: {len(kb.facts)}")
    content_lines.append("")

    if insights:
        content_lines.append("### Key Insights")
        for ins in insights:
            content_lines.append(f"- {ins}")
        content_lines.append("")

    if contrarian_risks:
        content_lines.append("### Contrarian Risks")
        for risk in contrarian_risks:
            content_lines.append(f"- {risk}")
        content_lines.append("")

    # Build Sources
    seen_urls = set()
    sources = []
    for fact in kb.facts:
        if fact.source_url and fact.source_url not in seen_urls:
            seen_urls.add(fact.source_url)
            sources.append(Source(
                url=fact.source_url,
                title=fact.source_title,
                snippet=fact.claim[:200],
                tier=fact.source_tier,
            ))

    # ── Build iteration_history for frontend ──────────────────────────────
    iteration_history = [
        {
            "iteration": 0,
            "score": round(final_coverage * 10, 1),
            "weaknesses": [
                f"Corrected {total_corrected} facts" if total_corrected else "No corrections needed",
            ] + [f"Thin section: {s}" for s in plan.sections if len(kb.facts_for_section(s)) < 3][:2],
            "queries": verify_queries + gap_queries,
            "stop_reason": "threshold",
        },
    ]

    layer_result = ResearchResult(
        layer=2,
        topic=plan.topic,
        content="\n".join(content_lines),
        sources=sources,
        metadata={
            "method": "verification_analysis",
            "iterations": 1,
            "final_score": round(final_coverage * 10, 1),
            "tool_calls": tool_calls[0],
            "verifications": total_verified + total_corrected,
            "facts_verified": total_verified,
            "facts_corrected": total_corrected,
            "insights_generated": len(insights),
            "contrarian_risks": len(contrarian_risks),
            "section_impacts": section_impacts,
            "iteration_history": iteration_history,
            "sources_found": len(sources),
            "sources_scraped": 0,
        },
        elapsed_seconds=elapsed,
    )

    return kb, insights, contrarian_risks, section_impacts, layer_result
