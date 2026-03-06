"""
Generic agent loop: Plan → Research → Draft → Self-Evaluate → Refine.

Pure async Python, no frameworks. Each research layer provides callbacks
for its specific behavior; the loop handles the iteration logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional, Awaitable

from research_agent.types import Source

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    """Self-evaluation output from the reviewer."""
    overall_score: float                        # 0.0 - 10.0
    dimension_scores: dict = field(default_factory=dict)  # {"coverage": 7, ...}
    weaknesses: list[str] = field(default_factory=list)
    suggested_queries: list[str] = field(default_factory=list)

    @property
    def pass_threshold(self) -> bool:
        return self._threshold_met

    def check_threshold(self, threshold: float) -> bool:
        self._threshold_met = self.overall_score >= threshold
        return self._threshold_met


@dataclass
class AgentIteration:
    """Record of one iteration for metadata/debugging."""
    iteration: int
    eval_score: float
    weaknesses: list[str]
    queries_run: list[str]
    new_sources_count: int


# Type aliases for callback signatures
PlanFn = Callable[[str, str], Awaitable[dict]]
ResearchFn = Callable[[list[str], list[Source]], Awaitable[tuple[list[Source], str]]]
DraftFn = Callable[[str, str, str], Awaitable[str]]
EvaluateFn = Callable[[str, str], Awaitable[EvalResult]]
ProgressFn = Optional[Callable[[int, str, str], None]]


async def run_agent_loop(
    topic: str,
    layer: int,
    plan_fn: PlanFn,
    research_fn: ResearchFn,
    draft_fn: DraftFn,
    evaluate_fn: EvaluateFn,
    max_iterations: int = 3,
    convergence_threshold: float = 7.0,
    initial_context: str = "",
    existing_sources: Optional[list[Source]] = None,
    progress_callback: ProgressFn = None,
) -> tuple[str, list[Source], list[AgentIteration]]:
    """
    Run the agent loop: plan → research → draft → evaluate → refine.

    Returns (final_draft, all_sources, iteration_history).
    """
    sources = list(existing_sources or [])
    context = initial_context
    draft = ""
    iterations: list[AgentIteration] = []

    def notify(status: str, msg: str):
        if progress_callback:
            progress_callback(layer, status, msg)
        logger.info(f"[Agent L{layer}] {status}: {msg}")

    for i in range(max_iterations):
        # ── Step 1: Plan (first iteration) or re-plan from weaknesses ──
        if i == 0:
            notify("planning", "Analyzing topic and planning research strategy...")
            plan = await plan_fn(topic, context)
            queries = plan.get("queries", [])
        else:
            # Use suggested queries from self-evaluation
            queries = eval_result.suggested_queries
            if not queries:
                logger.info(f"[Agent L{layer}] No suggested queries, stopping.")
                break

        notify("researching", f"Iteration {i + 1}/{max_iterations}: "
               f"executing {len(queries)} queries...")

        # ── Step 2: Research ──────────────────────────────────────────
        new_sources, new_context = await research_fn(queries, sources)
        sources.extend(new_sources)
        if new_context:
            context = context + "\n\n" + new_context if context else new_context

        # ── Step 3: Draft (or refine) ────────────────────────────────
        notify("drafting", f"Iteration {i + 1}/{max_iterations}: "
               f"{'writing initial draft...' if i == 0 else 'refining draft...'}")
        draft = await draft_fn(topic, context, draft)

        # ── Step 4: Self-evaluate ────────────────────────────────────
        notify("evaluating", f"Iteration {i + 1}/{max_iterations}: self-reviewing...")
        eval_result = await evaluate_fn(draft, topic)
        eval_result.check_threshold(convergence_threshold)

        iterations.append(AgentIteration(
            iteration=i,
            eval_score=eval_result.overall_score,
            weaknesses=eval_result.weaknesses,
            queries_run=queries,
            new_sources_count=len(new_sources),
        ))

        notify("eval_done", f"Iteration {i + 1}: score={eval_result.overall_score:.1f}/10"
               f"{' — converged!' if eval_result.pass_threshold else ''}")

        # ── Step 5: Check convergence ────────────────────────────────
        if eval_result.pass_threshold:
            break

        # Check if score improved enough to justify another iteration
        if i > 0 and len(iterations) >= 2:
            prev_score = iterations[-2].eval_score
            if eval_result.overall_score - prev_score < 0.3:
                logger.info(f"[Agent L{layer}] Minimal improvement "
                           f"({prev_score:.1f} → {eval_result.overall_score:.1f}), stopping.")
                break

    return draft, sources, iterations
