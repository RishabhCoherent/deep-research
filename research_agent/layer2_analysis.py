"""
Layer 2 — Analysis Agent (ReAct): autonomous tool-calling agent with claim verification.

Critically reads Layer 1 output, verifies key claims through targeted research,
fills data gaps, and produces deeper analytical synthesis. Has access to a
verify_claim tool that performs deterministic numerical comparison.
"""

from __future__ import annotations

import logging
import re
import time

from langchain_core.tools import tool

from config import get_llm
from tools.search import search
from tools.source_classifier import get_source_tier
from research_agent.types import ResearchResult, Source
from research_agent.prompts import LAYER2_AGENT_SYSTEM, LAYER2_SELF_REVIEW
from research_agent.agent_loop import (
    run_react_agent, AgentContext, _infer_publisher,
)

logger = logging.getLogger(__name__)


# ─── Deterministic verification helpers ──────────────────────────────────────


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
                numbers.append(val * multiplier if multiplier > 1 else val)
            except ValueError:
                pass
    return numbers


def _build_claim_verdict(claimed_value: str, evidence: list[dict]) -> dict:
    """Heuristic verdict: compare claimed value against search evidence.

    Uses tighter tolerance for percentages (30%) vs absolute numbers (50%)
    because percentage errors are more impactful.
    """
    if not evidence:
        return {"verdict": "UNVERIFIED", "evidence": "No evidence found"}

    claimed_numbers = _extract_numbers(claimed_value)
    is_percentage = "%" in claimed_value

    evidence_numbers = []
    evidence_texts = []
    for e in sorted(evidence, key=lambda x: x.get("tier", 3)):
        snippet = e.get("snippet", "")
        evidence_texts.append(f"[T{e.get('tier', 3)}] {e.get('source', '')}: {snippet}")
        evidence_numbers.extend(_extract_numbers(snippet))

    evidence_summary = " | ".join(evidence_texts[:3])

    if not claimed_numbers or not evidence_numbers:
        return {"verdict": "UNVERIFIED", "evidence": evidence_summary}

    lo, hi = (0.7, 1.43) if is_percentage else (0.5, 2.0)
    claimed_n = claimed_numbers[0]
    matches = [n for n in evidence_numbers if lo * n <= claimed_n <= hi * n]

    if matches:
        return {"verdict": "CONFIRMED", "evidence": evidence_summary}
    else:
        closest = min(evidence_numbers, key=lambda n: abs(n - claimed_n))
        return {
            "verdict": "DISPUTED",
            "evidence": evidence_summary,
            "corrected_value": str(closest),
        }


# ─── L2-specific tool factory ───────────────────────────────────────────────


def make_l2_tools(ctx: AgentContext) -> list:
    """Create the verify_claim tool for Layer 2."""

    @tool
    async def verify_claim(claim: str, claimed_value: str, search_query: str) -> str:
        """Verify a specific factual claim by searching for evidence and comparing
        values deterministically. Use this to fact-check market sizes, growth rates,
        market shares, and other numerical claims from the prior analysis."""
        if ctx.tool_call_count >= ctx.max_tool_calls:
            return "BUDGET EXCEEDED. Write your report now."
        ctx.tool_call_count += 1

        try:
            results = await search(search_query, max_results=3, include_news=False)
        except Exception as e:
            return f"Verification search failed: {e}"

        evidence = []
        for r in results:
            url = r.get("url", "")
            snippet = r.get("snippet", "")
            if not url:
                continue

            if url not in ctx.urls_seen:
                ctx.urls_seen.add(url)
                ctx.sources.append(Source(
                    url=url, title=r.get("title", ""),
                    snippet=snippet, publisher=_infer_publisher(url),
                    date=r.get("date", ""), tier=get_source_tier(url),
                ))

            evidence.append({
                "snippet": snippet[:300],
                "tier": get_source_tier(url),
                "source": r.get("title", ""),
            })

        verdict = _build_claim_verdict(claimed_value, evidence)
        ctx.tool_calls_log.append({
            "tool": "verify_claim", "claim": claim,
            "verdict": verdict["verdict"],
        })

        output = f"Claim: {claim} = {claimed_value}\nVerdict: {verdict['verdict']}"
        if verdict.get("corrected_value"):
            output += f"\nEvidence suggests: {verdict['corrected_value']}"
        output += f"\nEvidence: {verdict.get('evidence', 'none')[:300]}"
        return output

    return [verify_claim]


# ─── Main entry point ────────────────────────────────────────────────────────


async def run(topic: str, layer1_result: ResearchResult, progress_callback=None) -> ResearchResult:
    """Run Layer 2: ReAct analysis agent with claim verification."""
    logger.info(f"[Layer 2] ReAct analysis agent starting for: {topic}")
    start = time.time()

    ctx = AgentContext(
        max_tool_calls=20,
        prior_content=layer1_result.content,
        existing_sources=list(layer1_result.sources),
    )
    # Pre-populate with L1 sources
    ctx.sources = list(layer1_result.sources)
    ctx.urls_seen = {s.url for s in layer1_result.sources}

    llm = get_llm("analyst")
    eval_llm = get_llm("reviewer")

    draft, sources, iterations = await run_react_agent(
        topic=topic,
        layer=2,
        system_prompt=LAYER2_AGENT_SYSTEM,
        llm=llm,
        ctx=ctx,
        eval_prompt_template=LAYER2_SELF_REVIEW,
        eval_llm=eval_llm,
        max_iterations=3,
        convergence_threshold=7.5,
        extra_tools=make_l2_tools(ctx),
        progress_callback=progress_callback,
    )

    elapsed = time.time() - start
    final_score = iterations[-1].eval_score if iterations else 0
    total_tool_calls = len(ctx.tool_calls_log)
    verifications = [l for l in ctx.tool_calls_log if l.get("tool") == "verify_claim"]

    logger.info(f"[Layer 2] Done in {elapsed:.1f}s — {len(draft.split())} words, "
                f"{len(sources)} sources, {len(iterations)} iters, "
                f"{total_tool_calls} tool calls, {len(verifications)} verifications, "
                f"score: {final_score:.1f}/10")

    return ResearchResult(
        layer=2,
        topic=topic,
        content=draft,
        sources=sources,
        metadata={
            "method": "react_agent",
            "iterations": len(iterations),
            "final_score": final_score,
            "tool_calls": total_tool_calls,
            "verifications": len(verifications),
            "iteration_history": [
                {"iteration": it.iteration, "score": it.eval_score,
                 "weaknesses": it.weaknesses, "queries": it.queries_run}
                for it in iterations
            ],
            "sources_found": len(sources),
            "sources_scraped": sum(1 for s in sources if s.scraped_content),
        },
        elapsed_seconds=elapsed,
    )
