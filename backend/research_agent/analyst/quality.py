"""
Phase 4: QUALITY GATE — Score the research and decide if it's good enough.

Pure Python scoring + optional LLM review.
"""

import logging

from config import get_llm, set_model_tier
from research_agent.analyst.models import QualityScore, ResearchBoard, AnalysisResult
from research_agent.analyst.prompts import QUALITY_GATE_PROMPT
from research_agent.cost import track
from research_agent.utils import get_content, extract_json

logger = logging.getLogger(__name__)

# Minimum evidence pieces expected per answer_type.
# "comparison" and "list" questions need MORE evidence than "numeric" or "opinion"
# because they inherently cover multiple entities/items.
MIN_EVIDENCE_PER_TYPE = {
    "numeric": 1,       # one good data point is enough
    "trend": 2,         # need at least before + after or multiple time points
    "comparison": 3,    # comparing entities means evidence per entity
    "list": 3,          # listing things means multiple items
    "causal": 2,        # need cause + effect evidence
    "opinion": 1,       # expert opinion can be singular
    "general": 2,       # default
}


def score_research(board: ResearchBoard, analysis: AnalysisResult) -> QualityScore:
    """Score research quality using deterministic rules (no LLM needed)."""

    total_sq = len(board.framework.sub_questions)
    if total_sq == 0:
        return QualityScore(overall=0.0, passes=False, feedback="No sub-questions found.")

    # Hard fail: zero evidence means research didn't happen
    if not board.evidence:
        return QualityScore(
            overall=0.0,
            passes=False,
            feedback="No evidence collected. Investigation may have failed entirely.",
            remediation_queries=[q for sq in board.framework.sub_questions
                                 for q in sq.search_queries[:1]][:5],
        )

    # 1. Coverage (25%): % of sub-questions truly answered (not gaps), weighted by priority
    p1_total = sum(1 for sq in board.framework.sub_questions if sq.priority == 1)
    p1_answered = sum(1 for sq in board.framework.sub_questions if sq.priority == 1 and sq.is_answered)
    p2_answered = sum(1 for sq in board.framework.sub_questions if sq.priority == 2 and sq.is_answered)
    p2_total = sum(1 for sq in board.framework.sub_questions if sq.priority == 2)

    # P1 coverage matters most
    p1_cov = p1_answered / p1_total if p1_total else 1.0
    p2_cov = p2_answered / p2_total if p2_total else 1.0
    coverage = p1_cov * 0.6 + p2_cov * 0.3 + board.coverage * 0.1

    # 2. Evidence strength (20%): prefer T1/T2 sources
    if board.evidence:
        t1_t2 = sum(1 for e in board.evidence if e.source_tier <= 2)
        evidence_strength = t1_t2 / len(board.evidence)
    else:
        evidence_strength = 0.0

    # 3. Evidence depth (20%): do answered questions have ENOUGH evidence for their type?
    #    A "comparison" question answered with 1 data point is shallow.
    #    A "numeric" question answered with 1 data point is fine.
    depth_scores = []
    shallow_questions = []
    for sq in board.framework.sub_questions:
        if not sq.is_answered:
            continue
        ev_count = len(board.evidence_for(sq.id))
        min_expected = MIN_EVIDENCE_PER_TYPE.get(sq.answer_type, 2)
        # Score: 1.0 if at or above minimum, proportional below
        if min_expected > 0:
            depth = min(ev_count / min_expected, 1.0)
        else:
            depth = 1.0
        depth_scores.append(depth)
        if depth < 0.5:
            shallow_questions.append(sq)

    evidence_depth = sum(depth_scores) / len(depth_scores) if depth_scores else 0.0

    # 4. Contradiction resolution (10%)
    total_ct = len(board.contradictions)
    resolved_ct = sum(1 for c in board.contradictions if c.resolved)
    contradiction_resolution = resolved_ct / total_ct if total_ct else 1.0

    # 5. Judgment formation (15%)
    has_judgments = min(len(board.judgments) / 3, 1.0)  # Want at least 3 judgments
    judgment_formation = has_judgments

    # 6. Gap acknowledgment (10%)
    # Good if unanswered questions are explicitly marked "gap" rather than left "pending"
    gaps = sum(1 for sq in board.framework.sub_questions if sq.status == "gap")
    unanswered = sum(1 for sq in board.framework.sub_questions if sq.status in ("pending", "researching"))
    if gaps + unanswered > 0:
        gap_acknowledgment = gaps / (gaps + unanswered)
    else:
        gap_acknowledgment = 1.0
    # Penalize if most questions are gaps (acknowledged but still not researched)
    if gaps > 0 and p1_answered + p2_answered == 0:
        gap_acknowledgment *= 0.3  # Marking everything as "gap" isn't quality

    # Weighted overall
    overall = (
        coverage * 0.25 +
        evidence_strength * 0.20 +
        evidence_depth * 0.20 +
        contradiction_resolution * 0.10 +
        judgment_formation * 0.15 +
        gap_acknowledgment * 0.10
    )

    # Determine pass/fail
    threshold = 0.55 if board.iteration_count > 0 else 0.65
    passes = overall >= threshold

    # Build feedback
    feedback_parts = []
    if coverage < 0.7:
        feedback_parts.append(f"Coverage is low ({coverage:.0%}). P1 gaps remain.")
    if evidence_strength < 0.5:
        feedback_parts.append(f"Too many T3 sources ({evidence_strength:.0%} T1/T2). Scrape better sources.")
    if evidence_depth < 0.6:
        shallow_labels = [f"{sq.id} ({sq.answer_type})" for sq in shallow_questions[:3]]
        feedback_parts.append(
            f"Evidence is too shallow ({evidence_depth:.0%} depth). "
            f"These questions need more data points: {', '.join(shallow_labels)}. "
            f"Comparison/list questions need 3+ evidence pieces each."
        )
    if contradiction_resolution < 0.5 and total_ct > 0:
        feedback_parts.append(f"Unresolved contradictions ({total_ct - resolved_ct} remaining).")
    if judgment_formation < 0.5:
        feedback_parts.append("Too few analyst judgments formed. Need opinions, not just facts.")
    feedback = " ".join(feedback_parts) if feedback_parts else "Research quality is satisfactory."

    # Remediation queries — prioritize shallow questions, then gaps
    remediation = []
    if not passes:
        # First: re-search shallow answered questions that need more evidence
        for sq in shallow_questions:
            for q in sq.search_queries[:1]:
                remediation.append(q)
            if len(remediation) >= 3:
                break
        # Then: fill remaining gaps
        for sq in board.framework.pending_questions(priority=1):
            for q in sq.search_queries[:1]:
                remediation.append(q)
        for sq in board.framework.pending_questions(priority=2):
            for q in sq.search_queries[:1]:
                remediation.append(q)
            if len(remediation) >= 5:
                break

    score = QualityScore(
        coverage=coverage,
        evidence_strength=evidence_strength,
        evidence_depth=evidence_depth,
        contradiction_resolution=contradiction_resolution,
        judgment_formation=judgment_formation,
        gap_acknowledgment=gap_acknowledgment,
        overall=overall,
        passes=passes,
        feedback=feedback,
        remediation_queries=remediation,
    )

    logger.info(
        f"[Analyst] Quality: {overall:.2f} ({'PASS' if passes else 'FAIL'}) — "
        f"cov={coverage:.2f} str={evidence_strength:.2f} depth={evidence_depth:.2f} "
        f"ct={contradiction_resolution:.2f} jdg={judgment_formation:.2f} gap={gap_acknowledgment:.2f}"
    )

    return score
