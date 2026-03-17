"""
Research Agent — Multi-layer market research pipeline.

Three parallel layers, each producing a report:
  Layer 0 (Baseline):   Single LLM call, no research.     → layers/baseline.py
  Layer 1 (Enhanced):   ReAct agent + web tools.           → layers/enhanced.py
  Layer 2 (Expert):     4-phase knowledge pipeline:        → layers/expert.py
      Phase 1 (Understand) → phases/understand.py
      Phase 2 (Research)   → phases/research.py
      Phase 3 (Analyze)    → phases/analyze.py
      Phase 4 (Write)      → phases/write.py

Orchestration:
  pipeline.py      — runs all 3 layers in parallel, then evaluates
  react_engine.py  — ReAct agent engine (used by Layer 1)
  evaluator.py     — scores and compares layer outputs

Shared:
  models.py   — all data classes
  prompts.py  — all prompt templates
  utils.py    — JSON extraction, content helpers, text cleaning
  cost.py     — LLM cost tracking
  cli.py      — CLI print/save utilities
"""

from research_agent.pipeline import run_pipeline


async def run_all_layers(topic, max_layer=3, progress_callback=None):
    """Run the full research pipeline and produce a comparison report."""
    return await run_pipeline(topic=topic, progress_callback=progress_callback)


__all__ = ["run_all_layers"]
