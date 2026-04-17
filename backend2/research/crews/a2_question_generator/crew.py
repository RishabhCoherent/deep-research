"""CrewAI crew orchestration for Agent 2 - Question Generator."""

from crewai import Crew, Process
from research.core.types import IntentKind
from research.core.errors import CrewFailure
from .agents import build_agents
from .tasks import build_tasks
from .schemas import A2Output, PrioritizedQuestions
from .validators import assert_checklist_coverage, missing_categories
from .dedupe import deduplicate


def build_a2_crew():
    """Build the CrewAI crew for Agent 2."""
    dec, gap, pri = build_agents()
    t_decompose, t_gap, t_prioritize = build_tasks(dec, gap, pri)

    return Crew(
        agents=[dec, gap, pri],
        tasks=[t_decompose, t_gap, t_prioritize],
        process=Process.sequential,
        verbose=False,
        memory=False,
    )


async def run_a2(
    *,
    chosen_query: str,
    intent: IntentKind,
    original_query: str,
) -> A2Output:
    """Run the Agent 2 crew. Fully autonomous — no user interaction.

    Returns A2Output containing 8-15 ranked sub-questions ready for Agents 3/4/5.
    """
    crew = build_a2_crew()

    result = await crew.kickoff_async(
        inputs={
            "chosen_query":   chosen_query,
            "intent":         intent.value,
            "original_query": original_query,
        }
    )

    prioritized: PrioritizedQuestions = result.tasks_output[2].pydantic

    if prioritized is None:
        raise CrewFailure("Agent 2 prioritizer returned no parseable output.")

    # Node-level coverage check (not inside prompt — uses intent to drive assertion)
    try:
        assert_checklist_coverage(intent, prioritized.questions)
    except AssertionError as exc:
        # One retry: re-run only 2b + 2c with tightened prompt listing missing categories
        missing = missing_categories(intent, prioritized.questions)
        if missing:
            retry_result = await _retry_with_gap_fill(
                crew, chosen_query, intent, original_query, prioritized, missing
            )
            return retry_result
        raise CrewFailure(f"Coverage check failed and no missing categories found: {exc}") from exc

    return A2Output(questions=prioritized.questions)


async def _retry_with_gap_fill(
    crew: Crew,
    chosen_query: str,
    intent: IntentKind,
    original_query: str,
    prior_prioritized: PrioritizedQuestions,
    missing: list,
) -> A2Output:
    """Single retry: inject a note about missing categories and re-run the full crew."""
    missing_str = ", ".join(c.value for c in missing)
    augmented_query = (
        f"{chosen_query} "
        f"[RETRY: ensure questions cover these missing categories: {missing_str}]"
    )

    retry_crew = build_a2_crew()
    retry_result = await retry_crew.kickoff_async(
        inputs={
            "chosen_query":   augmented_query,
            "intent":         intent.value,
            "original_query": original_query,
        }
    )

    retry_prioritized: PrioritizedQuestions = retry_result.tasks_output[2].pydantic
    if retry_prioritized is None:
        raise CrewFailure("Agent 2 retry also returned no parseable output.")

    # If still failing, surface a clear error rather than silently continuing
    assert_checklist_coverage(intent, retry_prioritized.questions)

    return A2Output(questions=retry_prioritized.questions)
