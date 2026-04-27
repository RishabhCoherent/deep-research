"""CrewAI tasks for Agent 8 - Causation. Two LLM tasks; 8c is pure Python."""

from crewai import Task
from .schemas import DeltaBundle, CorrelatedEvents


def build_tasks(detector, correlator):
    """Build two sequential LLM tasks. 8c (evidence_validator) is called outside crew."""

    t_deltas = Task(
        description=(
            "Identify validated claims that appear at two different dates. "
            "Compute delta_pct for each metric pair. "
            "Sort by abs(delta_pct) descending. "
            "validated_claims_json={validated_claims_json}, "
            "precomputed_deltas_json={precomputed_deltas_json}"
        ),
        expected_output="JSON matching DeltaBundle: {deltas: [Delta, ...]}.",
        agent=detector,
        output_pydantic=DeltaBundle,
    )

    t_correlate = Task(
        description=(
            "For each delta, read scratchpad sections 'news' and 'market_context' first. "
            "Then search for causal events within each delta's time window. "
            "Each Driver must have ≥2 citations from ≥2 independent domains. "
            "Hard cap: ≤5 total searches. "
            "chosen_query={chosen_query}, deltas_json={deltas_json}"
        ),
        expected_output=(
            "JSON matching CorrelatedEvents: "
            "{causations: [CausationDraft with candidate_drivers]}."
        ),
        agent=correlator,
        context=[t_deltas],
        output_pydantic=CorrelatedEvents,
    )

    return t_deltas, t_correlate
