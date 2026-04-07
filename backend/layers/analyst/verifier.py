"""
Phase 6: VERIFY — Check composed report claims against collected evidence.

Single LLM call with budget model. Produces VerificationResult with grounding score.
Non-destructive: does NOT edit the report, only scores it.
"""

import logging

from config import get_llm, set_model_tier
from models.analyst import ResearchBoard, VerificationResult
from prompts.analyst import VERIFY_PROMPT
from utils.cost_tracker import track
from utils import get_content, extract_json

logger = logging.getLogger(__name__)

# Max evidence items sent to verifier (keeps prompt within budget model limits)
_MAX_EVIDENCE = 100
# Max report words sent (covers all sections without token explosion)
_MAX_REPORT_WORDS = 8000


async def verify(draft: str, board: ResearchBoard, notify=None) -> VerificationResult:
    """Check how many factual claims in the report are traceable to evidence."""
    if notify:
        notify("verify", "Checking report claims against evidence...")

    # Build flat evidence list (id: fact (source))
    evidence_lines = []
    for e in board.evidence[:_MAX_EVIDENCE]:
        fact = e.fact[:200]
        src = f" (source: {e.source_title})" if e.source_title else ""
        evidence_lines.append(f"[{e.id}]: {fact}{src}")
    evidence_list = "\n".join(evidence_lines) if evidence_lines else "(no evidence collected)"

    # Truncate report to max words
    words = draft.split()
    if len(words) > _MAX_REPORT_WORDS:
        report_text = " ".join(words[:_MAX_REPORT_WORDS]) + "\n\n[... truncated ...]"
    else:
        report_text = draft

    set_model_tier("budget")
    llm = get_llm("analyst")

    messages = [
        {"role": "system", "content": "You output only valid JSON. No explanation, no markdown fences."},
        {"role": "user", "content": VERIFY_PROMPT.format(
            evidence_list=evidence_list,
            report_text=report_text,
        )},
    ]

    try:
        response = await llm.ainvoke(messages)
        track("analyst verify", response)
        raw = get_content(response)
        data = extract_json(raw)
    except Exception as e:
        logger.warning(f"[Analyst] Verify phase failed: {e}")
        return VerificationResult()

    if not data or "claims" not in data:
        logger.warning(f"[Analyst] Verify phase returned no claims. Raw length: {len(raw) if 'raw' in dir() else 0}")
        return VerificationResult()

    claims = data.get("claims", [])
    if not isinstance(claims, list):
        return VerificationResult()

    total = len(claims)
    verified_count = sum(1 for c in claims if isinstance(c, dict) and c.get("status") == "verified")
    unverified = [
        c.get("text", "")[:150]
        for c in claims
        if isinstance(c, dict) and c.get("status") == "fabricated"
    ]
    uncertain = [
        c.get("text", "")[:150]
        for c in claims
        if isinstance(c, dict) and c.get("status") == "uncertain"
    ]

    # Use LLM-computed score if available and reasonable, else compute from counts
    llm_score = data.get("grounding_score")
    if isinstance(llm_score, (int, float)) and 0.0 <= llm_score <= 1.0:
        grounding_score = float(llm_score)
    else:
        grounding_score = verified_count / total if total > 0 else 0.0

    result = VerificationResult(
        grounding_score=round(grounding_score, 3),
        total_claims=total,
        verified_claims=verified_count,
        unverified=unverified,
        uncertain=uncertain,
    )

    logger.info(
        f"[Analyst] Verification complete: {verified_count}/{total} claims verified, "
        f"grounding score: {grounding_score:.0%}, "
        f"{len(unverified)} fabricated, {len(uncertain)} uncertain"
    )

    if notify:
        notify("verify",
               f"Grounding check: {grounding_score:.0%} verified "
               f"({verified_count}/{total} claims, {len(unverified)} unverified)")

    return result
