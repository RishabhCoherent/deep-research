"""
Test GPT Researcher vs our pipeline.

Runs the same topic through gpt-researcher and saves output for comparison.
Usage: python test_gpt_researcher.py
"""

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# gpt-researcher uses TAVILY_API_KEY, our .env has TAV_API_KEY
if not os.getenv("TAVILY_API_KEY") and os.getenv("TAV_API_KEY"):
    os.environ["TAVILY_API_KEY"] = os.getenv("TAV_API_KEY")

from gpt_researcher import GPTResearcher


TOPIC = (
    "Analyze the market potential for social commerce across the Asia Pacific region "
    "and recommend the top three countries based on a comparison of more than 50 parameters."
)


async def run_research():
    print(f"{'='*70}")
    print(f"GPT Researcher Test")
    print(f"Topic: {TOPIC}")
    print(f"Started: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*70}\n")

    start = time.time()

    # report_type options: "research_report", "detailed_report", "resource_report"
    researcher = GPTResearcher(
        query=TOPIC,
        report_type="detailed_report",  # most comprehensive option
    )

    print("[1/2] Conducting research (searching + scraping)...")
    await researcher.conduct_research()

    research_time = time.time() - start
    print(f"      Research done in {research_time:.1f}s")
    print(f"      Sources found: {len(researcher.get_source_urls())}")

    print("[2/2] Writing report...")
    report = await researcher.write_report()

    total_time = time.time() - start
    word_count = len(report.split())
    sources = researcher.get_source_urls()

    print(f"\n{'='*70}")
    print(f"RESULTS")
    print(f"{'='*70}")
    print(f"Total time:   {total_time:.1f}s ({total_time/60:.1f} min)")
    print(f"Word count:   {word_count}")
    print(f"Sources used: {len(sources)}")
    print(f"{'='*70}\n")

    # Save report as markdown
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = output_dir / f"gpt_researcher_{timestamp}.md"
    md_path.write_text(report, encoding="utf-8")
    print(f"Report saved: {md_path}")

    # Save metadata as JSON
    meta_path = output_dir / f"gpt_researcher_{timestamp}_meta.json"
    meta = {
        "topic": TOPIC,
        "report_type": "detailed_report",
        "timestamp": timestamp,
        "total_seconds": round(total_time, 1),
        "research_seconds": round(research_time, 1),
        "word_count": word_count,
        "source_count": len(sources),
        "sources": sources,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Metadata saved: {meta_path}")

    # Print first 500 chars as preview
    print(f"\n{'='*70}")
    print(f"REPORT PREVIEW (first 500 chars)")
    print(f"{'='*70}")
    print(report[:500])
    print("...")

    return report, meta


if __name__ == "__main__":
    asyncio.run(run_research())
