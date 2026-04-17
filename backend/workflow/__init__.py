"""Workflow package — L1 LangGraph helpers and optional post-run evaluation.

Full-job orchestration lives in ``workflow.pipeline_graph`` (called from
``research_manager``). This ``__init__`` re-exports only the L1 graph pieces
used by ``layers/enhanced_agent``.
"""

from workflow.state import AgentState
from workflow.tool_factory import make_tools, _validate_finding_against_source
from workflow.enhanced_graph import build_agent_graph, build_initial_state, ProgressFn
from utils.text_cleaning import _scrub_competitor_mentions
