"""
Discovery-based TOC → ME data mapping.

Classifies each TOC section by structural keys (not section numbers) and
maps segment dimensions to ME data keys using the same normalization as
me_extractor.py.
"""

import re
import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


@dataclass
class SectionPlan:
    """Describes how to render one TOC section."""
    section_number: int
    title: str
    section_type: str = ""  # overview, key_insights, segment, region, competitive, appendix
    toc: dict = field(default_factory=dict)
    dimension_key: str = ""        # e.g. "by_product_type"
    dimension_name: str = ""       # e.g. "Product Type"
    segment_names: list = field(default_factory=list)
    regions: list = field(default_factory=list)
    companies: dict = field(default_factory=dict)
    subsections: list = field(default_factory=list)


def _to_key(label: str) -> str:
    """Normalise 'Product Type' -> 'by_product_type'. Same logic as me_extractor."""
    cleaned = re.sub(r'^by\s+', '', label, flags=re.IGNORECASE).strip()
    return "by_" + re.sub(r'[^a-z0-9]+', '_', cleaned.lower()).strip('_')


def _fuzzy_match_segment(toc_name: str, me_names: list[str], threshold: float = 0.65) -> str | None:
    """Find the best ME data key matching a TOC segment name."""
    best_score = 0
    best_match = None
    toc_lower = toc_name.lower().strip()

    for me_name in me_names:
        me_lower = me_name.lower().strip()
        # Exact match
        if toc_lower == me_lower:
            return me_name
        score = SequenceMatcher(None, toc_lower, me_lower).ratio()
        if score > best_score:
            best_score = score
            best_match = me_name

    return best_match if best_score >= threshold else None


def _infer_title(sec: dict) -> str:
    """Infer a section title from subsection names when the title is missing."""
    subsections = sec.get("subsections", [])
    sub_titles = [s.get("title", "") for s in subsections if s.get("title")]
    if not sub_titles:
        return "Additional Information"

    lower_titles = [t.lower() for t in sub_titles]

    # Common patterns
    if any("methodology" in t for t in lower_titles):
        return "Research Methodology"
    if any("objective" in t for t in lower_titles):
        return "Introduction"
    if any("recommendation" in t for t in lower_titles):
        return "Analyst Recommendations"
    if any("abbreviation" in t for t in lower_titles):
        return "Introduction"
    if any("about us" in t for t in lower_titles):
        return "Research Methodology"

    # Fallback: join first two subsection titles
    if len(sub_titles) == 1:
        return sub_titles[0]
    return " & ".join(sub_titles[:2])


def map_sections(toc: dict, me_data: dict) -> list[SectionPlan]:
    """Map TOC sections to ME data, producing a list of SectionPlans.

    Classification rules (discovery-based, no hardcoded section numbers):
    - Has segment_dimension starting with "Region" → region
    - Has segment_dimension (not Region) → segment
    - Has companies key → competitive
    - Title contains "Overview" → overview
    - Title contains "Insight" → key_insights
    - Otherwise → appendix
    """
    sections = toc.get("sections", [])
    plans = []

    for sec in sections:
        num = sec.get("section_number", 0)
        title = sec.get("title", "")

        # Auto-generate title if missing or placeholder
        if not title or title.strip() == "(NO TITLE)":
            title = _infer_title(sec)
            logger.info(f"  Section {num}: inferred title → '{title}'")

        plan = SectionPlan(section_number=num, title=title, toc=sec)

        # Classify
        if "companies" in sec:
            plan.section_type = "competitive"
            plan.companies = sec["companies"]

        elif "segment_dimension" in sec:
            dim = sec["segment_dimension"]
            if re.match(r'^region', dim, re.I):
                plan.section_type = "region"
                plan.dimension_key = _to_key(dim)
                plan.dimension_name = dim
                plan.regions = sec.get("regions", [])
            else:
                plan.section_type = "segment"
                plan.dimension_key = _to_key(dim)
                plan.dimension_name = dim
                plan.segment_names = sec.get("segments", [])

        elif re.search(r'overview', title, re.I):
            plan.section_type = "overview"
            plan.subsections = sec.get("subsections", [])

        elif re.search(r'insight', title, re.I):
            plan.section_type = "key_insights"
            plan.subsections = sec.get("subsections", [])

        elif re.search(r'analyst', title, re.I):
            plan.section_type = "appendix"
            plan.subsections = sec.get("subsections", [])

        else:
            plan.section_type = "appendix"
            plan.subsections = sec.get("subsections", [])

        plans.append(plan)
        logger.info(
            f"  Section {num}: type={plan.section_type}"
            f"{f', dim={plan.dimension_key}' if plan.dimension_key else ''}"
        )

    return plans


def get_me_for_dimension(me_global: dict, dimension_key: str) -> dict:
    """Get ME data for a specific dimension across all 3 row sections.

    Returns:
        {
            "volume": {"Item1": {...}, "Item2": {...}},
            "value": {"Item1": {...}, "Item2": {...}},
            "pricing": {"Item1": {...}, "Item2": {...}},  # only for by_product_type
        }
    """
    result = {}
    for section_key, output_key in [
        ("market_volume", "volume"),
        ("market_value", "value"),
        ("pricing", "pricing"),
    ]:
        section = me_global.get(section_key, {})
        dim_data = section.get(dimension_key)
        if dim_data:
            result[output_key] = dim_data
    return result


def get_me_for_region(me_data: dict, region_name: str) -> dict | None:
    """Get ME data for a specific region sheet."""
    regions = me_data.get("regions", {})
    # Try exact match first
    if region_name in regions:
        return regions[region_name]
    # Try fuzzy
    for key in regions:
        if key.lower().strip() == region_name.lower().strip():
            return regions[key]
    return None


def get_total_data(me_global: dict) -> dict:
    """Get total market volume and value data."""
    return me_global.get("total", {})


def get_snapshot_years(years: list[str]) -> list[str]:
    """Pick 3 representative years: first, ~mid (2025), last."""
    if not years:
        return []
    sorted_years = sorted(years, key=int)
    first = sorted_years[0]
    last = sorted_years[-1]
    # Find year closest to 2025
    mid = min(sorted_years, key=lambda y: abs(int(y) - 2025))
    result = list(dict.fromkeys([first, mid, last]))  # deduplicate preserving order
    return result


def get_all_years(me_global: dict) -> list[str]:
    """Extract the list of forecast years from global total data."""
    total = me_global.get("total", {})
    for kind in ("volume", "value"):
        forecast = total.get(kind, {}).get("forecast", {})
        if forecast:
            return sorted(forecast.keys(), key=int)
    return []


def get_cagr_key(me_global: dict) -> str:
    """Discover the CAGR key from global total data."""
    total = me_global.get("total", {})
    for kind in ("volume", "value"):
        data = total.get(kind, {})
        for key in data:
            if key.startswith("cagr"):
                return key
    return "cagr"
