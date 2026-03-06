"""
CLI entry point + orchestrator for .docx report generation.

Usage:
    python -m report.generate inputs/Global_Utility_Markers_Market.json
    python -m report.generate inputs/Global_Utility_Markers_Market.json -o outputs/report.docx
    python -m report.generate inputs/Global_Utility_Markers_Market.json --no-content  (charts+tables only)
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from report.styles import create_styled_document, add_section_heading, add_subsection_heading, add_body_text, set_citation_registry, set_report_title, add_section_intro_strip
from report.mapper import map_sections
from report.sections.cover import build_cover
from report.sections.overview import build_overview
from report.sections.key_insights import build_key_insights
from report.sections.segment import build_segment_section
from report.sections.regional import build_regional_section
from report.sections.competitive import build_competitive_section
from report.sections.appendix import build_appendix_section

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger(__name__)
console = Console()


def _build_section(doc, plan, me_data, content_store):
    """Route a plan to its builder with appropriate arguments."""
    content = content_store.get(plan.section_number, {})
    stype = plan.section_type

    if stype == "overview":
        build_overview(doc, plan, me_data.get("global", {}), content=content)
    elif stype == "key_insights":
        build_key_insights(doc, plan, me_data.get("global", {}), content=content)
    elif stype == "segment":
        build_segment_section(doc, plan, me_data.get("global", {}), content=content)
    elif stype == "region":
        build_regional_section(doc, plan, me_data, content=content)
    elif stype == "competitive":
        build_competitive_section(doc, plan, content=content)
    elif stype == "appendix":
        build_appendix_section(doc, plan, content=content)
    else:
        build_appendix_section(doc, plan, content=content)


def _build_bibliography(doc, citations_mgr, content_store):
    """Build bibliography section listing ALL research sources."""
    if not citations_mgr or citations_mgr.count == 0:
        return

    from report.styles import add_bibliography_entry

    # List ALL registered sources (deduplicated by URL)
    citations = citations_mgr.citations
    seen_urls = set()
    entries = []
    for c in sorted(citations, key=lambda x: x["id"]):
        if c["url"] in seen_urls:
            continue
        seen_urls.add(c["url"])
        entries.append(c)

    if not entries:
        return

    add_section_heading(doc, "Bibliography")
    add_section_intro_strip(doc, "Bibliography", f"{len(entries)} references cited in this report", icon="◈",
                            metrics=[{"value": str(len(entries)), "label": "References"}])

    for c in entries:
        add_bibliography_entry(
            doc,
            citation_id=c["id"],
            title=c.get("title", "Untitled"),
            publisher=c.get("publisher", ""),
            date=c.get("date", ""),
            url=c.get("url", ""),
        )


async def generate_report(json_path: str, output_path: str | None = None, skip_content: bool = False):
    """Generate a .docx report from extracted TOC + ME JSON data.

    Args:
        json_path: Path to input JSON (TOC + ME data).
        output_path: Optional output .docx path.
        skip_content: If True, skip LLM content generation (charts+tables only).
    """
    json_path = Path(json_path)
    if not json_path.exists():
        console.print(f"[red]Error: JSON file not found: {json_path}[/red]")
        sys.exit(1)

    console.print(Panel(
        f"[bold]Input:[/bold] {json_path}",
        title="[bold green]Report Generation[/bold green]",
        border_style="green",
    ))

    # Load data
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    toc = data.get("toc", {})
    me_data = data.get("me_data", {})

    report_title = toc.get("report_title", "Market Research Report")
    subtitle = toc.get("subtitle", "")

    # Map sections
    console.print("\n[bold]Mapping TOC sections to ME data...[/bold]")
    plans = map_sections(toc, me_data)
    console.print(f"  Mapped [bold]{len(plans)}[/bold] sections")

    for p in plans:
        console.print(f"    S{p.section_number}: {p.section_type} — {p.title[:60] if p.title else '(no title)'}")

    # ── Content Generation (async) ─────────────────────────────────────
    content_store = {}
    citations_mgr = None

    if not skip_content:
        console.print("\n[bold]Generating content with LLM + web research...[/bold]")
        try:
            from report.content.engine import ContentEngine

            engine = ContentEngine(
                topic=report_title,
                plans=plans,
                me_data=me_data,
                toc=toc,
            )

            def progress_cb(msg):
                console.print(f"  [dim]{msg}[/dim]")

            content_store = await engine.generate_all(progress_callback=progress_cb)
            citations_mgr = engine.citations

            total_chars = sum(len(str(v)) for v in content_store.values())
            console.print(f"  Content generated: [bold]{total_chars:,}[/bold] characters across [bold]{len(content_store)}[/bold] sections")
            console.print(f"  Citations collected: [bold]{citations_mgr.count}[/bold]")
        except Exception as e:
            logger.error(f"Content generation failed: {e}")
            console.print(f"[yellow]Warning: Content generation failed ({e}). Proceeding with charts+tables only.[/yellow]")
            content_store = {}
    else:
        console.print("\n[dim]Skipping content generation (--no-content flag)[/dim]")

    # ── Build Document ─────────────────────────────────────────────────
    console.print("\n[bold]Building document...[/bold]")

    # Set citation registry so inline [src_xxx_nnn] become clickable hyperlinks
    if citations_mgr and citations_mgr.count > 0:
        set_citation_registry(citations_mgr.citations)
        console.print(f"  Citation registry loaded: [bold]{citations_mgr.count}[/bold] sources")

    doc = create_styled_document()
    set_report_title(report_title)

    # Cover page
    build_cover(doc, report_title, subtitle, plans, me_data=me_data)

    # Build each section
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Building sections...", total=len(plans))

        for plan in sorted(plans, key=lambda p: p.section_number):
            desc = f"Section {plan.section_number}: {plan.section_type}"
            progress.update(task, description=desc)

            try:
                _build_section(doc, plan, me_data, content_store)
            except Exception as e:
                logger.error(f"Error building section {plan.section_number}: {e}")
                add_section_heading(doc, plan.title or f"Section {plan.section_number}")
                add_section_intro_strip(doc, plan.title or f"Section {plan.section_number}", "Content generation error")
                add_body_text(doc, f"[Section content generation encountered an error: {e}]")

            progress.advance(task)

    # Bibliography
    if citations_mgr and citations_mgr.count > 0:
        console.print("  Building bibliography...")
        _build_bibliography(doc, citations_mgr, content_store)

    # ── Save ───────────────────────────────────────────────────────────
    if output_path is None:
        from datetime import datetime
        output_dir = Path("outputs")
        output_dir.mkdir(exist_ok=True)
        safe_title = report_title.replace(" ", "_")[:60]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"{safe_title}_{timestamp}.docx"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    doc.save(str(output_path))

    file_size = output_path.stat().st_size
    console.print(Panel(
        f"[bold]Report:[/bold] {report_title}\n"
        f"[bold]Sections:[/bold] {len(plans)}\n"
        f"[bold]Content sections:[/bold] {len(content_store)}\n"
        f"[bold]Citations:[/bold] {citations_mgr.count if citations_mgr else 0}\n"
        f"[bold]Output:[/bold] {output_path}\n"
        f"[bold]Size:[/bold] {file_size / (1024 * 1024):.1f} MB",
        title="[bold green]Report Generated[/bold green]",
        border_style="green",
    ))

    return str(output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Generate .docx report from extracted TOC + ME data"
    )
    parser.add_argument("json_input", help="Path to the JSON file from extract_inputs.py")
    parser.add_argument("--output", "-o", default=None, help="Output .docx path (default: outputs/<title>.docx)")
    parser.add_argument("--no-content", action="store_true", help="Skip LLM content generation (charts+tables only)")

    args = parser.parse_args()
    asyncio.run(generate_report(args.json_input, args.output, skip_content=args.no_content))


if __name__ == "__main__":
    main()
