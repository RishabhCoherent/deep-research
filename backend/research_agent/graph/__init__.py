"""
LangGraph agent engine — split into submodules for clarity.

Re-exports all public symbols so existing imports like
  `from research_agent.graph import build_agent_graph`
continue to work unchanged.
"""

from research_agent.graph.state import AgentState
from research_agent.graph.tools import make_tools, _validate_finding_against_source
from research_agent.graph.builder import build_agent_graph, build_initial_state, ProgressFn

# Backward compat — baseline.py and expert.py import this from graph
from research_agent.scrubbing import _scrub_competitor_mentions

__all__ = [
    "AgentState",
    "make_tools",
    "_validate_finding_against_source",
    "build_agent_graph",
    "build_initial_state",
    "ProgressFn",
    "_scrub_competitor_mentions",
]
