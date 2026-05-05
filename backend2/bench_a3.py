"""Benchmark _research_part to confirm the sync-search blocking diagnosis.

Runs 6 _research_part calls (a) sequentially and (b) "concurrently" with
asyncio.gather. If real concurrency is broken by sync search blocking the
event loop, the gather time should be close to the sum of sequential times,
not max(individual times).
"""
import asyncio
import time

from research.crews.a3_topic_researcher.crew import _research_part


SEQ_PARTS = [
    "BYD blade battery cell production 2025",
    "CATL gigafactory output Germany",
    "lithium spot price floor 2024",
    "cobalt artisanal mining DRC volume",
    "EV battery pack manufacturing cost target 2030",
    "wheel hub motor adoption trends",
]
CONC_PARTS = [
    "stationary battery storage capacity additions 2024",
    "second-life battery resale value forecast",
    "tesla 4680 cell yield improvement",
    "iron-air battery commercial deployment",
    "lithium hydroxide vs carbonate market share",
    "anode-free lithium metal battery research",
]


async def main():
    seen: set[str] = set()
    print("\n=== Sequential (one at a time) ===")
    seq_start = time.perf_counter()
    for q in SEQ_PARTS:
        t0 = time.perf_counter()
        passages = await _research_part(q, "bench_sq", seen)
        dt = time.perf_counter() - t0
        print(f"  '{q[:40]:40s}'  {dt:6.2f}s  passages={len(passages)}")
    seq_total = time.perf_counter() - seq_start
    print(f"SEQUENTIAL TOTAL: {seq_total:.2f}s")

    # Reset URL set for fair comparison
    seen.clear()

    print("\n=== Concurrent (asyncio.gather, supposed concurrency=6) ===")
    par_start = time.perf_counter()
    started: dict[str, float] = {}

    async def timed(q: str):
        started[q] = time.perf_counter()
        passages = await _research_part(q, "bench_sq", seen)
        dt = time.perf_counter() - started[q]
        return q, dt, len(passages)

    results = await asyncio.gather(*[timed(q) for q in CONC_PARTS])
    par_total = time.perf_counter() - par_start
    for q, dt, npass in results:
        print(f"  '{q[:40]:40s}'  {dt:6.2f}s  passages={npass}")
    print(f"CONCURRENT TOTAL: {par_total:.2f}s")
    print()
    print(f"speedup: {seq_total/par_total:.2f}x  (perfect concurrency would be 6.00x)")


if __name__ == "__main__":
    asyncio.run(main())
