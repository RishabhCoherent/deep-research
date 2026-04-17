"""CrewAI agents for Agent 5 - News & Events Researcher."""

from pathlib import Path
from crewai import Agent

from research.api.model_router import haiku, sonnet
from research.tools.web_search import web_search
from research.tools.web_fetch import web_fetch
from research.tools.scratchpad_rw import scratchpad_read, scratchpad_write

_PROMPTS = Path(__file__).parent / "prompts"
_PLAYBOOK_PATH = (
    Path(__file__).parent.parent / "a1_query_refiner" / "prompts" / "_playbook.md"
)
_PLAYBOOK = _PLAYBOOK_PATH.read_text()


def _fill(path: Path) -> str:
    return path.read_text().replace("{PLAYBOOK}", _PLAYBOOK)


def build_agents():
    """Build the three sub-agents for Agent 5."""

    event_hunter = Agent(
        role="Event Hunter",
        goal="Find significant company/product/M&A/earnings events from the last 90 days.",
        backstory="Financial journalist who monitors every press release and earnings call.",
        llm=haiku(max_tokens=1_200),
        tools=[web_search, web_fetch],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "5a_event_hunter.md"),
    )

    regulatory_tracker = Agent(
        role="Regulatory Tracker",
        goal="Track tariff, subsidy, standard, and antitrust changes in the last 90 days.",
        backstory="Policy analyst who reads every Federal Register, Official Journal, and gazette.",
        llm=haiku(max_tokens=1_200),
        tools=[web_search, web_fetch],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "5b_regulatory_tracker.md"),
    )

    geopolitical_scanner = Agent(
        role="Geopolitical Scanner",
        goal="Identify supply-chain disruptions targeting value-chain upstream nodes from scratchpad.",
        backstory="Geopolitical risk analyst who tracks conflicts, sanctions, and export controls.",
        llm=sonnet(max_tokens=1_500),
        tools=[web_search, scratchpad_read, scratchpad_write],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "5c_geopolitical_scanner.md"),
    )

    return event_hunter, regulatory_tracker, geopolitical_scanner
