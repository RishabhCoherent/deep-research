"""CrewAI tasks for Agent 4 - Market Context Researcher."""

from crewai import Task
from .schemas import ParentMarketResult, ValueChainMap, ImpactAnalysis


def build_tasks(identifier, mapper, analyst):
    """Build three sequential tasks for Agent 4."""

    t_identify = Task(
        description=(
            "Identify the parent and grandparent market for the child market "
            "in the chosen query. "
            "intent={intent}, chosen_query={chosen_query}, "
            "sub_questions_json={sub_questions_json}"
        ),
        expected_output="JSON matching ParentMarketResult (child, parent, grandparent, justification, citations).",
        agent=identifier,
        output_pydantic=ParentMarketResult,
    )

    t_map = Task(
        description=(
            "Map the full value chain for the parent market: upstream, midstream, "
            "downstream, and substitutes. Immediately write key nodes to scratchpad "
            "section='market_context'. "
            "chosen_query={chosen_query}, parent_market_json={parent_market_json}"
        ),
        expected_output="JSON matching ValueChainMap (≥2 upstream, ≥1 midstream, scratchpad_writes).",
        agent=mapper,
        context=[t_identify],
        output_pydantic=ValueChainMap,
    )

    t_analyse = Task(
        description=(
            "Quantify parent-market forces passing through to the child market. "
            "Extract NumericClaims with verbatim raw_excerpts. Write 400-800 word narrative. "
            "chosen_query={chosen_query}, "
            "parent_market_json={parent_market_json}, "
            "value_chain_json={value_chain_json}, "
            "sub_questions_json={sub_questions_json}"
        ),
        expected_output="JSON matching ImpactAnalysis (impacts with evidence, claims, 400-800 word narrative).",
        agent=analyst,
        context=[t_identify, t_map],
        output_pydantic=ImpactAnalysis,
    )

    return t_identify, t_map, t_analyse
