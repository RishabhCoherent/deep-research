"""
Phase 2 — RESEARCH: Systematic data collection driven by the research plan.

Processes research questions CONCURRENTLY in batches (one per section at a time)
using asyncio.gather for ~3-5x speedup over sequential processing.

After the first pass, a gap analysis fills unanswered questions.
The LLM is used ONLY for fact extraction (cheap model).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict

from config import get_llm
from research_agent.models import ResearchPlan, KnowledgeBase, Fact, ResearchResult, Source
from research_agent.prompts import PHASE2_EXTRACT_PROMPT, PHASE2_SCRAPE_EXTRACT_PROMPT
from research_agent.cost import track
from research_agent.utils import extract_json, get_content, infer_publisher
from tools.search import search
from tools.scraper import scrape_url
from tools.source_classifier import get_source_tier

logger = logging.getLogger(__name__)

# How many of the top search results to scrape for detailed extraction
SCRAPE_TOP_N = 2
# Max search queries per question
MAX_QUERIES_PER_QUESTION = 2
# Per-section tool call budget — actual max = num_sections * TOOL_CALLS_PER_SECTION
TOOL_CALLS_PER_SECTION = 8
# Max concurrent questions being researched at once
MAX_CONCURRENCY = 4


async def _search_and_extract(
    question, section: str, kb: KnowledgeBase, llm,
    tool_calls: list[int], max_tool_calls: int,
    semaphore: asyncio.Semaphore,
) -> list[Fact]:
    """Run search queries for a question and extract facts. Semaphore-limited."""
    facts_found = []

    async with semaphore:
        for query in question.search_queries[:MAX_QUERIES_PER_QUESTION]:
            if tool_calls[0] >= max_tool_calls:
                break

            # Search
            try:
                results = await search(query, max_results=6, include_news=False)
                tool_calls[0] += 1
            except Exception as e:
                logger.warning(f"[Phase 2] Search failed for '{query}': {e}")
                continue

            if not results:
                continue

            # Track URLs
            for r in results:
                url = r.get("url", "")
                if url:
                    kb.urls_seen.add(url)

            # Format search results for extraction
            search_text = ""
            for i, r in enumerate(results, 1):
                search_text += (
                    f"\n--- Result {i} ---\n"
                    f"Title: {r.get('title', '')}\n"
                    f"URL: {r.get('url', '')}\n"
                    f"Snippet: {r.get('snippet', '')}\n"
                )

            # Extract facts via LLM (async)
            try:
                extract_messages = [
                    {"role": "system", "content": "You extract factual data from search results. Return ONLY valid JSON."},
                    {"role": "user", "content": PHASE2_EXTRACT_PROMPT.format(
                        question=question.question,
                        section=section,
                        data_type=question.data_type,
                        search_results=search_text,
                    )},
                ]
                response = await llm.ainvoke(extract_messages)
                track("P2 extract", response)
                extracted = extract_json(get_content(response).strip())
            except Exception as e:
                logger.warning(f"[Phase 2] Extraction failed: {e}")
                continue

            if not isinstance(extracted, list):
                continue

            for item in extracted:
                if not isinstance(item, dict) or not item.get("claim"):
                    continue

                url = item.get("source_url", "")
                tier = get_source_tier(url) if url else 3

                fact = Fact(
                    id=f"f_{uuid.uuid4().hex[:8]}",
                    question_id=question.id,
                    section=section,
                    claim=item["claim"],
                    value=str(item.get("value", "")),
                    data_type=question.data_type,
                    source_url=url,
                    source_title=item.get("source_title", ""),
                    source_tier=tier,
                    confidence=item.get("confidence", "medium"),
                    raw_snippet=item.get("claim", ""),
                )
                kb.add_fact(fact)
                facts_found.append(fact)

            # Scrape top results for deeper extraction (only for priority 1 questions)
            if question.priority == 1 and tool_calls[0] < max_tool_calls:
                for r in results[:SCRAPE_TOP_N]:
                    url = r.get("url", "")
                    if not url or tool_calls[0] >= max_tool_calls:
                        break

                    try:
                        scrape_result = await scrape_url(url)
                        tool_calls[0] += 1
                    except Exception:
                        continue

                    if not scrape_result:
                        continue
                    page_content = scrape_result.get("content", "") if isinstance(scrape_result, dict) else str(scrape_result)
                    if not page_content or len(page_content.strip()) < 200:
                        continue

                    # Extract facts from scraped content (async)
                    try:
                        scrape_messages = [
                            {"role": "system", "content": "Extract facts from web page content. Return ONLY valid JSON."},
                            {"role": "user", "content": PHASE2_SCRAPE_EXTRACT_PROMPT.format(
                                question=question.question,
                                section=section,
                                page_content=page_content[:4000],
                            )},
                        ]
                        response = await llm.ainvoke(scrape_messages)
                        track("P2 scrape_extract", response)
                        scraped_facts = extract_json(get_content(response).strip())
                    except Exception:
                        continue

                    if not isinstance(scraped_facts, list):
                        continue

                    title = r.get("title", "")
                    tier = get_source_tier(url)

                    for sf in scraped_facts:
                        if not isinstance(sf, dict) or not sf.get("claim"):
                            continue
                        fact = Fact(
                            id=f"f_{uuid.uuid4().hex[:8]}",
                            question_id=question.id,
                            section=section,
                            claim=sf["claim"],
                            value=str(sf.get("value", "")),
                            data_type=question.data_type,
                            source_url=url,
                            source_title=title,
                            source_tier=tier,
                            confidence=sf.get("confidence", "medium"),
                            raw_snippet=sf.get("claim", ""),
                        )
                        kb.add_fact(fact)
                        facts_found.append(fact)

    return facts_found


async def run(
    plan: ResearchPlan,
    progress_callback=None,
) -> tuple[KnowledgeBase, ResearchResult]:
    """
    Execute the research plan with concurrent question processing.

    Questions are processed in batches using asyncio.gather, with a semaphore
    limiting concurrency. Round-robin ordering ensures every section gets
    coverage before going deeper.
    """
    start = time.time()
    kb = KnowledgeBase()
    llm = get_llm("researcher")
    tool_calls = [0]  # mutable counter (safe in asyncio — single thread)
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    def notify(status: str, msg: str):
        if progress_callback:
            progress_callback(1, status, msg)
        logger.info(f"[Phase 2] {status}: {msg}")

    # Dynamic tool call budget: scales with number of sections
    max_tool_calls = max(len(plan.sections) * TOOL_CALLS_PER_SECTION, 30)

    notify("start", f"Researching {len(plan.questions)} questions across "
                     f"{len(plan.sections)} sections (budget: {max_tool_calls} calls)...")

    # ── Build round-robin question order ──────────────────────────────────
    section_queues: dict[str, list] = defaultdict(list)
    for q in plan.questions:
        section_queues[q.section].append(q)
    for section in section_queues:
        section_queues[section].sort(key=lambda q: (q.priority, q.id))

    sorted_questions = []
    max_depth = max((len(qs) for qs in section_queues.values()), default=0)
    for depth in range(max_depth):
        for section in plan.sections:
            qs = section_queues.get(section, [])
            if depth < len(qs):
                sorted_questions.append(qs[depth])

    # ── Pass 1: Research questions concurrently in batches ─────────────────
    batch_size = max(len(plan.sections), MAX_CONCURRENCY)
    all_query_results = []  # (question, facts) pairs for tracking

    for batch_start in range(0, len(sorted_questions), batch_size):
        if tool_calls[0] >= max_tool_calls:
            notify("budget", "Search budget reached, moving to gap analysis...")
            break

        batch = sorted_questions[batch_start:batch_start + batch_size]
        batch = [q for q in batch if tool_calls[0] < max_tool_calls]
        if not batch:
            break

        notify("researching",
               f"Batch {batch_start // batch_size + 1}: "
               f"researching {len(batch)} questions concurrently...")

        tasks = [
            _search_and_extract(q, q.section, kb, llm, tool_calls, max_tool_calls, semaphore)
            for q in batch
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for q, result in zip(batch, results):
            if isinstance(result, Exception):
                logger.warning(f"[Phase 2] Question failed: {result}")
                q.status = "gap"
                all_query_results.append((q, []))
            elif result:
                q.status = "answered"
                all_query_results.append((q, result))
                notify("researching",
                       f"Found {len(result)} facts for '{q.section}'")
            else:
                q.status = "gap"
                all_query_results.append((q, []))

    pass1_coverage = kb.coverage_score(plan)
    pass1_facts = len(kb.facts)
    notify("drafted", f"Pass 1 complete: {pass1_facts} facts, "
                       f"{pass1_coverage:.0%} coverage")

    # ── Build iteration_queries for frontend ──────────────────────────────
    iteration_queries = []
    for q, facts in all_query_results:
        for query in q.search_queries[:MAX_QUERIES_PER_QUESTION]:
            iteration_queries.append({
                "tool": "search_web",
                "query": query,
                "hits": [
                    {"title": f.source_title, "snippet": f.claim[:150], "url": f.source_url}
                    for f in facts[:3]
                ],
            })

    # ── Pass 2: Gap-filling concurrently ──────────────────────────────────
    gap_questions = [q for q in plan.questions if q.status == "gap" and q.priority <= 2]
    gap_queries = []

    if gap_questions and tool_calls[0] < max_tool_calls:
        notify("researching", f"Gap analysis: {len(gap_questions)} questions concurrently...")

        for question in gap_questions:
            question.search_queries = [f"{plan.topic} {question.question} 2025 2026"]

        gap_batch = [q for q in gap_questions if tool_calls[0] < max_tool_calls]
        tasks = [
            _search_and_extract(q, q.section, kb, llm, tool_calls, max_tool_calls, semaphore)
            for q in gap_batch
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for q, result in zip(gap_batch, results):
            facts = result if isinstance(result, list) else []
            if facts:
                q.status = "answered"
            gap_queries.append({
                "tool": "search_web",
                "query": q.search_queries[0],
                "hits": [
                    {"title": f.source_title, "snippet": f.claim[:150], "url": f.source_url}
                    for f in facts[:3]
                ],
            })

    final_coverage = kb.coverage_score(plan)
    elapsed = time.time() - start

    notify("done", f"Research complete: {len(kb.facts)} facts, "
                    f"{len(kb.urls_seen)} sources, {final_coverage:.0%} coverage "
                    f"in {elapsed:.0f}s")

    # ── Build Sources list for compatibility ──────────────────────────────
    seen_urls = set()
    sources = []
    for fact in kb.facts:
        if fact.source_url and fact.source_url not in seen_urls:
            seen_urls.add(fact.source_url)
            sources.append(Source(
                url=fact.source_url,
                title=fact.source_title,
                snippet=fact.claim[:200],
                publisher=infer_publisher(fact.source_url),
                tier=fact.source_tier,
                credibility={1: "high", 2: "medium", 3: "low"}.get(fact.source_tier, "unknown"),
            ))

    # ── Build content summary ─────────────────────────────────────────────
    content_lines = [f"## Research Summary: {plan.topic}", ""]
    for section in plan.sections:
        section_facts = kb.facts_for_section(section)
        content_lines.append(f"### {section} ({len(section_facts)} facts)")
        for f in section_facts[:5]:
            content_lines.append(f"- {f.claim}")
        if len(section_facts) > 5:
            content_lines.append(f"- ... and {len(section_facts) - 5} more")
        content_lines.append("")

    # ── Build iteration_history for frontend ──────────────────────────────
    iteration_history = [
        {
            "iteration": 0,
            "score": round(pass1_coverage * 10, 1),
            "weaknesses": [
                f"{q.section}: {q.question}" for q in gap_questions[:3]
            ],
            "queries": iteration_queries,
            "stop_reason": "",
        },
    ]
    if gap_queries:
        iteration_history.append({
            "iteration": 1,
            "score": round(final_coverage * 10, 1),
            "weaknesses": [
                f"{q.section}: {q.question}"
                for q in plan.questions if q.status == "gap"
            ][:3],
            "queries": gap_queries,
            "stop_reason": "threshold" if final_coverage >= 0.8 else "plateau",
        })

    layer_result = ResearchResult(
        layer=1,
        topic=plan.topic,
        content="\n".join(content_lines),
        sources=sources,
        metadata={
            "method": "systematic_research",
            "iterations": len(iteration_history),
            "final_score": round(final_coverage * 10, 1),
            "tool_calls": tool_calls[0],
            "facts_collected": len(kb.facts),
            "coverage": round(final_coverage, 3),
            "questions_answered": len([q for q in plan.questions if q.status == "answered"]),
            "questions_gap": len([q for q in plan.questions if q.status == "gap"]),
            "iteration_history": iteration_history,
            "sources_found": len(sources),
            "sources_scraped": sum(1 for _ in sources),  # approximate
        },
        elapsed_seconds=elapsed,
    )

    return kb, layer_result
