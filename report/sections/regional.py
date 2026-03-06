"""Regional analysis section builder."""

from docx import Document

from report.styles import (
    add_section_heading, add_subsection_heading, add_sub_subsection_heading,
    add_body_text, add_chart_image, add_formatted_text,
    add_section_label, add_footer_insight_bar,
    add_slide_break,
    add_visual_bullet_list, add_section_intro_strip, add_stat_highlight_row,
)
from report.mapper import (
    SectionPlan, get_me_for_region, get_all_years,
    get_cagr_key, get_snapshot_years,
)
from report.charts import (
    chart_single_combo, chart_bar_country_comparison,
    chart_line_yoy_comparison, chart_combo_forecast,
)
from report.tables import add_forecast_table


def build_regional_section(doc: Document, plan: SectionPlan, me_data: dict, content: dict = None):
    """Build the regional analysis section.

    For each region: regional total, country bar chart, forecast tables.
    Cross-region comparison at the end.
    """
    me_global = me_data.get("global", {})
    years = get_all_years(me_global)
    cagr_key = get_cagr_key(me_global)
    snapshot_yrs = get_snapshot_years(years)

    # Compute intro metrics — region count + forecast range
    regions_in_data = me_global.get("market_value", {}).get("by_region", {})
    _ck_parts = cagr_key.split("_") if cagr_key else []
    start_yr = _ck_parts[1] if len(_ck_parts) >= 2 and _ck_parts[1].isdigit() else ""
    end_yr = years[-1] if years else ""
    intro_metrics = []
    if regions_in_data:
        intro_metrics.append({"value": str(len(regions_in_data)), "label": "Regions"})
    # Count total countries across all regions
    total_countries = 0
    for region_data in me_data.values():
        if isinstance(region_data, dict) and region_data is not me_global:
            for mv_key in ("market_value", "market_volume"):
                by_country = region_data.get(mv_key, {}).get("by_country", {})
                if by_country:
                    total_countries += len(by_country)
                    break
    if total_countries:
        intro_metrics.append({"value": str(total_countries), "label": "Countries"})
    if start_yr and end_yr:
        intro_metrics.append({"value": f"{start_yr}–{end_yr}", "label": "Forecast"})

    add_section_heading(doc, "Regional Analysis", section_label="REGIONAL ANALYSIS")
    add_section_intro_strip(doc, "Regional Analysis", plan.title or "Global Market by Region",
                            icon="◉", metrics=intro_metrics or None)

    regions_content = content.get("regions", {}) if content else {}

    # ── Cross-Region Overview Narrative ────────────────────────────────
    if content and content.get("cross_region_overview"):
        add_subsection_heading(doc, "Cross-Regional Overview")
        add_formatted_text(doc, content["cross_region_overview"])

    # ── Cross-Region Comparison ──────────────────────────────────────────
    vol_section = me_global.get("market_volume", {})
    val_section = me_global.get("market_value", {})
    region_vol = vol_section.get("by_region", {})
    region_val = val_section.get("by_region", {})

    if region_val:
        add_slide_break(doc)  # New slide for cross-region comparison
        val_unit = val_section.get("unit", "")

        # Multi-bar combo chart for all regions
        img = chart_combo_forecast(
            "Market Value by Region",
            region_val, years,
            value_label="Market Value", bar_unit=val_unit,
            show_yoy_line=False,
        )
        add_chart_image(doc, img, caption="Market Value Forecast by Region")

        # Forecast table
        add_forecast_table(
            doc, "Market Value by Region",
            region_val, years, cagr_key, unit=val_unit,
        )

    # YoY growth comparison across regions
    if region_vol and len(region_vol) > 1:
        img = chart_line_yoy_comparison(
            "YoY Growth Comparison Across Regions",
            region_vol,
        )
        add_chart_image(doc, img, caption="Year-over-Year Growth Trend by Region")

    # Footer insight bar after cross-region comparison
    if region_val:
        try:
            best_region, best_val_num = "", 0
            last_yr = years[-1] if years else None
            if last_yr:
                for name, data in region_val.items():
                    rv = float(data.get("forecast", {}).get(last_yr, 0))
                    if rv > best_val_num:
                        best_val_num = rv
                        best_region = name
            if best_region:
                add_footer_insight_bar(doc,
                    f"{best_region} leads the regional market with the highest projected value by {last_yr}, "
                    f"driven by favorable regulatory frameworks and strong demand fundamentals.")
        except (ValueError, TypeError):
            pass

    # ── Per-Region Breakdown ─────────────────────────────────────────────
    for region_info in plan.regions:
        region_name = region_info.get("name", "")
        countries = region_info.get("countries", [])

        add_slide_break(doc)  # New slide for each region
        add_section_label(doc, region_name.upper())
        add_subsection_heading(doc, region_name)

        # Render researched content for this region
        region_content = regions_content.get(region_name, {})
        if isinstance(region_content, dict) and region_content.get("overview"):
            add_formatted_text(doc, region_content["overview"])

        region_me = get_me_for_region(me_data, region_name)
        if not region_me:
            if not region_content:
                add_body_text(doc, f"Detailed market data for {region_name} is included in the dataset.")
            continue

        region_total = region_me.get("total", {})

        # Regional total value combo chart
        val_data = region_total.get("value", {})
        if val_data.get("forecast"):
            val_unit = region_me.get("market_value", {}).get("unit", "")
            img = chart_single_combo(
                f"{region_name} — Market Value",
                val_data["forecast"], val_data.get("yoy_growth", {}),
                years, bar_label="Market Value", bar_unit=val_unit,
            )
            add_chart_image(doc, img, caption=f"{region_name} Market Value Forecast")

        # Country comparison bar chart
        region_val_section = region_me.get("market_value", {})
        country_data = region_val_section.get("by_region", {})

        if country_data and snapshot_yrs:
            add_slide_break(doc)  # New slide for country comparison
            img = chart_bar_country_comparison(
                f"{region_name} — Country Comparison",
                country_data, snapshot_yrs,
                unit=region_val_section.get("unit", ""),
            )
            add_chart_image(doc, img, caption=f"{region_name} Country-Level Market Comparison")

        # Country-level content from research
        country_content = region_content.get("countries", {}) if isinstance(region_content, dict) else {}
        if country_content:
            for country_name, country_text in country_content.items():
                if country_text:
                    add_subsection_heading(doc, country_name)
                    add_formatted_text(doc, country_text)

        # Forecast tables for key dimensions within the region
        has_regional_tables = False
        for section_key, section_label in [
            ("market_volume", "Market Volume"),
            ("market_value", "Market Value"),
        ]:
            section_data = region_me.get(section_key, {})
            unit = section_data.get("unit", "")

            for dim_key, items in section_data.items():
                if dim_key == "unit" or not isinstance(items, dict):
                    continue
                if not has_regional_tables:
                    add_slide_break(doc)  # New slide only when tables exist
                    has_regional_tables = True
                dim_name = dim_key.replace("by_", "").replace("_", " ").title()
                add_forecast_table(
                    doc, f"{region_name} — {section_label} by {dim_name}",
                    items, years, cagr_key, unit=unit,
                )


