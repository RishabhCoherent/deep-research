"""Generic segment section builder — reused for all segment dimensions."""

from docx import Document

from report.styles import (
    add_section_heading, add_subsection_heading, add_sub_subsection_heading,
    add_body_text, add_chart_image, add_formatted_text,
    add_footer_insight_bar,
    add_chart_with_sidebar, add_cagr_analysis_card,
    add_slide_break,
    add_visual_bullet_list, add_section_intro_strip,
)
from report.mapper import (
    SectionPlan, get_me_for_dimension, get_all_years,
    get_cagr_key, get_snapshot_years, _fuzzy_match_segment,
)
from report.charts import (
    chart_combo_forecast, chart_stacked_100_bps,
    chart_single_combo, chart_line_yoy_comparison,
)
from report.tables import add_forecast_table, add_yoy_table, add_pct_share_table


def build_segment_section(doc: Document, plan: SectionPlan, me_global: dict, content: dict = None):
    """Build a segment analysis section for one dimension.

    Generates: narrative content, BPS chart, per-item forecast tables + combo charts,
    pricing tables (if applicable), YoY comparison.
    """
    dim_key = plan.dimension_key
    dim_name = plan.dimension_name
    title = plan.title or f"Market Analysis by {dim_name}"

    years = get_all_years(me_global)
    cagr_key = get_cagr_key(me_global)
    snapshot_yrs = get_snapshot_years(years)

    # Extract forecast start year from CAGR key
    _ck_parts = cagr_key.split("_") if cagr_key else []
    forecast_start_yr = _ck_parts[1] if len(_ck_parts) >= 2 and _ck_parts[1].isdigit() else None

    dim_data = get_me_for_dimension(me_global, dim_key)
    vol_items = dim_data.get("volume", {})
    val_items = dim_data.get("value", {})

    # Compute intro metrics
    seg_count = max(len(vol_items), len(val_items))
    start_yr = forecast_start_yr or (years[0] if years else "")
    end_yr = years[-1] if years else ""
    intro_metrics = []
    if seg_count:
        intro_metrics.append({"value": str(seg_count), "label": "Segments"})
    if start_yr and end_yr:
        intro_metrics.append({"value": f"{start_yr}–{end_yr}", "label": "Forecast"})
    if years:
        intro_metrics.append({"value": str(len(years)), "label": "Data Points"})

    add_section_heading(doc, f"By {dim_name}", section_label="SEGMENT ANALYSIS")
    add_section_intro_strip(doc, f"By {dim_name}", title, icon="◈",
                            metrics=intro_metrics or None)
    pricing_items = dim_data.get("pricing", {})

    vol_unit = me_global.get("market_volume", {}).get("unit", "")
    val_unit = me_global.get("market_value", {}).get("unit", "")
    price_unit = me_global.get("pricing", {}).get("unit", "")

    items_content = content.get("items", {}) if content else {}

    # ── Dimension Overview Narrative ───────────────────────────────────
    if content and content.get("dimension_overview"):
        add_subsection_heading(doc, f"{dim_name} Overview")
        add_formatted_text(doc, content["dimension_overview"])

    # ── BPS Stacked Chart (percentage share) ─────────────────────────────
    if vol_items:
        add_slide_break(doc)  # New slide for BPS chart
        img = chart_stacked_100_bps(
            f"Market Volume Share by {dim_name} (%)",
            vol_items, years,
        )
        add_chart_image(doc, img, caption=f"Market Volume Share Distribution by {dim_name}")

        # Footer insight bar highlighting the dominant segment
        try:
            last_yr = years[-1] if years else None
            if last_yr:
                best_name, best_share = "", 0
                for name, data in vol_items.items():
                    share = data.get("percentage_share", {}).get(last_yr, 0)
                    try:
                        if float(share) > best_share:
                            best_share = float(share)
                            best_name = name
                    except (ValueError, TypeError):
                        continue
                if best_name and best_share > 0:
                    add_footer_insight_bar(doc,
                        f"{best_name} is the dominant segment, commanding {best_share * 100:.1f}% "
                        f"of total market volume by {last_yr}.")
        except Exception:
            pass

    # ── Market Volume Forecast Table ─────────────────────────────────────
    if vol_items:
        add_slide_break(doc)  # New slide for volume table
        add_forecast_table(
            doc, f"Market Volume by {dim_name}",
            vol_items, years, cagr_key, unit=vol_unit,
            forecast_start_yr=forecast_start_yr,
        )

    # ── Market Value Forecast Table ──────────────────────────────────────
    if val_items:
        add_slide_break(doc)  # New slide for value table
        add_forecast_table(
            doc, f"Market Value by {dim_name}",
            val_items, years, cagr_key, unit=val_unit,
            forecast_start_yr=forecast_start_yr,
        )

    # ── Per-Item Combo Charts + Content ────────────────────────────────
    me_item_names = list(vol_items.keys()) if vol_items else list(val_items.keys())

    for toc_segment in plan.segment_names:
        # Fuzzy match TOC segment name to ME data key
        matched = _fuzzy_match_segment(toc_segment, me_item_names)
        if not matched:
            continue

        add_slide_break(doc)  # New slide for each segment
        add_subsection_heading(doc, toc_segment)

        # Render researched content for this item
        item_content = items_content.get(toc_segment, {})
        if isinstance(item_content, dict):
            if item_content.get("analysis"):
                add_formatted_text(doc, item_content["analysis"])
        elif isinstance(item_content, str) and item_content:
            add_formatted_text(doc, item_content)

        # Volume combo chart with CAGR sidebar
        if matched in vol_items:
            item_data = vol_items[matched]
            img = chart_single_combo(
                f"{toc_segment} — Market Volume",
                item_data.get("forecast", {}),
                item_data.get("yoy_growth", {}),
                years, bar_label="Volume", bar_unit=vol_unit,
                fig_size=(6.0, 3.8), forecast_start_yr=forecast_start_yr,
            )
            vol_cagr = item_data.get(cagr_key, "")
            fc = item_data.get("forecast", {})
            start_yr = years[0] if years else ""
            end_yr = years[-1] if years else ""
            start_val = fc.get(start_yr, "")
            end_val = fc.get(end_yr, "")

            def _build_vol_sidebar(cell, _cagr=vol_cagr, _sv=start_val, _ev=end_val,
                                   _sy=start_yr, _ey=end_yr, _u=vol_unit):
                from_label = f"{_sv} {_u} ({_sy})" if _sv else _sy
                to_label = f"{_ev} {_u} ({_ey})" if _ev else _ey
                add_cagr_analysis_card(cell, _cagr, from_label, to_label, label="CAGR")

            add_chart_with_sidebar(doc, img, _build_vol_sidebar,
                                   chart_width=5.8, sidebar_width=3.7,
                                   caption=f"{toc_segment} Market Volume Forecast")

        # Value combo chart with CAGR sidebar
        if matched in val_items:
            item_data = val_items[matched]
            img = chart_single_combo(
                f"{toc_segment} — Market Value",
                item_data.get("forecast", {}),
                item_data.get("yoy_growth", {}),
                years, bar_label="Value", bar_unit=val_unit,
                fig_size=(6.0, 3.8), forecast_start_yr=forecast_start_yr,
            )
            val_cagr = item_data.get(cagr_key, "")
            fc = item_data.get("forecast", {})
            start_yr = years[0] if years else ""
            end_yr = years[-1] if years else ""
            start_val = fc.get(start_yr, "")
            end_val = fc.get(end_yr, "")

            def _build_val_sidebar(cell, _cagr=val_cagr, _sv=start_val, _ev=end_val,
                                   _sy=start_yr, _ey=end_yr, _u=val_unit):
                from_label = f"{_sv} {_u} ({_sy})" if _sv else _sy
                to_label = f"{_ev} {_u} ({_ey})" if _ev else _ey
                add_cagr_analysis_card(cell, _cagr, from_label, to_label, label="CAGR")

            add_chart_with_sidebar(doc, img, _build_val_sidebar,
                                   chart_width=5.8, sidebar_width=3.7,
                                   caption=f"{toc_segment} Market Value Forecast")

        # Pricing table for this segment (only for by_product_type usually)
        if matched in pricing_items:
            item_data = pricing_items[matched]
            img = chart_single_combo(
                f"{toc_segment} — Pricing",
                item_data.get("forecast", {}),
                item_data.get("yoy_growth", {}),
                years, bar_label="Price", bar_unit=price_unit,
                bar_color="#FFC000",
            )
            add_chart_image(doc, img, caption=f"{toc_segment} Pricing Trend")

    # ── YoY Growth Comparison (all items) ────────────────────────────────
    items_for_yoy = vol_items if vol_items else val_items
    if items_for_yoy and len(items_for_yoy) > 1:
        add_slide_break(doc)  # New slide for YoY comparison
        add_subsection_heading(doc, f"YoY Growth Comparison — {dim_name}")
        img = chart_line_yoy_comparison(
            f"YoY Growth Comparison by {dim_name}",
            items_for_yoy,
        )
        add_chart_image(doc, img, caption=f"Year-over-Year Growth Comparison across {dim_name} segments")

        add_yoy_table(doc, f"YoY Growth by {dim_name}", items_for_yoy)

    # ── Percentage Share Table ───────────────────────────────────────────
    if vol_items:
        add_pct_share_table(doc, f"Market Volume Share by {dim_name}", vol_items)

    # ── Comparison Narrative ─────────────────────────────────────────────
    if content and content.get("comparison_narrative"):
        add_subsection_heading(doc, f"Comparative Analysis — {dim_name}")
        add_formatted_text(doc, content["comparison_narrative"])


