"""
Shared utilities — split into submodules for clarity.

Re-exports all public symbols so existing imports like
  `from research_agent.utils import strip_preamble`
continue to work unchanged.
"""

from research_agent.utils.text import get_content, extract_json, extract_json_scores, strip_preamble
from research_agent.utils.source_helpers import TIER_LABELS, TIER_LABELS_SHORT, format_tier, infer_publisher
from research_agent.utils.dates import date_vars
from research_agent.utils.outline import (
    generate_report_outline,
    parse_outline_type,
    parse_outline_sections,
    compute_depth_targets,
)
from research_agent.utils.topic import interpret_topic, generate_topic_scope

__all__ = [
    # text.py
    "get_content", "extract_json", "extract_json_scores", "strip_preamble",
    # source_helpers.py
    "TIER_LABELS", "TIER_LABELS_SHORT", "format_tier", "infer_publisher",
    # dates.py
    "date_vars",
    # outline.py
    "generate_report_outline", "parse_outline_type", "parse_outline_sections",
    "compute_depth_targets",
    # topic.py
    "interpret_topic", "generate_topic_scope",
]
