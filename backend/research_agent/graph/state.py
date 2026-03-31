"""AgentState — LangGraph state schema for L1/L2 research agents."""

from __future__ import annotations

from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """State for LangGraph research agents (L1 and L2)."""
    messages: Annotated[list[BaseMessage], add_messages]
    topic: str
    brief: str             # detailed client instructions (optional)
    layer: int
    prior_report: str
    tool_call_count: int
    max_tool_calls: int
    tool_calls_log: list[dict]
    draft: str
    retries: int           # number of times agent was asked to retry output
    max_retries: int
    min_word_count: int
    forced_search: bool    # whether we've already forced more research
