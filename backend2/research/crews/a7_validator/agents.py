"""CrewAI agents for Agent 7 - Validator."""

from pathlib import Path
from crewai import Agent

from research.api.model_router import haiku, sonnet
from research.tools.crew_tool import to_crew_tools
from research.tools.assess_source import assess_source

_PROMPTS = Path(__file__).parent / "prompts"
_PLAYBOOK_PATH = (
    Path(__file__).parent.parent / "a1_query_refiner" / "prompts" / "_playbook.md"
)
_PLAYBOOK = _PLAYBOOK_PATH.read_text()


def _fill(path: Path) -> str:
    return path.read_text().replace("{PLAYBOOK}", _PLAYBOOK)


def build_agents():
    """Build the four sub-agents for Agent 7."""

    authority_ranker = Agent(
        role="Authority Ranker",
        goal="Tag every claim's source with its AuthorityTier using assess_source tool.",
        backstory="Information librarian who classifies source credibility at scale.",
        llm=haiku(max_tokens=1_500),
        tools=to_crew_tools(assess_source),
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "7a_authority_ranker.md"),
    )

    cross_checker = Agent(
        role="Numeric Cross Checker",
        goal="Group claims by semantic equivalence; identify unanimous vs conflicted groups.",
        backstory="Data auditor who catches discrepancies across datasets.",
        llm=haiku(max_tokens=2_000),
        tools=[],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "7b_numeric_cross_checker.md"),
    )

    recency_judge = Agent(
        role="Recency Judge",
        goal="For same-tier claims, flag the most recent publication as the recency winner.",
        backstory="Fact-checker who always cites the most up-to-date source.",
        llm=haiku(max_tokens=1_500),
        tools=[],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "7c_recency_judge.md"),
    )

    conflict_resolver = Agent(
        role="Conflict Resolver",
        goal="Pick the final winner per metric using authority→recency hierarchy; build audit trail.",
        backstory="Senior editor who adjudicates source disputes with documented reasoning.",
        llm=sonnet(max_tokens=3_000),
        tools=[],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "7d_conflict_resolver.md"),
    )

    return authority_ranker, cross_checker, recency_judge, conflict_resolver
