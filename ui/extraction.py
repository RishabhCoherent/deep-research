"""Extraction logic — save uploads to temp files, run extractors."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st

from extractors.toc_extractor import extract_toc
from extractors.me_extractor import extract_me
from report.mapper import map_sections


def save_uploaded_file(uploaded_file) -> str:
    """Save a Streamlit UploadedFile to a temp file. Returns path."""
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, uploaded_file.name)
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path


def run_extraction(pptx_file, xlsx_file) -> dict:
    """Extract TOC + ME data from uploaded PPTX and XLSX files.

    Returns combined data dict (same structure as extract_inputs.py output).
    """
    pptx_path = save_uploaded_file(pptx_file)
    xlsx_path = save_uploaded_file(xlsx_file)

    toc_data = extract_toc(pptx_path)
    me_data = extract_me(xlsx_path)

    combined = {
        "extracted_at": datetime.now().isoformat(),
        "source_files": {
            "pptx": pptx_file.name,
            "xlsx": xlsx_file.name,
        },
        "toc": toc_data,
        "me_data": me_data,
    }

    return combined


def run_extraction_from_paths(pptx_path: str, xlsx_path: str) -> dict:
    """Extract TOC + ME data from local file paths directly."""
    pptx_path = pptx_path.strip().strip('"').strip("'")
    xlsx_path = xlsx_path.strip().strip('"').strip("'")

    if not os.path.isfile(pptx_path):
        raise FileNotFoundError(f"PPTX file not found: {pptx_path}")
    if not os.path.isfile(xlsx_path):
        raise FileNotFoundError(f"XLSX file not found: {xlsx_path}")

    toc_data = extract_toc(pptx_path)
    me_data = extract_me(xlsx_path)

    combined = {
        "extracted_at": datetime.now().isoformat(),
        "source_files": {
            "pptx": os.path.basename(pptx_path),
            "xlsx": os.path.basename(xlsx_path),
        },
        "toc": toc_data,
        "me_data": me_data,
    }

    return combined


def load_json_from_path(json_path: str) -> dict:
    """Load and validate a pre-extracted JSON from a local file path."""
    json_path = json_path.strip().strip('"').strip("'")

    if not os.path.isfile(json_path):
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "toc" not in data:
        raise ValueError("JSON missing 'toc' key")
    if "me_data" not in data:
        raise ValueError("JSON missing 'me_data' key")

    return data


def load_json_upload(json_file) -> dict:
    """Load and validate a pre-extracted JSON file."""
    data = json.load(json_file)

    if "toc" not in data:
        raise ValueError("JSON missing 'toc' key")
    if "me_data" not in data:
        raise ValueError("JSON missing 'me_data' key")

    return data


def get_extraction_summary(data: dict) -> dict:
    """Extract summary info from the combined data dict."""
    toc = data.get("toc", {})
    me_data = data.get("me_data", {})

    report_title = toc.get("report_title", "Unknown")
    sections = toc.get("sections", [])
    sheets = me_data.get("data_sheets", [])

    # Build section plans for preview
    plans = map_sections(toc, me_data)

    plan_summaries = []
    for p in sorted(plans, key=lambda x: x.section_number):
        title_short = p.title[:70] if p.title else "(no title)"
        plan_summaries.append({
            "number": p.section_number,
            "type": p.section_type,
            "title": title_short,
        })

    return {
        "report_title": report_title,
        "subtitle": toc.get("subtitle", ""),
        "section_count": len(sections),
        "sheet_count": len(sheets),
        "sheets": sheets,
        "plans": plan_summaries,
        "plan_objects": plans,
    }
