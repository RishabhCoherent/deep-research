"""
CLI tool to extract TOC and Market Estimate data from PPTX and XLSX files.

Usage:
    python extract_inputs.py \
        --pptx "path/to/Report.pptx" \
        --xlsx "path/to/ME_Report.xlsx" \
        --output "inputs/output.json"
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel

from extractors.toc_extractor import extract_toc
from extractors.me_extractor import extract_me

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger(__name__)
console = Console()


def run(pptx_path: str, xlsx_path: str, output_path: str | None = None):
    """Extract TOC and ME data, combine into a single JSON file."""
    console.print(Panel(
        f"[bold]PPTX:[/bold] {pptx_path}\n"
        f"[bold]XLSX:[/bold] {xlsx_path}",
        title="[bold green]Input Extraction[/bold green]",
        border_style="green",
    ))

    # Extract TOC
    console.print("\n[bold]Extracting Table of Contents...[/bold]")
    toc_data = extract_toc(pptx_path)
    section_count = len(toc_data.get("sections", []))
    console.print(f"  Found [bold]{section_count}[/bold] sections")

    # Extract ME data
    console.print("\n[bold]Extracting Market Estimate data...[/bold]")
    me_data = extract_me(xlsx_path)
    sheets = len(me_data.get("data_sheets", []))
    console.print(f"  Processed [bold]{sheets}[/bold] sheets")

    # Combine
    combined = {
        "extracted_at": datetime.now().isoformat(),
        "source_files": {
            "pptx": Path(pptx_path).name,
            "xlsx": Path(xlsx_path).name,
        },
        "toc": toc_data,
        "me_data": me_data,
    }

    # Determine output path
    if output_path is None:
        output_dir = Path("inputs")
        output_dir.mkdir(exist_ok=True)
        safe_title = toc_data.get("report_title", "report").replace(" ", "_")[:60]
        output_path = output_dir / f"{safe_title}.json"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)

    # Summary
    file_size = output_path.stat().st_size
    console.print(Panel(
        f"[bold]Report:[/bold] {toc_data.get('report_title', 'Unknown')}\n"
        f"[bold]TOC Sections:[/bold] {section_count}\n"
        f"[bold]ME Sheets:[/bold] {sheets}\n"
        f"[bold]Output:[/bold] {output_path}\n"
        f"[bold]Size:[/bold] {file_size / 1024:.1f} KB",
        title="[bold green]Extraction Complete[/bold green]",
        border_style="green",
    ))

    return combined


def main():
    parser = argparse.ArgumentParser(
        description="Extract Table of Contents and Market Estimate data from report files"
    )
    parser.add_argument("--pptx", required=True, help="Path to the PPTX report file (contains TOC)")
    parser.add_argument("--xlsx", required=True, help="Path to the XLSX ME file (contains market estimates)")
    parser.add_argument("--output", "-o", default=None, help="Output JSON path (default: inputs/<title>.json)")

    args = parser.parse_args()
    run(args.pptx, args.xlsx, args.output)


if __name__ == "__main__":
    main()
