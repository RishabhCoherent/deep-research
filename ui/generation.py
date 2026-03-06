"""Async bridge — runs report generation in a background thread with progress queue."""

import asyncio
import logging
import os
import queue
import tempfile
import threading
from datetime import datetime

from report.mapper import map_sections
from report.styles import create_styled_document, set_citation_registry
from report.sections.cover import build_cover
from report.generate import _build_section, _build_bibliography
from report.content.engine import ContentEngine

logger = logging.getLogger(__name__)


def start_generation(extracted_data: dict, skip_content: bool = False,
                     topic_override: str = "") -> tuple:
    """Launch report generation in a background thread.

    Returns: (thread, progress_queue, result_holder)
    """
    progress_queue = queue.Queue()
    result_holder = {}

    # Save to outputs/ folder in project directory
    toc = extracted_data.get("toc", {})
    safe_title = toc.get("report_title", "report").replace(" ", "_")[:60]
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"{safe_title}_{timestamp}.docx")

    thread = threading.Thread(
        target=_thread_target,
        args=(extracted_data, output_path, skip_content, topic_override,
              progress_queue, result_holder),
        daemon=True,
    )
    thread.start()

    return thread, progress_queue, result_holder


def _thread_target(extracted_data, output_path, skip_content, topic_override,
                   progress_queue, result_holder):
    """Background thread target — runs its own asyncio event loop."""

    async def _run():
        toc = extracted_data["toc"]
        me_data = extracted_data["me_data"]
        report_title = topic_override or toc.get("report_title", "Market Research Report")
        subtitle = toc.get("subtitle", "")

        # Map sections
        progress_queue.put(("status", "Mapping TOC sections to ME data..."))
        all_plans = map_sections(toc, me_data)
        progress_queue.put(("info", f"Mapped {len(all_plans)} sections total"))

        # Filter: keep first 3 sections + last section only
        sorted_all = sorted(all_plans, key=lambda p: p.section_number)
        plans = sorted_all[:3] + ([sorted_all[-1]] if len(sorted_all) > 3 else [])
        skipped = len(all_plans) - len(plans)
        progress_queue.put(("info", f"Generating {len(plans)} sections (skipping {skipped} middle sections)"))

        # Content generation
        content_store = {}
        citations_mgr = None

        if not skip_content:
            progress_queue.put(("status", "Generating content with LLM + web research..."))
            try:
                engine = ContentEngine(
                    topic=report_title,
                    plans=plans,
                    me_data=me_data,
                    toc=toc,
                )

                def progress_cb(msg):
                    progress_queue.put(("progress", msg))

                content_store = await engine.generate_all(progress_callback=progress_cb)
                citations_mgr = engine.citations

                total_chars = sum(len(str(v)) for v in content_store.values())
                cit_count = citations_mgr.count if citations_mgr else 0
                progress_queue.put(("info", f"Content: {total_chars:,} chars | Citations: {cit_count}"))
            except Exception as e:
                progress_queue.put(("warning", f"Content generation failed: {e}. Proceeding with charts only."))
                content_store = {}
        else:
            progress_queue.put(("info", "Skipping LLM content (charts + tables only)"))

        # Build document
        progress_queue.put(("status", "Building document..."))

        # Set citation registry so inline [src_xxx_nnn] become clickable hyperlinks
        if citations_mgr and citations_mgr.count > 0:
            set_citation_registry(citations_mgr.citations)
            progress_queue.put(("info", f"Citation registry loaded: {citations_mgr.count} sources"))

        doc = create_styled_document()
        build_cover(doc, report_title, subtitle, all_plans, me_data=me_data)

        for i, plan in enumerate(plans):
            progress_queue.put(("progress", f"Building section {i + 1}/{len(plans)}: S{plan.section_number} ({plan.section_type}) [{plan.title}]"))
            try:
                _build_section(doc, plan, me_data, content_store)
            except Exception as e:
                progress_queue.put(("warning", f"Section {plan.section_number} error: {e}"))
                from report.styles import add_section_heading, add_body_text
                add_section_heading(doc, plan.title or f"Section {plan.section_number}")
                add_body_text(doc, f"[Section generation error: {e}]")

        # Bibliography
        if citations_mgr and citations_mgr.count > 0:
            progress_queue.put(("progress", "Building bibliography..."))
            _build_bibliography(doc, citations_mgr, content_store)

        # Save
        progress_queue.put(("status", "Saving document..."))
        doc.save(output_path)

        file_size = os.path.getsize(output_path)
        progress_queue.put(("info", f"Report saved: {file_size / (1024 * 1024):.1f} MB"))

        return output_path

    try:
        result_path = asyncio.run(_run())
        result_holder["success"] = True
        result_holder["output_path"] = result_path
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        result_holder["success"] = False
        result_holder["error"] = str(e)
    finally:
        progress_queue.put(("done", ""))


def drain_queue(progress_queue: queue.Queue) -> list:
    """Drain all messages from the progress queue."""
    messages = []
    while True:
        try:
            msg = progress_queue.get_nowait()
            messages.append(msg)
        except queue.Empty:
            break
    return messages
