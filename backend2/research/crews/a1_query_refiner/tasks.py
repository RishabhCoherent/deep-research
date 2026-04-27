"""CrewAI tasks for Agent 1 - Query Refiner."""

from crewai import Task
from .schemas import IntentClassification, VariantBundle, ScoredBundle


def build_tasks(ic, vg, cs):
    """Build the three sequential tasks for Agent 1."""
    
    t_intent = Task(
        description="Classify the raw query. Raw query: {raw_query}",
        expected_output="JSON matching IntentClassification.",
        agent=ic,
        output_pydantic=IntentClassification,
    )
    
    t_variants = Task(
        description=(
            "Using the intent and reasoning from the previous task's context, "
            "produce exactly 4 refined queries (one per angle). Raw query: {raw_query}"
        ),
        expected_output="JSON matching VariantBundle.",
        agent=vg,
        context=[t_intent],  # CrewAI passes prior output as context
        output_pydantic=VariantBundle,
    )
    
    t_scored = Task(
        description=(
            "Score each variant 0-10 on specificity, scope_clarity, answerability; "
            "composite = 0.4/0.3/0.3; sort desc. Raw query: {raw_query}"
        ),
        expected_output="JSON matching ScoredBundle (sorted desc).",
        agent=cs,
        context=[t_variants],
        output_pydantic=ScoredBundle,
    )
    
    return t_intent, t_variants, t_scored
