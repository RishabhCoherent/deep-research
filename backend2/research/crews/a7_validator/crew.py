"""CrewAI crew orchestration for Agent 7 - Validator / Relevancy."""

from __future__ import annotations

import json
import structlog

from crewai import Crew, Process

from research.core.types import ConsolidatedReport, NumericClaim, Conflict
from research.core.errors import CrewFailure

from .agents import build_agents
from .tasks import build_tasks
from .schemas import RankedClaims, CrossCheckResult, RecencyResult, ValidationResult, A7Output
from .crosscheck import group_claims, resolve_all, max_pct_diff_group
from .validators import assert_all_conflicts_resolved

log = structlog.get_logger(__name__)


def build_a7_crew():
    ranker, checker, judge, resolver = build_agents()
    t_rank, t_cross, t_recency, t_resolve = build_tasks(ranker, checker, judge, resolver)
    return Crew(
        agents=[ranker, checker, judge, resolver],
        tasks=[t_rank, t_cross, t_recency, t_resolve],
        process=Process.sequential,
        verbose=False,
        memory=False,
    )


async def run_a7(*, consolidated: ConsolidatedReport) -> A7Output:
    """Run Agent 7 - Validator. No Tavily calls. Only assess_source tool for 7a.

    Uses a hybrid approach:
    - Pre-computes groupings + % diffs deterministically before LLM
    - LLMs handle semantic equivalence + rejection reason generation
    - Post-validates: deterministic authority code overrides any LLM deviation
    """
    claims = consolidated.claims
    if not claims:
        log.warning("a7_validator.no_claims")
        return A7Output(validated_claims=[], conflicts=[])

    # ── Pre-compute (deterministic) ─────────────────────────────────────
    unanimous_pre, candidates_pre = group_claims(claims)
    original_groups = {}
    for c in candidates_pre:
        key = (c.metric, c.scope or "")
        original_groups[key] = c.claims

    claims_json = json.dumps([c.model_dump() for c in claims], default=str)
    candidates_json = json.dumps([c.model_dump() for c in candidates_pre], default=str)
    unanimous_json = json.dumps([c.model_dump() for c in unanimous_pre], default=str)

    crew = build_a7_crew()
    try:
        result = await crew.kickoff_async(
            inputs={
                "claims_json":        claims_json,
                "ranked_claims_json": claims_json,   # pre-filled for 7b
                "candidates_json":    candidates_json,
                "unanimous_json":     unanimous_json,
            }
        )
    except Exception as exc:
        log.warning("a7_validator.kickoff_failed_using_deterministic_fallback",
                    error=str(exc)[:200])
        validated_det, conflicts_det = resolve_all(unanimous_pre, candidates_pre)
        return A7Output(validated_claims=validated_det, conflicts=conflicts_det)

    ranked: RankedClaims          = result.tasks_output[0].pydantic
    crossed: CrossCheckResult     = result.tasks_output[1].pydantic
    recency: RecencyResult        = result.tasks_output[2].pydantic
    resolved: ValidationResult    = result.tasks_output[3].pydantic

    if any(x is None for x in [ranked, crossed, recency, resolved]):
        log.warning("a7_validator.llm_parse_failed_using_deterministic_fallback")
        validated_det, conflicts_det = resolve_all(unanimous_pre, candidates_pre)
        return A7Output(validated_claims=validated_det, conflicts=conflicts_det)

    # ── Post-validate: deterministic fallback enforces authority hierarchy ──
    try:
        assert_all_conflicts_resolved(resolved.validated_claims, resolved.conflicts)
    except AssertionError as exc:
        log.warning("a7_validator.conflict_assertion_failed", error=str(exc))

    # Re-resolve deterministically and compare; override if LLM deviated
    validated_det, conflicts_det = resolve_all(unanimous_pre, candidates_pre)

    # Merge: use LLM conflicts (for richer rejection reasons) but use
    # code-computed winners (authority-correct) for validated_claims
    final_validated = validated_det
    final_conflicts = resolved.conflicts if resolved.conflicts else conflicts_det

    log.info("a7_validator.done",
             input_claims=len(claims),
             validated=len(final_validated),
             conflicts=len(final_conflicts))

    return A7Output(
        validated_claims=final_validated,
        conflicts=final_conflicts,
    )
