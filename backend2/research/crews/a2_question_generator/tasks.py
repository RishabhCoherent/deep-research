"""CrewAI tasks for Agent 2 - Question Generator."""

from crewai import Task
from .schemas import DecomposedQuestions, GappedQuestions, PrioritizedQuestions


def build_tasks(dec, gap, pri):
    """Build the three sequential tasks for Agent 2."""

    t_decompose = Task(
        description=(
            "Decompose the chosen query into atomic sub-questions. "
            "chosen_query={chosen_query}, intent={intent}, "
            "original_query={original_query}"
        ),
        expected_output="JSON matching DecomposedQuestions (10-18 items, source=decomposer).",
        agent=dec,
        output_pydantic=DecomposedQuestions,
    )

    t_gap = Task(
        description=(
            "Fill any checklist gaps for intent={intent}. "
            "Keep all existing items and add gap_fill items for missing must-have categories. "
            "chosen_query={chosen_query}"
        ),
        expected_output="JSON matching GappedQuestions (all original items + gap_fill additions).",
        agent=gap,
        context=[t_decompose],
        output_pydantic=GappedQuestions,
    )

    t_prioritize = Task(
        description=(
            "Score each question on info_value and answerability, "
            "deduplicate near-duplicates, sort desc by composite, "
            "truncate to 8-15 items. chosen_query={chosen_query}"
        ),
        expected_output="JSON matching PrioritizedQuestions (8-15 items, sorted desc by composite).",
        agent=pri,
        context=[t_gap],
        output_pydantic=PrioritizedQuestions,
    )

    return t_decompose, t_gap, t_prioritize
