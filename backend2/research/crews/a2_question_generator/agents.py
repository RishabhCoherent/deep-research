"""CrewAI agents for Agent 2 - Question Generator."""

from crewai import Agent
from research.api.model_router import haiku, sonnet
from pathlib import Path

_PROMPTS = Path(__file__).parent / "prompts"
_PLAYBOOK_PATH = Path(__file__).parent.parent.parent / "crews" / "a1_query_refiner" / "prompts" / "_playbook.md"
_PLAYBOOK = _PLAYBOOK_PATH.read_text()
_CHECKLIST = (_PROMPTS / "_checklist.md").read_text()


def _fill(path: Path) -> str:
    """Substitute {PLAYBOOK} and {CHECKLIST} placeholders in prompt templates."""
    return (
        path.read_text()
        .replace("{PLAYBOOK}", _PLAYBOOK)
        .replace("{CHECKLIST}", _CHECKLIST)
    )


def build_agents():
    """Build the three sub-agents for Agent 2."""

    decomposer = Agent(
        role="Sub-Question Decomposer",
        goal="Break the refined query into 10-18 atomic sub-questions.",
        backstory="Senior analyst who scopes research engagements in kickoff meetings.",
        llm=sonnet(),
        tools=[],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "2a_decomposer.md"),
    )

    gap_analyzer = Agent(
        role="Gap Analyzer",
        goal="Ensure the question set covers the senior-analyst checklist for this intent.",
        backstory="Editor who red-lines research briefs to catch missing analytical angles.",
        llm=haiku(max_tokens=4_096),
        tools=[],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "2b_gap_analyzer.md"),
    )

    prioritizer = Agent(
        role="Question Prioritizer",
        goal="Score, deduplicate, and rank questions; return 8-15 sorted descending.",
        backstory="Research lead triaging the day's workload by value and feasibility.",
        llm=haiku(max_tokens=4_096),
        tools=[],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "2c_prioritizer.md"),
    )

    return decomposer, gap_analyzer, prioritizer
