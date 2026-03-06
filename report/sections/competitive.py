"""Competitive Landscape section builder."""

from docx import Document

from report.styles import (
    add_section_heading, add_subsection_heading, add_sub_subsection_heading,
    add_body_text, add_formatted_text, set_cell_shading,
    add_footer_insight_bar,
    add_slide_break,
    add_company_profile_card,
    add_visual_bullet_list,
    add_section_intro_strip,
    add_icon_feature_cards,
    NAVY, GOLD, STEEL_GRAY, DARK_TEXT, WHITE,
    DARK_BLUE, ACCENT_BLUE,
    FONT_BODY,
)
from report.mapper import SectionPlan


def build_competitive_section(doc: Document, plan: SectionPlan, content: dict = None):
    """Build the Competitive Landscape section with company tables + researched content."""
    companies = plan.companies
    total_companies = sum(len(cl) for cl in companies.values()) if companies else 0
    num_regions = len(companies) if companies else 0
    intro_metrics = []
    if total_companies:
        intro_metrics.append({"value": str(total_companies), "label": "Companies"})
    if num_regions:
        intro_metrics.append({"value": str(num_regions), "label": "Regions"})

    add_section_heading(doc, plan.title or "Competitive Landscape", section_label="COMPETITIVE LANDSCAPE")
    add_section_intro_strip(doc, "Competitive Landscape",
                            "Key players, market positioning, and strategic dynamics",
                            icon="◎", metrics=intro_metrics or None)

    # ── Landscape Overview Narrative ──────────────────────────────────
    if content and content.get("landscape_overview"):
        add_subsection_heading(doc, "Competitive Overview")
        add_formatted_text(doc, content["landscape_overview"])
    else:
        add_body_text(doc,
            "This section provides a comprehensive overview of the competitive landscape, "
            "including key market players segmented by geographic presence."
        )

    companies = plan.companies
    if not companies:
        add_body_text(doc, "Company profiles and competitive analysis are included in the full report.")
        return

    companies_content = content.get("companies", {}) if content else {}

    for group_key, company_list in companies.items():
        if not company_list:
            continue

        add_slide_break(doc)  # New slide for each geographic group

        # Format group name: "north_america" -> "North America Players"
        group_name = group_key.replace("_", " ").title()
        add_subsection_heading(doc, f"{group_name} Players")

        # Build visual feature cards for companies in this group
        feature_cards = [
            {"icon": "◈", "title": company, "desc": f"{group_name} competitor"}
            for company in company_list
        ]
        add_icon_feature_cards(doc, feature_cards, cols=min(3, len(feature_cards)))

        # Per-company profiles from research — visual profile cards
        for company in company_list:
            profile = companies_content.get(company, "")
            if profile:
                add_company_profile_card(doc, company, profile)

    # ── Positioning Narrative ─────────────────────────────────────────
    if content and content.get("positioning_narrative"):
        add_slide_break(doc)  # New slide for positioning
        add_subsection_heading(doc, "Competitive Positioning")
        add_formatted_text(doc, content["positioning_narrative"])

    # Footer insight bar summarizing competitive dynamics
    total_companies = sum(len(cl) for cl in companies.values())
    if total_companies > 0:
        add_footer_insight_bar(doc,
            f"The competitive landscape features {total_companies} key players across "
            f"{len(companies)} geographic segments, with market consolidation driven by "
            f"strategic partnerships, product innovation, and regional expansion.")


