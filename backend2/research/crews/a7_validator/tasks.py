"""CrewAI tasks for Agent 7 - Validator. Four sequential tasks."""

from crewai import Task
from .schemas import RankedClaims, CrossCheckResult, RecencyResult, ValidationResult


def build_tasks(ranker, checker, judge, resolver):
    """Build four sequential tasks for Agent 7."""

    t_rank = Task(
        description=(
            "Call assess_source(url) for each unique URL in the claims list. "
            "Confirm or upgrade authority_tier for each claim. "
            "claims_json={claims_json}"
        ),
        expected_output="JSON matching RankedClaims: {claims: [NumericClaim with confirmed authority_tier]}.",
        agent=ranker,
        output_pydantic=RankedClaims,
    )

    t_crosscheck = Task(
        description=(
            "Group ranked claims by (normalised metric, scope). "
            "Flag groups with ≥2 claims as ConflictCandidates. "
            "Compute max_diff_pct for each conflicted group. "
            "ranked_claims_json={ranked_claims_json}"
        ),
        expected_output="JSON matching CrossCheckResult: {unanimous: [...], conflicted: [ConflictCandidate, ...]}.",
        agent=checker,
        context=[t_rank],
        output_pydantic=CrossCheckResult,
    )

    t_recency = Task(
        description=(
            "For each ConflictCandidate, set recency_winner_idx to the index of the "
            "claim with the highest authority tier (recency as tiebreak for same-tier). "
            "candidates_json={candidates_json}"
        ),
        expected_output="JSON matching RecencyResult: {candidates: [ConflictCandidate with recency_winner_idx set]}.",
        agent=judge,
        context=[t_crosscheck],
        output_pydantic=RecencyResult,
    )

    t_resolve = Task(
        description=(
            "For each ConflictCandidate: pick winner by authority→recency; "
            "if top-2 finalists within 5% and same tier, emit range claim. "
            "Build Conflict audit trail with rejection reasons. "
            "unanimous_json={unanimous_json}, candidates_json={candidates_json}"
        ),
        expected_output=(
            "JSON matching ValidationResult: "
            "{validated_claims: [NumericClaim, ...], conflicts: [Conflict, ...]}."
        ),
        agent=resolver,
        context=[t_rank, t_crosscheck, t_recency],
        output_pydantic=ValidationResult,
    )

    return t_rank, t_crosscheck, t_recency, t_resolve
