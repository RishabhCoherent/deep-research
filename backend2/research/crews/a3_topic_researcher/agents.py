"""CrewAI agents for Agent 3 - Topic Researcher."""

from crewai import Agent
from research.api.model_router import haiku, sonnet
from research.tools.research_search import research_search
from research.tools.web_fetch import web_fetch
from research.tools.scratchpad_rw import scratchpad_read, scratchpad_write
from research.tools.assess_source import assess_source
from pathlib import Path

_PROMPTS = Path(__file__).parent / "prompts"
_PLAYBOOK_PATH = (
    Path(__file__).parent.parent / "a1_query_refiner" / "prompts" / "_playbook.md"
)
_PLAYBOOK = _PLAYBOOK_PATH.read_text()


def _fill(path: Path) -> str:
    return path.read_text().replace("{PLAYBOOK}", _PLAYBOOK)


def build_agents():
    """Build the four sub-agents for Agent 3."""

    search_planner = Agent(
        role="Search Planner",
        goal="Convert sub-questions into precise Tavily search queries for numeric evidence.",
        backstory="Research librarian who constructs expert Boolean and site-filtered queries.",
        llm=haiku(max_tokens=2_000),
        tools=[],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "3a_search_planner.md"),
    )

    source_fetcher = Agent(
        role="Source Fetcher",
        goal="Execute searches, fetch passages, deduplicate, keep best 12 by authority×relevance.",
        backstory="Diligent research analyst who reads everything before writing a single word.",
        llm=sonnet(),
        tools=[research_search, web_fetch, scratchpad_read, assess_source],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "3b_source_fetcher.md"),
    )

    claim_extractor = Agent(
        role="Claim Extractor",
        goal="Extract verbatim numeric claims with exact citations from fetched passages.",
        backstory="Fact-checker who copies sentences verbatim and never paraphrases numbers.",
        llm=haiku(max_tokens=4_000),
        tools=[],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "3c_claim_extractor.md"),
    )

    topic_summarizer = Agent(
        role="Topic Summarizer",
        goal="Write a 400-800 word analyst narrative citing claims; push observations to scratchpad.",
        backstory="Senior analyst who writes tight, number-first briefing notes for partners.",
        llm=sonnet(),
        tools=[scratchpad_write],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "3d_topic_summarizer.md"),
    )

    return search_planner, source_fetcher, claim_extractor, topic_summarizer
