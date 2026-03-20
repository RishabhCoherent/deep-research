"""
Research Agent — Multi-layer sequential research pipeline.

Three layers run sequentially, each improving on the previous:
  Layer 0 (Baseline):     Best model, no tools.          → layers/baseline.py
  Layer 1 (Enhancement):  LangGraph agent + web search.  → layers/enhanced.py
  Layer 2 (Deep Dive):    LangGraph agent + deep search. → layers/expert.py

Orchestration:
  pipeline.py      — runs all 3 layers sequentially, then evaluates
  graph.py         — LangGraph agent engine (used by Layer 1 and 2)
  evaluator.py     — scores and compares layer outputs

Shared:
  models.py   — all data classes
  prompts.py  — all prompt templates
  utils.py    — JSON extraction, content helpers, text cleaning, outline generation
  cost.py     — LLM cost tracking
  cli.py      — CLI print/save utilities
"""

from research_agent.pipeline import run_pipeline


async def run_all_layers(topic, brief="", max_layer=3, progress_callback=None):
    """Run the full research pipeline and produce a comparison report."""
    return await run_pipeline(topic=topic, brief=brief, progress_callback=progress_callback)


__all__ = ["run_all_layers"]
