"""CrewAI agents for Agent 4 - Market Context Researcher."""

from pathlib import Path
from crewai import Agent

from research.api.model_router import sonnet
from research.tools.research_search import research_search
from research.tools.web_fetch import web_fetch
from research.tools.scratchpad_rw import scratchpad_read, scratchpad_write
from research.tools.assess_source import assess_source

_PROMPTS = Path(__file__).parent / "prompts"
_PLAYBOOK_PATH = (
    Path(__file__).parent.parent / "a1_query_refiner" / "prompts" / "_playbook.md"
)
_PLAYBOOK = _PLAYBOOK_PATH.read_text()


def _fill(path: Path) -> str:
    return path.read_text().replace("{PLAYBOOK}", _PLAYBOOK)


def build_agents():
    """Build the three sub-agents for Agent 4."""

    parent_market_identifier = Agent(
        role="Parent Market Identifier",
        goal="Place the child market in its global hierarchy with citations.",
        backstory="Industry analyst who maps markets using GICS, NAICS, and analyst convention.",
        llm=sonnet(max_tokens=800),
        tools=[research_search, web_fetch],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "4a_parent_market_identifier.md"),
    )

    value_chain_mapper = Agent(
        role="Value Chain Mapper",
        goal="Map upstream/midstream/downstream players with shares; write to scratchpad immediately.",
        backstory="Supply chain strategist who has mapped 200+ industrial value chains.",
        llm=sonnet(max_tokens=2_000),
        tools=[research_search, web_fetch, scratchpad_read, scratchpad_write, assess_source],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "4b_value_chain_mapper.md"),
    )

    impact_analyst = Agent(
        role="Impact Analyst",
        goal="Quantify how parent-market forces pass through to child market with numeric evidence.",
        backstory="Macro economist specialising in input-output pass-through analysis.",
        llm=sonnet(max_tokens=2_000),
        tools=[research_search, scratchpad_read],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "4c_impact_analyst.md"),
    )

    return parent_market_identifier, value_chain_mapper, impact_analyst
