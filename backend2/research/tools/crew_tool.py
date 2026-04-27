"""LangChain Core tools → CrewAI ``BaseTool`` (required by recent CrewAI + Pydantic v2)."""

from __future__ import annotations

from crewai.tools.base_tool import Tool as CrewTool


def to_crew_tools(*langchain_tools) -> list:
    """Wrap LangChain ``StructuredTool`` instances from ``@tool`` for use on ``crewai.Agent``."""
    return [CrewTool.from_langchain(t) for t in langchain_tools]
