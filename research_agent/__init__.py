"""
Multi-Layer Research Agent System
=================================

Progressively improves research quality through 4 layers,
replicating the methodology of an experienced market researcher.

Layer 0 — Baseline:    Single LLM prompt, no research
Layer 1 — Research:    Web search → source gathering → grounded synthesis
Layer 2 — Analysis:    Cross-referencing → framework application → gap-filling → quantified claims
Layer 3 — Expert:      Assumption challenging → second-order effects → contrarian views → final polish
"""

from research_agent.runner import run_all_layers, run_layer

__all__ = ["run_all_layers", "run_layer"]
