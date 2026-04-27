"""CrewAI agents for Agent 6 - Consolidator. Zero tool calls."""

from pathlib import Path
from crewai import Agent

from research.api.model_router import haiku, sonnet

_PROMPTS = Path(__file__).parent / "prompts"
_PLAYBOOK_PATH = (
    Path(__file__).parent.parent / "a1_query_refiner" / "prompts" / "_playbook.md"
)
_PLAYBOOK = _PLAYBOOK_PATH.read_text()


def _fill(path: Path) -> str:
    return path.read_text().replace("{PLAYBOOK}", _PLAYBOOK)


def build_agents():
    """Build the three sub-agents for Agent 6. No tools — internal state only."""

    claim_normaliser = Agent(
        role="Claim Normaliser",
        goal="Merge all claims from Agents 3/4/5, normalise units, remove exact duplicates.",
        backstory="Data engineer who standardises financial data across disparate sources.",
        llm=haiku(max_tokens=2_500),
        tools=[],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "6a_claim_normaliser.md"),
    )

    theme_clusterer = Agent(
        role="Theme Clusterer",
        goal="Group normalised claims into 3-8 named analyst themes with supporting evidence.",
        backstory="Research strategist who structures data-rooms into investment themes.",
        llm=haiku(max_tokens=3_000),
        tools=[],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "6b_theme_clusterer.md"),
    )

    narrative_builder = Agent(
        role="Narrative Builder",
        goal="Write 800-1500 word bottom-up narrative: one paragraph per theme, exec-summary last.",
        backstory="Senior analyst who writes partner-grade research briefs from structured data.",
        llm=sonnet(max_tokens=3_000),
        tools=[],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "6c_narrative_builder.md"),
    )

    return claim_normaliser, theme_clusterer, narrative_builder
