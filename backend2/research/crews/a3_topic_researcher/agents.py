"""CrewAI agents for Agent 3 - Topic Researcher.

source_fetcher (Sonnet, max_iter=8 tool loop) was removed because it was
unused — the live path uses pure-Python search+scrape via
`_recursive_fetch_passages` / `_deep_fetch_passages` in crew.py. Keeping
the agent forced an unnecessary Sonnet model instantiation and confused
the LLM-call budget reporting.
"""

from crewai import Agent
from research.api.model_router import haiku, sonnet
from pathlib import Path

_PROMPTS = Path(__file__).parent / "prompts"
_PLAYBOOK_PATH = (
    Path(__file__).parent.parent / "a1_query_refiner" / "prompts" / "_playbook.md"
)
_PLAYBOOK = _PLAYBOOK_PATH.read_text()


def _fill(path: Path) -> str:
    return path.read_text().replace("{PLAYBOOK}", _PLAYBOOK)


def build_agents():
    """Build the three sub-agents actually used by Agent 3.

    Returns (search_planner, claim_extractor, topic_summarizer). The
    legacy `source_fetcher` slot has been removed — fetching is done in
    pure-Python (no LLM) by `_recursive_fetch_passages` /
    `_deep_fetch_passages` in crew.py.
    """

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

    claim_extractor = Agent(
        role="Claim Structurer",
        goal="Structure pre-found numeric candidates into NumericClaims with full qualifiers.",
        backstory="Analyst who takes spans found by a deterministic prefilter and "
                  "fills in subject, metric_kind, scope, and time qualifiers.",
        llm=haiku(max_tokens=12_000),
        tools=[],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "3c_claim_extractor.md"),
    )

    topic_summarizer = Agent(
        role="Topic Summarizer",
        goal="Write a 400-800 word analyst narrative citing claims; include observations in JSON.",
        backstory="Senior analyst who writes tight, number-first briefing notes for partners.",
        llm=sonnet(max_tokens=6_000),
        tools=[],
        allow_delegation=False,
        verbose=False,
        system_template=_fill(_PROMPTS / "3d_topic_summarizer.md"),
    )

    return search_planner, claim_extractor, topic_summarizer
