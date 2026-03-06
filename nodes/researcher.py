"""
Web Researcher node.

Iterative search → scrape → extract loop.
- Executes search queries from the planner
- Evaluates and scrapes top results
- Extracts data points with citations
- Decides if more research is needed (max 3 iterations)
"""

import asyncio
import json
import logging
from datetime import datetime

from config import get_llm, SEARCH_RESULTS_PER_QUERY, MIN_CITATIONS_PER_SUBSECTION
from prompts.researcher import RESEARCHER_SYSTEM, EXTRACTION_PROMPT, RESEARCH_SUFFICIENCY_PROMPT
from state import SubSectionWorkerState
from tools.citation import validate_citation, generate_citation_id
from tools.search import search, enhance_query_for_primary_sources
from tools.scraper import scrape_url

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine, handling event loop edge cases."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _execute_search_queries(queries: list[dict], topic: str) -> list[dict]:
    """Execute multiple search queries and collect results."""
    all_results = []
    for q in queries:
        query_str = q.get("query", "") if isinstance(q, dict) else str(q)
        if not query_str:
            continue

        try:
            results = await search(query_str, max_results=SEARCH_RESULTS_PER_QUERY)
            for r in results:
                r["original_query"] = query_str
            all_results.extend(results)
        except Exception as e:
            logger.warning(f"Search failed for query '{query_str[:50]}': {e}")

    # Also try an enhanced query for primary sources
    if queries:
        first_query = queries[0].get("query", "") if isinstance(queries[0], dict) else str(queries[0])
        enhanced = enhance_query_for_primary_sources(f"{topic} {first_query[:30]}")
        try:
            results = await search(enhanced, max_results=5, include_news=False)
            all_results.extend(results)
        except Exception:
            pass

    return all_results


async def _scrape_top_urls(search_results: list[dict], max_urls: int = 3) -> list[dict]:
    """Scrape the top N unique URLs from search results."""
    seen_urls = set()
    urls_to_scrape = []
    for r in search_results:
        url = r.get("url", "")
        if url and url not in seen_urls and not url.endswith(".pdf"):
            seen_urls.add(url)
            urls_to_scrape.append(url)
            if len(urls_to_scrape) >= max_urls:
                break

    scraped = []
    for url in urls_to_scrape:
        try:
            result = await scrape_url(url)
            if result:
                scraped.append(result)
        except Exception as e:
            logger.warning(f"Scrape failed for {url}: {e}")

    return scraped


def _extract_data_from_page(page: dict, subsection_name: str, topic: str, subsection_id: str,
                            citation_offset: int) -> tuple[list[dict], list[dict]]:
    """Use LLM to extract structured data points from a scraped page.

    Returns (new_search_results, new_citations).
    """
    llm = get_llm("researcher")

    prompt = EXTRACTION_PROMPT.format(
        subsection_name=subsection_name,
        topic=topic,
        url=page.get("url", ""),
        title=page.get("title", ""),
        content=page.get("content", "")[:8000],  # Cap for token limits
    )

    messages = [
        {"role": "system", "content": RESEARCHER_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    try:
        response = llm.invoke(messages)
        content = response.content

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        data_points = json.loads(content.strip())
        if not isinstance(data_points, list):
            data_points = []
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Extraction failed for {page.get('url', '?')}: {e}")
        data_points = []

    new_results = []
    new_citations = []

    for i, dp in enumerate(data_points):
        url = dp.get("source_url", page.get("url", ""))
        title = dp.get("publisher", page.get("title", ""))
        publisher = dp.get("publisher", "")

        is_competitor = not validate_citation(url, title, publisher)

        if is_competitor:
            # Keep competitor data for research but don't create citation
            logger.info(f"Competitor source (kept for research, no citation): {publisher}")
            new_results.append({
                "query": f"extracted from {url}",
                "title": page.get("title", ""),
                "url": url,
                "snippet": dp.get("text", ""),
                "source": "scraped_extraction",
                "category": dp.get("category", "fact"),
                "_is_competitor": True,
            })
        else:
            citation_id = generate_citation_id(subsection_id, citation_offset + i)

            new_citations.append({
                "id": citation_id,
                "url": url,
                "title": page.get("title", ""),
                "source_type": _infer_source_type(url, publisher),
                "publisher": publisher,
                "date": dp.get("date"),
                "snippet": dp.get("text", ""),
                "is_valid": True,
            })

            new_results.append({
                "query": f"extracted from {url}",
                "title": page.get("title", ""),
                "url": url,
                "snippet": dp.get("text", ""),
                "source": "scraped_extraction",
                "citation_id": citation_id,
                "category": dp.get("category", "fact"),
            })

    return new_results, new_citations


def _infer_source_type(url: str, publisher: str) -> str:
    """Infer citation source type from URL and publisher."""
    url_lower = url.lower()
    pub_lower = publisher.lower()

    if "sec.gov" in url_lower:
        return "sec_filing"
    elif "fda.gov" in url_lower:
        return "fda_database"
    elif "ema.europa.eu" in url_lower:
        return "ema_database"
    elif "who.int" in url_lower or "nih.gov" in url_lower or "cdc.gov" in url_lower:
        return "gov_database"
    elif "clinicaltrials.gov" in url_lower:
        return "clinical_trial"
    elif "reuters" in pub_lower or "bloomberg" in pub_lower or "wsj" in pub_lower or "ft.com" in url_lower:
        return "news_article"
    elif "nature.com" in url_lower or "lancet" in url_lower or "nejm" in url_lower or "pubmed" in url_lower:
        return "journal"
    elif "prnewswire" in url_lower or "businesswire" in url_lower or "globenewswire" in url_lower:
        return "press_release"
    elif "investor" in url_lower or "annual-report" in url_lower or "10-k" in url_lower:
        return "investor_presentation"
    else:
        return "news_article"


def _check_sufficiency(state: SubSectionWorkerState) -> dict:
    """Use LLM to evaluate if enough research data has been collected."""
    llm = get_llm("researcher")
    citations = state.get("citations", [])
    search_results = state.get("search_results", [])

    # Count data types
    stats = [r for r in search_results if isinstance(r, dict) and r.get("category") == "statistic"]
    actions = [r for r in search_results if isinstance(r, dict) and r.get("category") == "company_action"]
    regs = [r for r in search_results if isinstance(r, dict) and r.get("category") == "regulatory_info"]
    facts = [r for r in search_results if isinstance(r, dict) and r.get("category") == "fact"]

    data_summary = "\n".join(
        f"- {r.get('snippet', '')[:100]}"
        for r in search_results[-15:]
        if isinstance(r, dict) and r.get("snippet")
    )

    prompt = RESEARCH_SUFFICIENCY_PROMPT.format(
        subsection_name=state["subsection_name"],
        topic=state["topic"],
        fact_count=len(facts),
        stat_count=len(stats),
        action_count=len(actions),
        reg_count=len(regs),
        citation_count=len(citations),
        data_summary=data_summary or "No data collected yet.",
    )

    messages = [
        {"role": "system", "content": RESEARCHER_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    try:
        response = llm.invoke(messages)
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        return json.loads(content.strip())
    except Exception:
        # Default: sufficient if we have enough citations
        return {"sufficient": len(citations) >= MIN_CITATIONS_PER_SUBSECTION, "additional_queries": []}


def researcher_node(state: SubSectionWorkerState) -> dict:
    """Execute one iteration of web research for a sub-section."""
    subsection_id = state["subsection_id"]
    subsection_name = state["subsection_name"]
    iteration = state.get("research_iteration", 0)
    existing_citations = state.get("citations", [])

    logger.info(f"Research iteration {iteration + 1} for: {subsection_name}")

    # Get queries for this iteration
    queries = state.get("research_queries", [])

    # Execute searches
    raw_results = _run_async(_execute_search_queries(queries, state["topic"]))
    logger.info(f"Got {len(raw_results)} search results for {subsection_name}")

    # Filter out duplicates by URL
    seen_urls = {r.get("url") for r in state.get("search_results", []) if isinstance(r, dict)}
    new_results = [r for r in raw_results if r.get("url") not in seen_urls]

    # Scrape top URLs for deeper content
    scraped_pages = _run_async(_scrape_top_urls(new_results, max_urls=3))
    logger.info(f"Scraped {len(scraped_pages)} pages for {subsection_name}")

    # Extract data points from scraped pages
    all_new_results = []
    all_new_citations = []
    citation_offset = len(existing_citations)

    for page in scraped_pages:
        new_sr, new_cit = _extract_data_from_page(
            page, subsection_name, state["topic"], subsection_id, citation_offset
        )
        all_new_results.extend(new_sr)
        all_new_citations.extend(new_cit)
        citation_offset += len(new_cit)

    # Also create citations/results from search result snippets (no scraping needed)
    for r in new_results[:5]:
        url = r.get("url", "")
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        if not snippet:
            continue

        if validate_citation(url, title):
            # Primary source — create citation
            cid = generate_citation_id(subsection_id, citation_offset)
            all_new_citations.append({
                "id": cid,
                "url": url,
                "title": title,
                "source_type": _infer_source_type(url, ""),
                "publisher": r.get("source", "web"),
                "date": r.get("date"),
                "snippet": snippet,
                "is_valid": True,
            })
            all_new_results.append({
                "query": r.get("original_query", ""),
                "title": title,
                "url": url,
                "snippet": snippet,
                "source": r.get("source", "web"),
                "citation_id": cid,
                "category": "fact",
            })
            citation_offset += 1
        else:
            # Competitor source — keep data for research, no citation
            all_new_results.append({
                "query": r.get("original_query", ""),
                "title": title,
                "url": url,
                "snippet": snippet,
                "source": r.get("source", "web"),
                "category": "fact",
                "_is_competitor": True,
            })

    logger.info(f"Extracted {len(all_new_citations)} citations, {len(all_new_results)} data points")

    # Check if we need more research and generate refined queries
    temp_state = dict(state)
    temp_state["citations"] = existing_citations + all_new_citations
    temp_state["search_results"] = state.get("search_results", []) + all_new_results

    sufficiency = _check_sufficiency(temp_state)

    # Update research queries for next iteration if needed
    new_queries = []
    if not sufficiency.get("sufficient", False) and sufficiency.get("additional_queries"):
        new_queries = [
            {"subsection_id": subsection_id, "query": q, "intent": "gap fill", "priority": 1}
            for q in sufficiency["additional_queries"]
        ]

    return {
        "search_results": all_new_results,  # Merged via operator.add
        "citations": all_new_citations,     # Merged via operator.add
        "research_iteration": iteration + 1,
        "research_queries": new_queries if new_queries else queries,
    }
