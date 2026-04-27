"""Quick sanity test for the full pipeline."""
import asyncio
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv
load_dotenv(BACKEND_ROOT.parent / ".env")
load_dotenv(BACKEND_ROOT / ".env")

from research.graph.build import build_graph
from research.core.state import create_initial_state
import uuid

async def test():
    run_id = str(uuid.uuid4())
    state = create_initial_state(run_id, "autonomous trucking market outlook 2026")
    graph = build_graph()
    config = {"configurable": {"thread_id": run_id, "auto_pick": 1}}
    print("Starting graph invocation...")
    t0 = time.perf_counter()
    try:
        result = await graph.ainvoke(state, config=config)
        elapsed = time.perf_counter() - t0
        print(f"Done in {elapsed:.1f}s")
        print("Result keys:", list(result.keys()))
        # Print some summary data
        print("Chosen query:", result.get("chosen_query", "N/A"))
        print("Sub-questions count:", len(result.get("sub_questions", [])))
        print("Topic claims count:", len(result.get("topic_claims", [])))
        print("Consolidated:", bool(result.get("consolidated")))
        print("Validated claims:", len(result.get("validated_claims", [])))
        print("Causations:", len(result.get("causations", [])))
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"Error after {elapsed:.1f}s: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    asyncio.run(test())
