"""
LangGraph pipeline: Main orchestrator + subsection worker subgraph.

Main Graph:
    START → plan → fan-out via Send() → subsection_worker ×11 → assemble → END

Subsection Worker Subgraph:
    START → research ←(loop max 3)→ organize → analyze → write → review ←(rewrite once)→ END
"""

import logging

from langgraph.graph import StateGrtaph, END, START
from langgraph.types import Send

from config import RESEARCH_MAX_ITERATIONS, MIN_CITATIONS_PER_SUBSECTION, MAX_REWRITE_ATTEMPTS
from state import PipelineState, SubSectionWorkerState, WorkerOutput
from nodes.planner import planner_node
from nodes.researcher import researcher_node
from nodes.organizer import organizer_node
from nodes.analyst import analyst_node
from nodes.writer import writer_node
from nodes.reviewer import reviewer_node
from nodes.assembler import assembler_node

logger = logging.getLogger(__name__)


# ─── Subsection Worker: Conditional Edge Functions ─────────────────────────────


def should_continue_research(state: SubSectionWorkerState) -> str:
    """Decide if more research iterations are needed."""
    iteration = state.get("research_iteration", 0)
    max_iter = state.get("max_research_iterations", RESEARCH_MAX_ITERATIONS)
    citations = state.get("citations", [])

    if iteration >= max_iter:
        logger.info(f"Max research iterations ({max_iter}) reached for {state.get('subsection_name')}")
        return "organize"

    if len(citations) >= MIN_CITATIONS_PER_SUBSECTION:
        logger.info(f"Sufficient citations ({len(citations)}) for {state.get('subsection_name')}")
        return "organize"

    logger.info(f"Need more data for {state.get('subsection_name')} "
                f"(iteration {iteration}, citations: {len(citations)})")
    return "research"


def should_rewrite(state: SubSectionWorkerState) -> str:
    """Decide if the written section needs rewriting."""
    feedback = state.get("review_feedback")
    rewrite_count = state.get("rewrite_count", 0)

    if feedback is None:
        return "finalize"

    if isinstance(feedback, dict) and feedback.get("passed", True):
        return "finalize"

    if rewrite_count >= MAX_REWRITE_ATTEMPTS:
        logger.warning(f"Max rewrites reached for {state.get('subsection_name')}, accepting as-is")
        return "finalize"

    logger.info(f"Rewriting {state.get('subsection_name')} (attempt {rewrite_count + 1})")
    return "write"


def increment_rewrite(state: SubSectionWorkerState) -> dict:
    """Increment rewrite counter before sending back to writer."""
    return {"rewrite_count": state.get("rewrite_count", 0) + 1}


def finalize_worker(state: SubSectionWorkerState) -> dict:
    """Package the worker's output for the main graph's accumulation.

    Returns completed_sections and all_citations which merge into PipelineState
    via operator.add.
    """
    written = state.get("written_section", {})
    citations = state.get("citations", [])

    return {
        "completed_sections": [written] if written else [],
        "all_citations": citations,
    }


# ─── Build Subsection Worker Subgraph ──────────────────────────────────────────


def build_subsection_graph() -> StateGraph:
    """Build the inner subgraph that processes one sub-section."""
    g = StateGraph(SubSectionWorkerState, output=WorkerOutput)

    # Nodes
    g.add_node("research", researcher_node)
    g.add_node("organize", organizer_node)
    g.add_node("analyze", analyst_node)
    g.add_node("write", writer_node)
    g.add_node("review", reviewer_node)
    g.add_node("increment_rewrite", increment_rewrite)
    g.add_node("finalize", finalize_worker)

    # Edges
    g.add_edge(START, "research")

    # Research loop: continue or move to organize
    g.add_conditional_edges("research", should_continue_research, {
        "research": "research",
        "organize": "organize",
    })

    g.add_edge("organize", "analyze")
    g.add_edge("analyze", "write")
    g.add_edge("write", "review")

    # Review loop: increment rewrite counter then rewrite, or finalize
    g.add_conditional_edges("review", should_rewrite, {
        "write": "increment_rewrite",
        "finalize": "finalize",
    })
    g.add_edge("increment_rewrite", "write")

    g.add_edge("finalize", END)

    return g.compile()


subsection_subgraph = build_subsection_graph()


# ─── Main Graph: Fan-out Routing ───────────────────────────────────────────────


def route_to_workers(state: PipelineState):
    """Fan out: create one worker per sub-section via Send()."""
    configs = state.get("subsection_configs", [])

    sends = []
    for cfg in configs:
        worker_state = {
            "topic": state["topic"],
            "subsection_id": cfg["id"],
            "subsection_name": cfg["name"],
            "research_queries": [
                {
                    "subsection_id": cfg["id"],
                    "query": q,
                    "intent": f"Find data for {cfg['name']}",
                    "priority": 1,
                }
                for q in cfg.get("query_hints", [])
            ],
            "search_results": [],
            "citations": [],
            "organized_data": None,
            "written_section": None,
            "review_feedback": None,
            "research_iteration": 0,
            "max_research_iterations": RESEARCH_MAX_ITERATIONS,
            "rewrite_count": 0,
        }
        sends.append(Send("subsection_worker", worker_state))

    logger.info(f"Fanning out to {len(sends)} subsection workers")
    return sends


# ─── Build Main Graph ─────────────────────────────────────────────────────────


def build_main_graph():
    """Build the top-level orchestrator graph."""
    g = StateGraph(PipelineState)

    # Nodes
    g.add_node("plan", planner_node)
    g.add_node("subsection_worker", subsection_subgraph)
    g.add_node("assemble", assembler_node)

    # Edges
    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", route_to_workers, ["subsection_worker"])
    g.add_edge("subsection_worker", "assemble")
    g.add_edge("assemble", END)

    return g.compile()


# The compiled graph — import and invoke this
app = build_main_graph()
