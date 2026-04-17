"""CrewAI tasks for Agent 5 - News & Events Researcher.

Task layout:
  t_events  (async=True)  ─┐
                            ├─► t_geopolitical (sequential, context=[both])
  t_regulatory (async=True) ┘

5a and 5b run concurrently (both Haiku, independent inputs).
5c runs after both complete — its context window contains their outputs
and it benefits from maximum scratchpad population time from Agent 4b.
"""

from crewai import Task
from .schemas import EventBundle, RegulatoryBundle, GeopoliticalBundle


def build_tasks(hunter, tracker, scanner):
    """Build tasks with 5a ‖ 5b parallel, then 5c sequential."""

    t_events = Task(
        description=(
            "Scan for company, product, M&A, earnings, and partnership news "
            "from the last 90 days that affect the child or parent market. "
            "intent={intent}, chosen_query={chosen_query}"
        ),
        expected_output="JSON matching EventBundle: {events: [≥3 NewsEvent objects]}.",
        agent=hunter,
        async_execution=True,
        output_pydantic=EventBundle,
    )

    t_regulatory = Task(
        description=(
            "Find tariff, subsidy, standard, and antitrust regulatory changes "
            "from the last 90 days affecting the market. "
            "intent={intent}, chosen_query={chosen_query}"
        ),
        expected_output="JSON matching RegulatoryBundle: {changes: [≥1 RegulatoryChange]}.",
        agent=tracker,
        async_execution=True,
        output_pydantic=RegulatoryBundle,
    )

    t_geopolitical = Task(
        description=(
            "Read the value chain from the scratchpad (market_context section) "
            "then run targeted news searches per upstream node to find "
            "conflicts, sanctions, and supply-chain disruptions. "
            "Write elevated/critical findings to scratchpad section='news'. "
            "intent={intent}, chosen_query={chosen_query}"
        ),
        expected_output=(
            "JSON matching GeopoliticalBundle: "
            "{disruptions: [Disruption, ...], scratchpad_writes: [Observation, ...]}."
        ),
        agent=scanner,
        context=[t_events, t_regulatory],
        output_pydantic=GeopoliticalBundle,
    )

    return t_events, t_regulatory, t_geopolitical
