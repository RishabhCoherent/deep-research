"""CrewAI agents for Agent 8 - Causation / Reasoning.

8a: Haiku — finds metric deltas from validated claims (no tools).
8b: Sonnet — correlates events to deltas (web_search basic + scratchpad_read).
8c: Pure Python (evidence_validator.py) — no CrewAI agent.
"""

from pathlib import Path
from crewai import Agent

from research.api.model_router import haiku, sonnet
from research.tools.crew_tool import to_crew_tools
from research.tools.web_search import web_search
from research.tools.scratchpad_rw import scratchpad_read

_PROMPTS = Path(__file__).parent / "prompts"
_PLAYBOOK_PATH = (
    Path(__file__).parent.parent / "a1_query_refiner" / "prompts" / "_playbook.md"
)
_PLAYBOOK = _PLAYBOOK_PATH.read_text()


def _fill(path: Path) -> str:
    return path.read_text().replace("{PLAYBOOK}", _PLAYBOOK)


def build_agents():
    """Build the two LLM sub-agents for Agent 8. 8c is pure Python."""

    delta_detector = Agent(
        role="Delta Detector",
        goal="Identify metrics with prior and current values; compute delta percentages.",
        backstory="Quant analyst who spots meaningful data changes across time-series.",
        llm=haiku(max_tokens=800),
        tools=[],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "8a_delta_detector.md"),
    )

    event_correlator = Agent(
        role="Event Correlator",
        goal="Find causal events for each metric delta with ≥2 independent citations.",
        backstory="Investigative journalist who traces market moves to their root causes.",
        llm=sonnet(max_tokens=2_500),
        tools=to_crew_tools(web_search, scratchpad_read),
        max_iter=6,
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "8b_event_correlator.md"),
    )

    return delta_detector, event_correlator
