"""
Layer 2 — Analysis Agent (Agentic): Critical Read → Plan → Research → Draft → Self-Evaluate → Refine.

Mimics what a senior analyst (10+ years experience) does:
1. Critical Read: Reads Layer 1 with a skeptical eye — finds weak claims, gaps, implausible data
2. Research Plan: Prioritizes problems as "verify" or "fill" tasks
3. Targeted Research: Executes verification searches, scrapes, cross-references
4. Draft: Writes deep analytical synthesis with verified data
5. Self-Review: Scores rigor, depth, quantification, completeness
6. Refine: Iterates on weaknesses (up to 2 more iterations)

What it adds over Layer 1:
- Source triangulation (claims verified across multiple sources)
- Critical reading of prior work (not blind acceptance)
- Framework-based analysis (structured analytical thinking)
- Gap-filling (targeted research for what's missing)
- Quantification of vague claims
- Iterative self-improvement loop
"""

from __future__ import annotations

import json
import logging
import re
import time

from config import get_llm
from tools.search import search
from tools.scraper import scrape_url
from tools.source_classifier import get_source_tier
from research_agent.types import ResearchResult, Source
from research_agent.prompts import (
    LAYER2_SYSTEM, LAYER2_USER, LAYER2_CLAIM_EXTRACTION,
    LAYER2_CRITICAL_READ, LAYER2_RESEARCH_PLAN, LAYER2_SELF_REVIEW, LAYER2_REFINE,
)
from research_agent.utils import extract_json
from research_agent.cost import track
from research_agent.agent_loop import run_agent_loop, EvalResult

logger = logging.getLogger(__name__)


# ─── Existing helpers (unchanged) ────────────────────────────────────────────


def _build_claim_verdict(claimed_value: str, evidence: list[dict]) -> dict:
    """Heuristic verdict: compare claimed value against search evidence.

    Uses tighter tolerance for percentages (30%) vs absolute numbers (50%)
    because percentage errors are more impactful (31% vs 20% is a huge difference
    in market share analysis, but passes a loose 2x check).
    """
    if not evidence:
        return {"verdict": "UNVERIFIED", "evidence": "No verification evidence found"}

    # Extract numbers from claimed value
    claimed_numbers = _extract_numbers(claimed_value)
    is_percentage = "%" in claimed_value

    # Collect numbers from evidence snippets, preferring tier-1
    evidence_numbers = []
    evidence_texts = []
    for e in sorted(evidence, key=lambda x: x.get("tier", 3)):
        snippet = e.get("snippet", "")
        evidence_texts.append(f"[T{e.get('tier', 3)}] {e.get('source', '')}: {snippet}")
        nums = _extract_numbers(snippet)
        evidence_numbers.extend(nums)

    evidence_summary = " | ".join(evidence_texts[:3])

    if not claimed_numbers or not evidence_numbers:
        return {
            "verdict": "UNVERIFIED",
            "evidence": evidence_summary,
        }

    if is_percentage:
        lo_mult, hi_mult = 0.7, 1.43
    else:
        lo_mult, hi_mult = 0.5, 2.0

    claimed_n = claimed_numbers[0]
    matches = [n for n in evidence_numbers if lo_mult * n <= claimed_n <= hi_mult * n]

    if matches:
        return {
            "verdict": "CONFIRMED",
            "evidence": evidence_summary,
        }
    else:
        closest = min(evidence_numbers, key=lambda n: abs(n - claimed_n))
        return {
            "verdict": "DISPUTED",
            "evidence": evidence_summary,
            "corrected_value": str(closest),
        }


def _extract_numbers(text: str) -> list[float]:
    """Extract numerical values from text, handling $, B, M, T, % suffixes."""
    numbers = []

    patterns = [
        (r'\$(\d+(?:\.\d+)?)\s*[Tt](?:rillion)?', 1e12),
        (r'\$(\d+(?:\.\d+)?)\s*[Bb](?:illion)?', 1e9),
        (r'\$(\d+(?:\.\d+)?)\s*[Mm](?:illion)?', 1e6),
        (r'(\d+(?:\.\d+)?)\s*[Tt](?:rillion)?', 1e12),
        (r'(\d+(?:\.\d+)?)\s*[Bb](?:illion)?', 1e9),
        (r'(\d+(?:\.\d+)?)\s*[Mm](?:illion)?', 1e6),
        (r'(\d+(?:\.\d+)?)\s*%', 1),
    ]

    for pattern, multiplier in patterns:
        for match in re.finditer(pattern, text):
            try:
                val = float(match.group(1))
                if multiplier > 1:
                    numbers.append(val * multiplier)
                else:
                    numbers.append(val)
            except ValueError:
                pass

    return numbers


def _validate_computed_claims(verified_claims: list[dict]) -> list[dict]:
    """Post-process verified claims to catch math errors in computed metrics."""
    all_numbers = {}
    for vc in verified_claims:
        claim = vc.get("claim", "").lower()
        value = vc.get("value", "")
        nums = _extract_numbers(value)
        if nums:
            all_numbers[claim] = nums[0]

    for vc in verified_claims:
        claim = vc.get("claim", "").lower()
        value = vc.get("value", "").lower()

        if "cagr" in claim or "cagr" in value:
            cagr_nums = _extract_numbers(value)
            if not cagr_nums:
                continue
            stated_cagr = cagr_nums[0]

            for other_claim, other_val in all_numbers.items():
                is_decline = any(w in other_claim for w in ["decline", "drop", "fall", "contraction", "shrink"])
                is_growth = any(w in other_claim for w in ["growth", "increase", "rise", "grew"])

                if is_decline or is_growth:
                    annual_rate = -other_val if is_decline else other_val
                    if abs(stated_cagr) > 0 and abs(annual_rate) > 0:
                        ratio = abs(stated_cagr) / abs(annual_rate)
                        if ratio < 0.6 or ratio > 1.7:
                            vc["verdict"] = "DISPUTED"
                            vc["evidence"] = (
                                f"Math inconsistency: stated CAGR of {stated_cagr}% "
                                f"conflicts with annual change of {annual_rate}%. "
                                f"Over a 1-year period, CAGR should equal the annual rate."
                            )
                            vc["corrected_value"] = f"{annual_rate}%"
                            logger.info(f"[Layer 2] Math validation caught CAGR error: "
                                        f"{stated_cagr}% vs annual {annual_rate}%")
                            break

        if any(w in value for w in ["over ", "above ", "more than ", "exceed"]):
            boundary_nums = _extract_numbers(value)
            if boundary_nums and "%" in value:
                boundary = boundary_nums[0]
                evidence = vc.get("evidence", "")
                evidence_nums = _extract_numbers(evidence)
                for en in evidence_nums:
                    if en < boundary and en > boundary * 0.9:
                        vc["verdict"] = "DISPUTED"
                        vc["evidence"] += f" | Boundary check: stated 'over {boundary}%' but evidence shows {en}%"
                        vc["corrected_value"] = f"{en}%"
                        logger.info(f"[Layer 2] Boundary check: 'over {boundary}%' vs actual {en}%")
                        break

    return verified_claims


def _build_verification_context(verified_claims: list[dict]) -> str:
    """Format verification results for the synthesis LLM."""
    if not verified_claims:
        return "No claims were extracted for verification."

    parts = []
    for vc in verified_claims:
        verdict = vc.get("verdict", "UNVERIFIED")
        line = f"[{verdict}] {vc.get('claim', '')}: {vc.get('value', '')}"
        if verdict == "DISPUTED" and vc.get("corrected_value"):
            line += f" → Evidence suggests: {vc['corrected_value']}"
        if vc.get("evidence"):
            line += f"\n  Evidence: {vc['evidence'][:200]}"
        parts.append(line)

    return "\n\n".join(parts)


def _build_additional_context(sources: list[Source], max_chars: int = 8000) -> str:
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


def _infer_publisher(url: str) -> str:
    """Extract publisher name from URL domain."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        host = host.replace("www.", "")
        return host.split(".")[0].capitalize() if host else "Unknown"
    except Exception:
        return "Unknown"


# ─── Search and verification helpers ──────────────────────────────────────────


async def _search_and_gather(queries: list[str], scrape_top: int = 3) -> list[Source]:
    """Execute searches and gather results with optional scraping."""
    all_sources: list[Source] = []
    urls_seen: set[str] = set()

    for query in queries:
        try:
            results = await search(query, max_results=5, include_news=False)
        except Exception as e:
            logger.warning(f"[Layer 2] Search failed for '{query}': {e}")
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


async def _verify_claims_batch(
    claims: list[dict],
    existing_sources: list[Source],
) -> tuple[list[dict], list[Source]]:
    """Search for verification evidence for each claim and assign verdicts."""
    verified_claims = []
    new_sources: list[Source] = []
    existing_urls = {s.url for s in existing_sources}

    for claim_info in claims:
        query = claim_info.get("search_query", "")
        claimed_value = claim_info.get("value", "")
        if not query:
            continue

        try:
            results = await search(query, max_results=3, include_news=False)
        except Exception as e:
            logger.warning(f"[Layer 2] Verification search failed for '{query}': {e}")
            verified_claims.append({
                **claim_info,
                "verdict": "UNVERIFIED",
                "evidence": "Search failed",
            })
            continue

        evidence_snippets = []
        for r in results:
            url = r.get("url", "")
            snippet = r.get("snippet", "")
            title = r.get("title", "")
            if not url:
                continue

            if url not in existing_urls:
                existing_urls.add(url)
                new_sources.append(Source(
                    url=url,
                    title=title,
                    snippet=snippet,
                    publisher=_infer_publisher(url),
                    date=r.get("date", ""),
                    tier=get_source_tier(url),
                ))

            evidence_snippets.append({
                "snippet": snippet[:300],
                "tier": get_source_tier(url),
                "source": title,
            })

        verdict = _build_claim_verdict(claimed_value, evidence_snippets)
        verified_claims.append({
            **claim_info,
            "verdict": verdict["verdict"],
            "evidence": verdict["evidence"],
            "corrected_value": verdict.get("corrected_value", ""),
        })

    return verified_claims, new_sources


# ─── State shared across agent loop iterations ───────────────────────────────

_l2_layer1_content: str = ""
_l2_critical_reading: dict = {}
_l2_verified_claims: list[dict] = []
_l2_verification_context: str = ""


# ─── Agent loop callbacks ────────────────────────────────────────────────────


async def _l2_plan(topic: str, context: str) -> dict:
    """Critical read of Layer 1, then plan targeted research tasks."""
    llm_analyst = get_llm("analyst")
    llm_planner = get_llm("planner")

    # Step 1: Critical reading of Layer 1
    messages = [
        {"role": "system", "content": "You are a senior market analyst. Return valid JSON only."},
        {"role": "user", "content": LAYER2_CRITICAL_READ.format(
            topic=topic,
            layer1_content=_l2_layer1_content[:4000],
        )},
    ]

    try:
        response = llm_analyst.invoke(messages)
        track("L2 critical read", response)
        critical = extract_json(response.content.strip())
        if isinstance(critical, dict):
            _l2_critical_reading.clear()
            _l2_critical_reading.update(critical)
    except Exception as e:
        logger.warning(f"[Layer 2] Critical reading failed: {e}")
        _l2_critical_reading.clear()

    # Step 2: Extract claims for verification
    llm_cheap = get_llm("researcher")
    claim_messages = [
        {"role": "system", "content": "You extract verifiable factual claims from research reports."},
        {"role": "user", "content": LAYER2_CLAIM_EXTRACTION.format(
            layer1_content=_l2_layer1_content[:4000],
        )},
    ]

    claims = []
    try:
        response = llm_cheap.invoke(claim_messages)
        track("L2 claim extract", response)
        claims = extract_json(response.content.strip())
        if not isinstance(claims, list):
            claims = []
        claims = claims[:10]
    except Exception as e:
        logger.warning(f"[Layer 2] Claim extraction failed: {e}")

    # Step 3: Build research plan from critical reading
    critical_str = json.dumps(_l2_critical_reading, indent=2) if _l2_critical_reading else "No critical reading available."
    plan_messages = [
        {"role": "system", "content": "You are a research planner. Return valid JSON only."},
        {"role": "user", "content": LAYER2_RESEARCH_PLAN.format(
            topic=topic,
            critical_reading=critical_str,
        )},
    ]

    queries = []
    try:
        response = llm_planner.invoke(plan_messages)
        track("L2 research plan", response)
        plan = extract_json(response.content.strip())
        if isinstance(plan, dict) and "research_tasks" in plan:
            for task in plan["research_tasks"]:
                q = task.get("query", "")
                if q:
                    queries.append(q)
    except Exception as e:
        logger.warning(f"[Layer 2] Research planning failed: {e}")

    # Add verification queries from claim extraction
    for claim in claims:
        q = claim.get("search_query", "")
        if q and q not in queries:
            queries.append(q)

    # Store claims for later verification in _l2_research
    _l2_verified_claims.clear()
    _l2_verified_claims.extend(claims)

    problem_count = (
        len(_l2_critical_reading.get("weak_claims", [])) +
        len(_l2_critical_reading.get("missing_dimensions", [])) +
        len(_l2_critical_reading.get("implausible_data", []))
    )
    logger.info(f"[Layer 2] Plan: {problem_count} problems found, "
                f"{len(claims)} claims to verify, {len(queries)} queries")

    return {"queries": queries}


async def _l2_research(queries: list[str], existing_sources: list[Source]) -> tuple[list[Source], str]:
    """Execute searches, verify claims, gather sources, build context."""
    existing_urls = {s.url for s in existing_sources}

    # Run targeted searches from the plan
    new_sources = await _search_and_gather(queries, scrape_top=5)
    truly_new = [s for s in new_sources if s.url not in existing_urls]

    # Verify claims extracted from Layer 1
    if _l2_verified_claims:
        verified, verification_sources = await _verify_claims_batch(
            _l2_verified_claims,
            existing_sources + truly_new,
        )
        # Post-process for math errors
        verified = _validate_computed_claims(verified)

        # Deduplicate verification sources
        for vs in verification_sources:
            if vs.url not in existing_urls and vs.url not in {s.url for s in truly_new}:
                truly_new.append(vs)

        # Store verification context for the draft
        global _l2_verification_context
        _l2_verification_context = _build_verification_context(verified)

        confirmed = sum(1 for c in verified if c.get("verdict") == "CONFIRMED")
        disputed = sum(1 for c in verified if c.get("verdict") == "DISPUTED")
        unverified = len(verified) - confirmed - disputed
        logger.info(f"[Layer 2] Verification: {confirmed} confirmed, {disputed} disputed, "
                    f"{unverified} unverified")

    # Build combined context from all new sources
    all_for_context = existing_sources + truly_new
    context = _build_additional_context(all_for_context)
    logger.info(f"[Layer 2] Research: {len(truly_new)} new sources")

    return truly_new, context


async def _l2_draft(topic: str, context: str, previous_draft: str) -> str:
    """Write or refine the analytical report."""
    llm = get_llm("analyst")

    if not previous_draft:
        # First draft — use existing synthesis prompt
        messages = [
            {"role": "system", "content": LAYER2_SYSTEM},
            {"role": "user", "content": LAYER2_USER.format(
                topic=topic,
                layer1_content=_l2_layer1_content,
                additional_research=context if context else "No additional research data.",
                verification_results=_l2_verification_context if _l2_verification_context else "No verification results.",
            )},
        ]
    else:
        # Refinement — use refine prompt
        messages = [
            {"role": "system", "content": LAYER2_SYSTEM},
            {"role": "user", "content": LAYER2_REFINE.format(
                topic=topic,
                draft=previous_draft,
                weaknesses="See the additional research data for areas that need improvement.",
                new_context=context,
                layer1_content=_l2_layer1_content[:2000],
            )},
        ]

    try:
        response = llm.invoke(messages)
        track("L2 draft" if not previous_draft else "L2 refine", response)
        return response.content.strip()
    except Exception as e:
        logger.error(f"[Layer 2] Draft failed: {e}")
        return previous_draft or f"Error: {e}"


async def _l2_evaluate(draft: str, topic: str) -> EvalResult:
    """Self-review the analysis for rigor and completeness."""
    llm = get_llm("reviewer")

    messages = [
        {"role": "system", "content": "You are a demanding research director. Return valid JSON only."},
        {"role": "user", "content": LAYER2_SELF_REVIEW.format(topic=topic, draft=draft)},
    ]

    try:
        response = llm.invoke(messages)
        track("L2 self-review", response)
        result = extract_json(response.content.strip())

        if isinstance(result, dict):
            return EvalResult(
                overall_score=float(result.get("overall", 5.0)),
                dimension_scores=result.get("scores", {}),
                weaknesses=result.get("weaknesses", []),
                suggested_queries=result.get("suggested_queries", []),
            )
    except Exception as e:
        logger.warning(f"[Layer 2] Self-review failed: {e}")

    return EvalResult(overall_score=5.0, weaknesses=["Self-review failed"], suggested_queries=[])


# ─── Main entry point ────────────────────────────────────────────────────────


async def run(topic: str, layer1_result: ResearchResult, progress_callback=None) -> ResearchResult:
    """Run Layer 2: agentic analysis with critical reading, verification, and self-evaluation."""
    logger.info(f"[Layer 2] Analysis agent starting for: {topic}")
    start = time.time()

    # Store Layer 1 content for callbacks to access
    global _l2_layer1_content, _l2_critical_reading, _l2_verified_claims, _l2_verification_context
    _l2_layer1_content = layer1_result.content
    _l2_critical_reading = {}
    _l2_verified_claims = []
    _l2_verification_context = ""

    draft, sources, iterations = await run_agent_loop(
        topic=topic,
        layer=2,
        plan_fn=_l2_plan,
        research_fn=_l2_research,
        draft_fn=_l2_draft,
        evaluate_fn=_l2_evaluate,
        max_iterations=3,
        convergence_threshold=7.5,
        existing_sources=list(layer1_result.sources),
        progress_callback=progress_callback,
    )

    elapsed = time.time() - start
    final_score = iterations[-1].eval_score if iterations else 0
    logger.info(f"[Layer 2] Done in {elapsed:.1f}s — {len(draft.split())} words, "
                f"{len(sources)} sources, {len(iterations)} iterations, "
                f"final score: {final_score:.1f}/10")

    return ResearchResult(
        layer=2,
        topic=topic,
        content=draft,
        sources=sources,
        metadata={
            "method": "agentic_analysis",
            "iterations": len(iterations),
            "final_score": final_score,
            "iteration_history": [
                {"iteration": it.iteration, "score": it.eval_score,
                 "weaknesses": it.weaknesses}
                for it in iterations
            ],
            "critical_reading": {
                "weak_claims": len(_l2_critical_reading.get("weak_claims", [])),
                "logical_gaps": len(_l2_critical_reading.get("logical_gaps", [])),
                "missing_dimensions": len(_l2_critical_reading.get("missing_dimensions", [])),
                "implausible_data": len(_l2_critical_reading.get("implausible_data", [])),
            },
            "sources_found": len(sources),
            "sources_scraped": sum(1 for s in sources if s.scraped_content),
        },
        elapsed_seconds=elapsed,
    )
