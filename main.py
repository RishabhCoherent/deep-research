"""
Entry point for the Section 3 pipeline.

Usage:
    python main.py "Global Cancer Stem Cells Market"
    python main.py "Global CAR-T Cell Therapy Market" --context "Focus on FDA-approved therapies"
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger(__name__)
console = Console()


def run(topic: str, context: str = ""):
    """Run the Section 3 pipeline for the given market topic."""
    console.print(Panel(
        f"[bold]Topic:[/bold] {topic}\n"
        f"[bold]Context:[/bold] {context or 'None'}",
        title="[bold green]Section 3: Key Industry Insights Pipeline[/bold green]",
        border_style="green",
    ))

    # Validate API keys
    if not os.getenv("OPENAI_API_KEY"):
        console.print("[bold red]Error: OPENAI_API_KEY not found in environment[/bold red]")
        console.print("Create a .env file with your API key: OPENAI_API_KEY=sk-...")
        sys.exit(1)

    from tools.search import _searxng_available
    if _searxng_available():
        console.print("[dim]SearXNG is running — using SearXNG as primary search[/dim]")
    else:
        console.print("[dim]SearXNG not available — using DuckDuckGo for search[/dim]")
        console.print("[dim]Start SearXNG with: docker compose up -d[/dim]")

    # Import graph here to avoid import-time errors if env not loaded
    from graph import app

    console.print("\n[bold]Starting pipeline...[/bold]\n")

    initial_state = {
        "topic": topic,
        "report_context": context,
        "subsection_configs": [],
        "completed_sections": [],
        "all_citations": [],
        "final_section": "",
        "citation_bibliography": "",
        "status": "planning",
    }

    # Run the pipeline
    result = app.invoke(initial_state)

    # Save output
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = topic.replace(" ", "_")[:50]
    output_path = output_dir / f"{safe_topic}_section3_{timestamp}.md"

    report_content = result.get("final_section", "")
    bibliography = result.get("citation_bibliography", "")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)
        if bibliography:
            f.write("\n\n---\n\n")
            f.write(bibliography)

    # Print summary
    completed = result.get("completed_sections", [])
    all_cit = result.get("all_citations", [])
    total_words = sum(
        s.get("word_count", 0) for s in completed if isinstance(s, dict)
    )

    console.print(Panel(
        f"[bold]Sections written:[/bold] {len(completed)}/11\n"
        f"[bold]Total words:[/bold] {total_words:,}\n"
        f"[bold]Total citations:[/bold] {len(all_cit)}\n"
        f"[bold]Output:[/bold] {output_path}",
        title="[bold green]Pipeline Complete[/bold green]",
        border_style="green",
    ))


def main():
    parser = argparse.ArgumentParser(
        description="Generate Section 3 (Key Industry Insights) of a market research report"
    )
    parser.add_argument("topic", help="Market topic (e.g., 'Global Cancer Stem Cells Market')")
    parser.add_argument("--context", "-c", default="", help="Additional context for the report")

    args = parser.parse_args()
    run(args.topic, args.context)


if __name__ == "__main__":
    main()
