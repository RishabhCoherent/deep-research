"""
Auto-generate data-driven insight sentences from ME numbers.

NO LLM calls — pure formatting from data. Fast, deterministic, always accurate.
Works for any market topic.
"""

from __future__ import annotations


def _fmt_val(val, decimals: int = 2) -> str:
    """Format a number with commas."""
    try:
        return f"{float(val):,.{decimals}f}"
    except (ValueError, TypeError):
        return str(val)


def _fmt_pct(val) -> str:
    """Format decimal as percentage."""
    try:
        return f"{float(val) * 100:.2f}%"
    except (ValueError, TypeError):
        return str(val)


def _get_unit_label(unit: str) -> str:
    """Format unit for display."""
    if not unit:
        return ""
    return f" ({unit})"


# ─── Total Market Insights ───────────────────────────────────────────────────


def generate_total_insights(total_data: dict, years: list[str], cagr_key: str,
                            vol_unit: str = "", val_unit: str = "") -> list[str]:
    """Generate insight sentences from total market volume/value data."""
    insights = []
    first_yr = years[0] if years else ""
    last_yr = years[-1] if years else ""

    for kind, label, unit in [("volume", "market volume", vol_unit), ("value", "market value", val_unit)]:
        data = total_data.get(kind, {})
        forecast = data.get("forecast", {})
        cagr = data.get(cagr_key)

        if not forecast:
            continue

        first_val = forecast.get(first_yr)
        last_val = forecast.get(last_yr)

        if first_val and last_val and cagr:
            insights.append(
                f"The global {label} is projected to grow from {_fmt_val(first_val)}{_get_unit_label(unit)} "
                f"in {first_yr} to {_fmt_val(last_val)}{_get_unit_label(unit)} in {last_yr}, "
                f"registering a CAGR of {_fmt_pct(cagr)} during the forecast period ({first_yr}-{last_yr})."
            )

        # YoY peak and trend
        yoy = data.get("yoy_growth", {})
        if yoy:
            max_yr = max(yoy, key=lambda y: float(yoy[y]))
            min_yr = min(yoy, key=lambda y: float(yoy[y]))
            insights.append(
                f"Year-over-year growth for {label} is expected to peak at {_fmt_pct(yoy[max_yr])} in {max_yr}, "
                f"while the lowest growth rate of {_fmt_pct(yoy[min_yr])} is projected for {min_yr}."
            )

    return insights


# ─── Segment Insights ────────────────────────────────────────────────────────


def generate_segment_insights(
    dim_name: str,
    items: dict,
    years: list[str],
    cagr_key: str,
    unit: str = "",
) -> dict[str, list[str]]:
    """Generate per-item insight sentences for a segment dimension.

    Returns: {"Item Name": ["insight1", "insight2", ...]}
    """
    if not items or not years:
        return {}

    first_yr = years[0]
    last_yr = years[-1]
    mid_yr = min(years, key=lambda y: abs(int(y) - 2025))

    result = {}

    # Calculate rankings
    rankings_first = {}
    rankings_last = {}
    cagr_rankings = {}

    for name, data in items.items():
        forecast = data.get("forecast", {})
        if forecast.get(first_yr) is not None:
            rankings_first[name] = float(forecast[first_yr])
        if forecast.get(last_yr) is not None:
            rankings_last[name] = float(forecast[last_yr])
        if data.get(cagr_key) is not None:
            cagr_rankings[name] = float(data[cagr_key])

    sorted_by_size = sorted(rankings_last.items(), key=lambda x: x[1], reverse=True)
    sorted_by_cagr = sorted(cagr_rankings.items(), key=lambda x: x[1], reverse=True)

    for name, data in items.items():
        insights = []
        forecast = data.get("forecast", {})
        cagr = data.get(cagr_key)
        pct_share = data.get("percentage_share", {})
        yoy = data.get("yoy_growth", {})

        first_val = forecast.get(first_yr)
        last_val = forecast.get(last_yr)

        # Growth projection
        if first_val and last_val and cagr:
            insights.append(
                f"The {name} segment is projected to grow from {_fmt_val(first_val)}{_get_unit_label(unit)} "
                f"in {first_yr} to {_fmt_val(last_val)}{_get_unit_label(unit)} in {last_yr}, "
                f"at a CAGR of {_fmt_pct(cagr)}."
            )

        # Market share
        share_mid = pct_share.get(mid_yr)
        share_last = pct_share.get(last_yr)
        if share_mid:
            insights.append(
                f"{name} is estimated to account for {_fmt_pct(share_mid)} of the total {dim_name.lower()} "
                f"market share in {mid_yr}."
            )

        # Ranking
        if sorted_by_size:
            rank = next((i + 1 for i, (n, _) in enumerate(sorted_by_size) if n == name), None)
            if rank == 1:
                insights.append(f"{name} is the largest segment by {dim_name.lower()}, maintaining market leadership through {last_yr}.")
            elif rank == len(sorted_by_size):
                insights.append(f"{name} represents the smallest segment by {dim_name.lower()} in the market.")

        # Fastest/slowest growing
        if sorted_by_cagr:
            cagr_rank = next((i + 1 for i, (n, _) in enumerate(sorted_by_cagr) if n == name), None)
            if cagr_rank == 1 and len(sorted_by_cagr) > 1:
                insights.append(f"{name} is projected to be the fastest-growing segment with the highest CAGR of {_fmt_pct(cagr)} during the forecast period.")

        # Share trend
        if share_mid and share_last:
            share_change = float(share_last) - float(share_mid)
            if abs(share_change) > 0.005:
                direction = "increase" if share_change > 0 else "decrease"
                insights.append(
                    f"The market share of {name} is expected to {direction} from {_fmt_pct(share_mid)} in {mid_yr} "
                    f"to {_fmt_pct(share_last)} in {last_yr}."
                )

        result[name] = insights

    return result


def generate_dimension_summary(dim_name: str, items: dict, years: list[str], cagr_key: str) -> str:
    """Generate a summary paragraph comparing all items in a dimension."""
    if not items or not years:
        return ""

    last_yr = years[-1]
    parts = []

    # Sort by size (last year forecast)
    sized = []
    for name, data in items.items():
        val = data.get("forecast", {}).get(last_yr, 0)
        cagr = data.get(cagr_key, 0)
        sized.append((name, float(val) if val else 0, float(cagr) if cagr else 0))

    sized.sort(key=lambda x: x[1], reverse=True)

    if sized:
        largest = sized[0]
        parts.append(
            f"Among all {dim_name.lower()} segments, {largest[0]} is projected to hold the largest "
            f"market position by {last_yr} with a forecast value of {_fmt_val(largest[1])}."
        )

    fastest = max(sized, key=lambda x: x[2]) if sized else None
    if fastest and fastest[2] > 0:
        parts.append(
            f"The {fastest[0]} segment is expected to register the highest growth rate "
            f"with a CAGR of {_fmt_pct(fastest[2])} during the forecast period."
        )

    if len(sized) > 1:
        smallest = sized[-1]
        parts.append(
            f"The {smallest[0]} segment represents the smallest share of the market "
            f"with a projected value of {_fmt_val(smallest[1])} by {last_yr}."
        )

    return " ".join(parts)


# ─── Regional Insights ───────────────────────────────────────────────────────


def generate_regional_insights(
    region_data: dict,
    years: list[str],
    cagr_key: str,
    unit: str = "",
) -> dict[str, list[str]]:
    """Generate per-region insight sentences from by_region ME data.

    region_data: {"North America": {"forecast": {...}, "cagr_...": x, ...}}
    Returns: {"North America": ["insight1", ...]}
    """
    if not region_data or not years:
        return {}

    first_yr = years[0]
    last_yr = years[-1]
    result = {}

    # Rankings
    cagr_ranked = sorted(
        [(name, float(data.get(cagr_key, 0))) for name, data in region_data.items()],
        key=lambda x: x[1], reverse=True,
    )
    size_ranked = sorted(
        [(name, float(data.get("forecast", {}).get(last_yr, 0))) for name, data in region_data.items()],
        key=lambda x: x[1], reverse=True,
    )

    for name, data in region_data.items():
        insights = []
        forecast = data.get("forecast", {})
        cagr = data.get(cagr_key)
        yoy = data.get("yoy_growth", {})

        first_val = forecast.get(first_yr)
        last_val = forecast.get(last_yr)

        if first_val and last_val and cagr:
            insights.append(
                f"The {name} market is projected to grow from {_fmt_val(first_val)}{_get_unit_label(unit)} "
                f"in {first_yr} to {_fmt_val(last_val)}{_get_unit_label(unit)} in {last_yr}, "
                f"at a CAGR of {_fmt_pct(cagr)}."
            )

        # Ranking
        size_rank = next((i + 1 for i, (n, _) in enumerate(size_ranked) if n == name), None)
        if size_rank == 1:
            insights.append(f"{name} is projected to be the largest regional market by {last_yr}.")
        cagr_rank = next((i + 1 for i, (n, _) in enumerate(cagr_ranked) if n == name), None)
        if cagr_rank == 1 and len(cagr_ranked) > 1:
            insights.append(f"{name} is expected to witness the highest growth rate among all regions.")

        result[name] = insights

    return result
