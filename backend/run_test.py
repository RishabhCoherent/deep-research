"""
Quick test runner — runs the analyst agent on a topic and saves results.
Usage: python run_test.py
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from layers.analyst.run import run_analyst


TOPIC = "The electric aircraft (eVTOL) race in 2025-2026 — focus on Joby Aviation, Archer Aviation, and Lilium's restructuring. Include funding raised, FAA certification progress, and commercial launch timelines."


def progress(layer, phase, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{phase}] {msg[:120]}")


async def main():
    print(f"\n{'='*70}")
    print(f"TOPIC: {TOPIC}")
    print(f"{'='*70}\n")

    result = await run_analyst(
        topic=TOPIC,
        progress_callback=progress,
    )

    # Save full result
    out = {
        "topic": TOPIC,
        "ran_at": datetime.now().isoformat(),
        "word_count": len(result.content.split()),
        "evidence_count": result.metadata.get("evidence_count"),
        "searches": result.metadata.get("searches_count"),
        "scrapes": result.metadata.get("scrapes_done"),
        "coverage": result.metadata.get("coverage"),
        "quality": result.metadata.get("quality"),
        "tool_calls": result.metadata.get("tool_calls"),
        "elapsed_s": round(result.elapsed_seconds, 1),
        "content": result.content,
        "trace": result.metadata.get("trace", {}),
        "board": result.metadata.get("board", {}),
        "analysis": result.metadata.get("analysis", {}),
    }

    out_path = Path("data/test_run_evtol.json")
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*70}")
    print(f"DONE — {out['word_count']} words, {out['evidence_count']} evidence, "
          f"{out['searches']} searches, coverage={out['coverage']:.0%}")
    print(f"Quality: {out['quality']}")
    print(f"Saved to: {out_path}")
    print(f"{'='*70}\n")

    # Print report preview
    print(result.content[:3000])


if __name__ == "__main__":
    asyncio.run(main())
