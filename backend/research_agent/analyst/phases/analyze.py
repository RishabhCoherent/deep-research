"""
Phase 3: ANALYZE — Cross-reference findings, resolve contradictions, form judgments.

Single LLM call with reasoning model. Produces AnalysisResult.
"""

import logging

from config import get_llm, set_model_tier
from research_agent.analyst.models import (
    AnalysisResult, AnalystJudgment, CausalLink, ResearchBoard,
)
from research_agent.analyst.prompts import ANALYZE_PROMPT
from research_agent.cost import track
from research_agent.utils import get_content, extract_json, date_vars

logger = logging.getLogger(__name__)


async def analyze(board: ResearchBoard, topic: str, notify=None) -> AnalysisResult:
    """Cross-reference all evidence and form analyst judgments."""
    if notify:
        notify("analyze", "Cross-referencing findings and forming judgments...")

    # Build evidence summary
    evidence_lines = []
    for sq in board.framework.sub_questions:
        evidence_lines.append(f"\n### {sq.id}: {sq.question} (status: {sq.status})")
        sq_evidence = board.evidence_for(sq.id)
        if sq_evidence:
            for e in sq_evidence:
                tier_label = f"T{e.source_tier}"
                evidence_lines.append(f"  [{e.id}] [{tier_label}] {e.fact}")
                if e.source_title:
                    evidence_lines.append(f"    Source: {e.source_title} ({e.source_url})")
        else:
            evidence_lines.append("  (no evidence)")
    evidence_summary = "\n".join(evidence_lines)

    # Contradictions
    contradiction_lines = []
    for c in board.contradictions:
        status = "RESOLVED" if c.resolved else "UNRESOLVED"
        contradiction_lines.append(f"  [{c.id}] [{status}] {c.description}")
        if c.resolved:
            contradiction_lines.append(f"    Resolution: {c.resolution}")
    contradictions_text = "\n".join(contradiction_lines) if contradiction_lines else "None"

    # Question status
    status_lines = []
    for sq in board.framework.sub_questions:
        ev_count = len(board.evidence_for(sq.id))
        status_lines.append(
            f"  {sq.id} [P{sq.priority}] {sq.status} ({ev_count} evidence) — {sq.question}"
        )
    question_status = "\n".join(status_lines)

    set_model_tier("reasoning")
    llm = get_llm("analyst")

    messages = [
        {"role": "system", "content": "You output only valid JSON. No explanation, no markdown fences."},
        {"role": "user", "content": ANALYZE_PROMPT.format(
            topic=topic,
            evidence_summary=evidence_summary,
            contradictions=contradictions_text,
            question_status=question_status,
            **date_vars(),
        )},
    ]

    response = await llm.ainvoke(messages)
    track("analyst analyze", response)
    raw = get_content(response)
    data = extract_json(raw)

    if not data:
        logger.error("[Analyst] Analyze phase failed to parse")
        return AnalysisResult(overall_confidence=0.5, narrative_thread="Analysis unavailable.")

    # Build result
    result = AnalysisResult(
        key_findings=data.get("key_findings", []),
        overall_confidence=data.get("overall_confidence", 0.5),
        narrative_thread=data.get("narrative_thread", ""),
    )

    # Extract causal chains
    for chain in data.get("causal_chains", []):
        if isinstance(chain, str):
            result.causal_chains.append(chain)

    # Extract judgments
    for j_data in data.get("judgments", []):
        if not isinstance(j_data, dict):
            continue
        j = AnalystJudgment(
            claim=j_data.get("claim", ""),
            conviction=j_data.get("conviction", "medium"),
            supporting_evidence=j_data.get("supporting_evidence_ids", []),
            counter_evidence=j_data.get("counter_evidence_ids", []),
            reasoning=j_data.get("reasoning", ""),
            section=j_data.get("section", ""),
        )
        result.judgments.append(j)
        board.judgments.append(j)

    # Resolve contradictions from analysis
    for cr in data.get("contradiction_resolutions", []):
        if not isinstance(cr, dict):
            continue
        ct_id = cr.get("contradiction_id", "")
        for ct in board.contradictions:
            if ct.id == ct_id and not ct.resolved:
                ct.resolved = True
                ct.resolution = cr.get("resolution", "")
                ct.preferred_evidence_id = cr.get("preferred_evidence_id", "")
                ct.reasoning = cr.get("reasoning", "")

    # Record evidence gaps
    for gap in data.get("evidence_gaps", []):
        if isinstance(gap, dict):
            sq_id = gap.get("sq_id", "")
            severity = gap.get("severity", "acceptable")
            result.evidence_gaps.append(sq_id)
            result.gap_severity[sq_id] = severity

    # Extract original analytical frameworks
    sm = data.get("scoring_matrix")
    if isinstance(sm, dict):
        result.scoring_matrix = sm

    ms = data.get("market_segments")
    if isinstance(ms, list):
        result.market_segments = [s for s in ms if isinstance(s, dict)]

    rr = data.get("ranked_recommendations")
    if isinstance(rr, list):
        result.ranked_recommendations = [r for r in rr if isinstance(r, dict)]

    cf = data.get("conversion_framework")
    if isinstance(cf, dict):
        result.conversion_framework = cf

    ci = data.get("contrarian_insights")
    if isinstance(ci, list):
        result.contrarian_insights = [c for c in ci if isinstance(c, str)]

    logger.info(
        f"[Analyst] Analysis complete: {len(result.key_findings)} findings, "
        f"{len(result.judgments)} judgments, {len(result.causal_chains)} causal chains, "
        f"confidence: {result.overall_confidence:.0%}"
    )

    if notify:
        notify("analyze",
               f"Analysis complete: {len(result.judgments)} judgments formed, "
               f"confidence: {result.overall_confidence:.0%}")

    return result
