"""CrewAI crew orchestration for Agent 1 - Query Refiner."""

from crewai import Crew, Process
from .agents import build_agents
from .tasks import build_tasks
from .schemas import A1Output
import json


def build_a1_crew():
    """Build the CrewAI crew for Agent 1."""
    ic, vg, cs = build_agents()
    t_intent, t_variants, t_scored = build_tasks(ic, vg, cs)
    
    return Crew(
        agents=[ic, vg, cs],
        tasks=[t_intent, t_variants, t_scored],
        process=Process.sequential,
        verbose=False,
        memory=False,
    )


async def run_a1(raw_query: str) -> A1Output:
    """Run the Agent 1 crew (no user interaction). Returns ranked variants + intent."""
    crew = build_a1_crew()
    
    result = await crew.kickoff_async(inputs={"raw_query": raw_query})
    
    # CrewAI exposes per-task outputs on result.tasks_output
    intent_out = result.tasks_output[0].pydantic
    scored_out = result.tasks_output[2].pydantic
    
    return A1Output(
        intent=intent_out.intent,
        variants_sorted=scored_out.scored,
        chosen_query=None,
    )
