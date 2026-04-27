"""Run the full A1–A8 LangGraph pipeline, save markdown + metrics.

Usage (from `backend2` directory):
    python scripts/run_full_pipeline.py "Your research topic here"

Requires ANTHROPIC_API_KEY and TAVILY_API_KEY in environment or `.env`.

CrewAI token usage is aggregated by monkey-patching `Crew.kickoff_async` before
importing the graph (covers all crews). Cost bounds use Anthropic list pricing
for Claude 3.5 Haiku ($1/$5 per MTok in/out) and Sonnet ($3/$15 per MTok); actual
billed cost will fall between these when calls mix models.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure `import research` works when run as `python scripts/run_full_pipeline.py`
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from dotenv import load_dotenv

load_dotenv(_BACKEND_ROOT.parent / ".env")
load_dotenv(_BACKEND_ROOT / ".env")


def _patch_crew_token_aggregation():
    """Aggregate UsageMetrics from every CrewAI kickoff_async call."""
    from crewai import Crew
    from crewai.types.usage_metrics import UsageMetrics

    total = UsageMetrics()
    _orig = Crew.kickoff_async

    async def _wrapped(self, inputs=None):
        out = await _orig(self, inputs)
        total.add_usage_metrics(out.token_usage)
        return out

    Crew.kickoff_async = _wrapped
    return total


def _estimate_cost_bounds(metrics) -> dict:
    """Lower (all Haiku) and upper (all Sonnet) USD bounds from token split."""
    inn = metrics.prompt_tokens
    out = metrics.completion_tokens
    # Anthropic public list pricing (Claude 3.5 era), per 1M tokens
    haiku_in, haiku_out = 1.0, 5.0
    sonnet_in, sonnet_out = 3.0, 15.0
    lower = (inn * haiku_in + out * haiku_out) / 1_000_000
    upper = (inn * sonnet_in + out * sonnet_out) / 1_000_000
    mid = (lower + upper) / 2.0
    return {
        "estimated_cost_usd_haiku_mix_floor": round(lower, 6),
        "estimated_cost_usd_sonnet_mix_ceiling": round(upper, 6),
        "estimated_cost_usd_midpoint_blend": round(mid, 6),
        "pricing_note_usd_per_mtok": {
            "haiku_input": haiku_in,
            "haiku_output": haiku_out,
            "sonnet_input": sonnet_in,
            "sonnet_output": sonnet_out,
        },
    }


def _json_safe(obj):
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(x) for x in obj]
    if isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)


def _write_artifacts(
    *,
    out_dir: Path,
    run_id: str,
    raw_query: str,
    elapsed_s: float,
    usage_accum,
    final: dict | None,
    error: str | None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics = {
        "run_id": run_id,
        "original_query": raw_query,
        "status": "ok" if error is None else "error",
        "error": error,
        "elapsed_seconds": round(elapsed_s, 3),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "crewai_token_usage": usage_accum.model_dump(),
    }
    metrics.update(_estimate_cost_bounds(usage_accum))

    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    if final is not None:
        from research.report.markdown_renderer import render_markdown

        (out_dir / "research_brief.md").write_text(render_markdown(final), encoding="utf-8")
        (out_dir / "state_snapshot.json").write_text(
            json.dumps(_json_safe(final), indent=2, ensure_ascii=False)[:2_000_000],
            encoding="utf-8",
        )
    if error:
        (out_dir / "error.txt").write_text(error, encoding="utf-8")


async def main() -> int:
    raw_query = (
        " ".join(sys.argv[1:]).strip()
        or "Solid-state EV battery pilot programs and commercial readiness in Europe by 2026"
    )

    usage_accum = _patch_crew_token_aggregation()

    from research.graph.build import build_graph
    from research.core.state import create_initial_state

    run_id = str(uuid.uuid4())
    t0 = time.perf_counter()
    out_dir = _BACKEND_ROOT / "out" / f"run_{run_id[:8]}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    state = create_initial_state(run_id, raw_query)
    graph = build_graph()

    config = {
        "configurable": {
            "thread_id": run_id,
            "auto_pick": 1,
        }
    }

    err_text: str | None = None
    final = None
    try:
        final = await graph.ainvoke(state, config=config)
    except BaseException as exc:
        err_text = "".join(traceback.format_exception(exc))

    elapsed_s = time.perf_counter() - t0
    _write_artifacts(
        out_dir=out_dir,
        run_id=run_id,
        raw_query=raw_query,
        elapsed_s=elapsed_s,
        usage_accum=usage_accum,
        final=final,
        error=err_text,
    )

    print(f"run_id={run_id}  status={'ok' if err_text is None else 'error'}")
    print(f"Elapsed: {elapsed_s:.2f}s")
    print(f"Tokens: {usage_accum.total_tokens} (prompt={usage_accum.prompt_tokens}, completion={usage_accum.completion_tokens})")
    metrics_path = out_dir / "metrics.json"
    m = json.loads(metrics_path.read_text(encoding="utf-8"))
    print(f"Est. cost (midpoint blend): ${m['estimated_cost_usd_midpoint_blend']:.4f}")
    print(f"Wrote: {metrics_path}")
    if err_text:
        print(f"Wrote: {out_dir / 'error.txt'}")
        print(err_text[:2000])
        return 1

    print(f"Wrote: {out_dir / 'research_brief.md'}")
    print(f"Wrote: {out_dir / 'state_snapshot.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
