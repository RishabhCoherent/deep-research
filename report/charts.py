"""
Chart generators using matplotlib.

Each function returns a BytesIO PNG at 300 DPI.

5 chart types:
  1. Combo Forecast (clustered bars + YoY line)
  2. Doughnut Share (side-by-side year comparison)
  3. Stacked 100% BPS (percentage share over time)
  4. Bar Country Comparison (horizontal bars at 3 years)
  5. Line YoY Comparison (growth trends)
"""

import io
import logging
import warnings

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

warnings.filterwarnings("ignore", category=UserWarning, module="matplotlib.category")

from report.styles import (
    CHART_COLORS, HEX_NAVY, HEX_GOLD, HEX_STEEL_GRAY,
    HEX_DARK_TEXT, HEX_BRIGHT_RED, HEX_AMBER, HEX_MINT_GREEN,
    HEX_TEAL_GREEN, HEX_FOREST_GREEN, HEX_LIGHT_TEAL_GREEN,
    FONT_DISPLAY, FONT_BODY,
)

# Backward-compat aliases used throughout this file
HEX_DARK_BLUE = HEX_NAVY
HEX_ACCENT_BLUE = HEX_NAVY
HEX_ACCENT_ORANGE = HEX_GOLD

logger = logging.getLogger(__name__)


# ─── Smart Number Formatter ─────────────────────────────────────────────────


def _fmt_value(val, _pos=None) -> str:
    """Format numbers with K/M/B abbreviations for cleaner axis labels."""
    abs_val = abs(val)
    if abs_val >= 1e9:
        return f"{val / 1e9:.1f}B"
    if abs_val >= 1e6:
        return f"{val / 1e6:.1f}M"
    if abs_val >= 1e3:
        return f"{val / 1e3:.1f}K"
    return f"{val:.0f}"


def _fmt_bar_label(val) -> str:
    """Format value for bar labels (shorter)."""
    abs_val = abs(val)
    if abs_val >= 1e9:
        return f"{val / 1e9:.1f}B"
    if abs_val >= 1e6:
        return f"{val / 1e6:.1f}M"
    if abs_val >= 1e3:
        return f"{val / 1e3:.0f}K"
    return f"{val:.0f}"


# ─── Shared Setup ────────────────────────────────────────────────────────────


def _setup_chart_style():
    """Apply PPTX-grade chart styling — clean, minimal, no gridlines."""
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Calibri", "Arial", "Helvetica"],
        "font.size": 10,
        "axes.titlesize": 14,
        "axes.titleweight": "bold",
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.facecolor": "white",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": False,
        "axes.spines.bottom": False,
        "axes.grid": False,
        "axes.edgecolor": "#E8E8E8",
        "xtick.color": "#5A7D8C",
        "ytick.color": "#5A7D8C",
        "axes.labelcolor": "#006B77",
    })


# PPTX-grade palette — teal + green + cyan (mixed for visual variety)
_PPTX_PRIMARY = ["#006B77", "#009688", "#00BCD4"]  # Dark Teal, Teal-Green, Bright Cyan
_PPTX_EXTENDED = ["#006B77", "#009688", "#00BCD4", "#2E7D32", "#5A7D8C", "#4DB6AC"]
_NAVY_GRADIENT = ["#003F48", "#006B77", "#009688", "#2E7D32", "#4DB6AC", "#5A7D8C"]

# Keep old names as aliases for functions that reference them
_CONSULTING_BLUE_GRADIENT = _NAVY_GRADIENT
_CONSULTING_PALETTE = _PPTX_EXTENDED


def _to_buffer(fig) -> io.BytesIO:
    """Render figure to PNG BytesIO and close."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=300,
                facecolor="white", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf


def _add_chart_title(fig, title: str, subtitle: str = ""):
    """Add PPTX-grade title with optional insight subtitle."""
    fig.suptitle(title, fontsize=14, fontweight="bold", color=HEX_NAVY,
                 y=0.99, ha="center")
    if subtitle:
        fig.text(0.5, 0.945, subtitle, fontsize=9, color=HEX_STEEL_GRAY,
                 ha="center", style="italic")


# ─── 1. Combo Forecast Chart ────────────────────────────────────────────────


def chart_combo_forecast(
    title: str,
    items: dict,
    years: list[str],
    value_label: str = "Value",
    bar_unit: str = "",
    show_yoy_line: bool = True,
) -> io.BytesIO:
    """Clustered column bars for each item + optional YoY growth line.

    Args:
        title: Chart title.
        items: {"Item": {"forecast": {"2020": x, ...}, "yoy_growth": {"2021": x, ...}}}
        years: Year strings for x-axis.
        value_label: Y-axis label.
        bar_unit: Unit for bar values.
        show_yoy_line: Whether to add secondary y-axis with YoY growth.
    """
    _setup_chart_style()

    n_items = len(items)
    if n_items == 0:
        return _empty_chart(title)

    x = np.arange(len(years))
    width = 0.7 / max(n_items, 1)

    fig, ax1 = plt.subplots(figsize=(11, 5.5))
    _add_chart_title(fig, title)

    # Use PPTX palette for bars (navy, gold, steel gray cycle)
    item_names = list(items.keys())
    palette = _PPTX_PRIMARY if n_items <= 3 else _PPTX_EXTENDED
    for i, name in enumerate(item_names):
        forecast = items[name].get("forecast", {})
        vals = [forecast.get(y, 0) for y in years]
        offset = (i - n_items / 2 + 0.5) * width
        color = palette[i % len(palette)]
        bars = ax1.bar(x + offset, vals, width, label=name, color=color,
                       alpha=0.9, zorder=3, edgecolor="white", linewidth=0.5)
        # Value labels on EVERY bar (PPTX pattern)
        if n_items <= 4:
            for j, bar in enumerate(bars):
                h = bar.get_height()
                if h > 0:
                    ax1.text(bar.get_x() + bar.get_width() / 2, h,
                             _fmt_bar_label(h), ha="center", va="bottom",
                             fontsize=6, color=HEX_NAVY, fontweight="bold")

    unit_str = f" ({bar_unit})" if bar_unit else ""
    ax1.set_ylabel(f"{value_label}{unit_str}", fontweight="medium")
    ax1.set_xticks(x)
    ax1.set_xticklabels(years, rotation=0 if len(years) <= 8 else 45,
                         ha="center" if len(years) <= 8 else "right")
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_value))
    ax1.spines["left"].set_visible(False)
    ax1.tick_params(axis="y", length=0)
    # Ultra-subtle baseline grid only
    ax1.yaxis.grid(True, alpha=0.08, color="#CCCCCC", zorder=0)

    # YoY growth line on secondary axis
    if show_yoy_line and n_items == 1:
        name = item_names[0]
        yoy = items[name].get("yoy_growth", {})
        if yoy:
            yoy_years = [y for y in years if y in yoy]
            yoy_vals = [yoy[y] * 100 for y in yoy_years]
            yoy_x = [years.index(y) for y in yoy_years]

            ax2 = ax1.twinx()
            ax2.plot(yoy_x, yoy_vals, color=HEX_ACCENT_ORANGE, marker="o",
                     linewidth=2.5, markersize=7, label="YoY Growth %", zorder=5)
            ax2.set_ylabel("YoY Growth (%)", color=HEX_ACCENT_ORANGE, fontweight="medium")
            ax2.tick_params(axis="y", labelcolor=HEX_ACCENT_ORANGE)
            ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: f"{v:.1f}%"))
            ax2.spines["right"].set_visible(True)
            ax2.spines["right"].set_color(HEX_ACCENT_ORANGE)

            lines1, labels1 = ax1.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left",
                       framealpha=0.95, edgecolor="#E0E0E0", fancybox=True)
        else:
            ax1.legend(loc="upper left", framealpha=0.95, edgecolor="#E0E0E0")
    else:
        ax1.legend(loc="upper left", framealpha=0.95, edgecolor="#E0E0E0",
                   ncol=min(n_items, 4))

    fig.tight_layout(rect=[0, 0, 1, 0.93])
    return _to_buffer(fig)


def chart_single_combo(
    title: str,
    forecast: dict,
    yoy: dict,
    years: list[str],
    bar_label: str = "Market Size",
    bar_unit: str = "",
    bar_color: str = HEX_ACCENT_BLUE,
    fig_size: tuple = (11, 5.5),
    forecast_start_yr: str = None,
) -> io.BytesIO:
    """Single-series combo chart (bars + YoY line). For totals.

    Args:
        fig_size: Figure dimensions in inches. Use (6.0, 3.8) for sidebar context,
                  (11, 5.5) for full-width. Correct sizing ensures fonts appear
                  at the right scale when inserted into the document.
        forecast_start_yr: First year of the forecast period (e.g. "2025"). When
                           provided, historical bars are rendered in dark navy and
                           forecast bars in a lighter blue, with a vertical dashed
                           separator and period labels for a professional look.
    """
    _setup_chart_style()

    x = np.arange(len(years))
    vals = [forecast.get(y, 0) for y in years]

    # Determine historical/forecast split index
    split_idx = None
    if forecast_start_yr:
        for i, y in enumerate(years):
            if str(y) >= str(forecast_start_yr):
                split_idx = i
                break

    fig, ax1 = plt.subplots(figsize=fig_size)
    _add_chart_title(fig, title)

    # Bar coloring: historical (dark navy) vs forecast (medium navy) split
    if split_idx is not None:
        bar_colors = [
            HEX_NAVY if i < split_idx else "#4A8B96"
            for i in range(len(vals))
        ]
    else:
        # Solid navy for all bars — consistent single-metric time series
        bar_colors = [HEX_NAVY] * len(vals)

    bars = ax1.bar(x, vals, 0.6, label=bar_label, color=bar_colors,
                   alpha=0.9, zorder=3, edgecolor="white", linewidth=0.5)

    # Value labels on EVERY bar
    for i, bar in enumerate(bars):
        h = bar.get_height()
        if h > 0:
            ax1.text(bar.get_x() + bar.get_width() / 2, h,
                     _fmt_bar_label(h), ha="center", va="bottom",
                     fontsize=7, color=HEX_NAVY, fontweight="bold")

    # Historical / Forecast period markers
    if split_idx is not None and split_idx > 0:
        x_line = split_idx - 0.5
        ax1.axvline(x=x_line, color="#5A7D8C", linewidth=1.2, linestyle=":",
                    zorder=2, alpha=0.85)
        t = ax1.get_xaxis_transform()
        ax1.text(x_line - 0.25, 0.98, "Historical", ha="right", va="top",
                 fontsize=7, color="#5A7D8C", style="italic", transform=t)
        ax1.text(x_line + 0.25, 0.98, "Forecast", ha="left", va="top",
                 fontsize=7, color=HEX_GOLD, style="italic",
                 fontweight="bold", transform=t)

    unit_str = f" ({bar_unit})" if bar_unit else ""
    ax1.set_ylabel(f"{bar_label}{unit_str}", fontweight="medium")
    ax1.set_xticks(x)
    ax1.set_xticklabels(years, rotation=0 if len(years) <= 8 else 45,
                         ha="center" if len(years) <= 8 else "right")
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_value))
    ax1.spines["left"].set_visible(False)
    ax1.tick_params(axis="y", length=0)
    ax1.yaxis.grid(True, alpha=0.08, color="#CCCCCC", zorder=0)

    if yoy:
        yoy_years = [y for y in years if y in yoy]
        yoy_vals = [yoy[y] * 100 for y in yoy_years]
        yoy_x = [years.index(y) for y in yoy_years]

        ax2 = ax1.twinx()
        ax2.plot(yoy_x, yoy_vals, color=HEX_ACCENT_ORANGE, marker="o",
                 linewidth=2.5, markersize=7, label="YoY Growth %", zorder=5)
        ax2.set_ylabel("YoY Growth (%)", color=HEX_ACCENT_ORANGE, fontweight="medium")
        ax2.tick_params(axis="y", labelcolor=HEX_ACCENT_ORANGE)
        ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: f"{v:.1f}%"))
        ax2.spines["right"].set_visible(True)
        ax2.spines["right"].set_color(HEX_ACCENT_ORANGE)

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left",
                   framealpha=0.95, edgecolor="#E0E0E0")
    else:
        ax1.legend(loc="upper left", framealpha=0.95, edgecolor="#E0E0E0")

    fig.tight_layout(rect=[0, 0, 1, 0.93])
    return _to_buffer(fig)


# ─── 2. Doughnut Share Chart ────────────────────────────────────────────────


def chart_doughnut_share(
    title: str,
    items: dict,
    year_a: str,
    year_b: str,
    fig_size: tuple = (11, 5.5),
) -> io.BytesIO:
    """Side-by-side doughnut charts comparing share in two years.

    Args:
        items: {"Item": {"percentage_share": {"2020": 0.43, ...}}}
        year_a, year_b: Two years to compare.
        fig_size: Figure dimensions (width, height) in inches.
    """
    _setup_chart_style()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=fig_size)
    _add_chart_title(fig, title, f"Market Share Comparison: {year_a} vs {year_b}")

    names = list(items.keys())
    colors = [_PPTX_EXTENDED[i % len(_PPTX_EXTENDED)] for i in range(len(names))]

    for ax, year, side_title in [(ax1, year_a, year_a), (ax2, year_b, year_b)]:
        shares = []
        for name in names:
            pct = items[name].get("percentage_share", {}).get(year, 0)
            shares.append(pct * 100 if pct else 0)

        if sum(shares) == 0:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    transform=ax.transAxes, fontsize=12, color="#999999")
            ax.set_title(side_title, fontsize=12, fontweight="bold", color=HEX_DARK_BLUE)
            continue

        wedges, texts, autotexts = ax.pie(
            shares, labels=None, colors=colors, autopct="%1.1f%%",
            startangle=90, pctdistance=0.75,
            wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 2},
        )
        for at in autotexts:
            at.set_fontsize(8.5)
            at.set_fontweight("bold")
            at.set_color("white")

        # Center label: year in bold navy
        ax.text(0, 0, side_title, ha="center", va="center",
                fontsize=14, fontweight="bold", color=HEX_NAVY)

        # Subtle subtitle under year
        ax.text(0, -0.18, "Market Share", ha="center", va="center",
                fontsize=7, color=HEX_STEEL_GRAY, style="italic")

    fig.legend(names, loc="lower center", ncol=min(len(names), 5),
               fontsize=9, framealpha=0.95, edgecolor="#E0E0E0",
               markerscale=1.2)

    fig.tight_layout(rect=[0, 0.08, 1, 0.90])
    return _to_buffer(fig)


# ─── 3. Stacked 100% BPS Chart ──────────────────────────────────────────────


def chart_stacked_100_bps(
    title: str,
    items: dict,
    years: list[str],
) -> io.BytesIO:
    """100% stacked bar chart showing percentage share over time.

    Args:
        items: {"Item": {"percentage_share": {"2020": 0.43, ...}}}
        years: Year strings for x-axis.
    """
    _setup_chart_style()

    fig, ax = plt.subplots(figsize=(11, 5.5))
    _add_chart_title(fig, title, "Percentage market share evolution over forecast period")

    names = list(items.keys())
    x = np.arange(len(years))
    bottoms = np.zeros(len(years))

    seg_vals = {}
    for i, name in enumerate(names):
        pct = items[name].get("percentage_share", {})
        vals = np.array([pct.get(y, 0) * 100 for y in years])
        color = _PPTX_EXTENDED[i % len(_PPTX_EXTENDED)]
        ax.bar(x, vals, 0.7, bottom=bottoms, label=name, color=color, edgecolor="white",
               linewidth=0.8, zorder=3)
        seg_vals[name] = (vals, bottoms.copy())
        bottoms += vals

    # % labels inside bars where segment is wide enough (>= 6%)
    for name, (vals, bot) in seg_vals.items():
        for xi, (v, b) in enumerate(zip(vals, bot)):
            if v >= 6.0:
                ax.text(xi, b + v / 2, f"{v:.0f}%",
                        ha="center", va="center", fontsize=7,
                        color="white", fontweight="bold", zorder=5)

    ax.set_ylabel("Market Share (%)", fontweight="medium")
    ax.set_xticks(x)
    ax.set_xticklabels(years, rotation=0 if len(years) <= 8 else 45,
                         ha="center" if len(years) <= 8 else "right")
    ax.set_ylim(0, 105)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: f"{v:.0f}%"))
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.legend(loc="upper right", fontsize=8, framealpha=0.95, edgecolor="#E0E0E0",
              ncol=min(len(names), 4))

    fig.tight_layout(rect=[0, 0, 1, 0.90])
    return _to_buffer(fig)


# ─── 4. Bar Country Comparison ──────────────────────────────────────────────


def chart_bar_country_comparison(
    title: str,
    countries: dict,
    snapshot_years: list[str],
    unit: str = "",
) -> io.BytesIO:
    """Horizontal bar chart comparing countries at 3 snapshot years.

    Args:
        countries: {"Country": {"forecast": {"2020": x, ...}}}
        snapshot_years: 3 years to compare.
    """
    _setup_chart_style()

    names = list(countries.keys())
    n_years = len(snapshot_years)
    n_countries = len(names)

    fig, ax = plt.subplots(figsize=(11, max(4.5, n_countries * 0.65 + 2)))
    _add_chart_title(fig, title)

    y = np.arange(n_countries)
    height = 0.7 / max(n_years, 1)

    for i, year in enumerate(snapshot_years):
        vals = []
        for name in names:
            forecast = countries[name].get("forecast", {})
            vals.append(forecast.get(year, 0))
        offset = (i - n_years / 2 + 0.5) * height
        color = _PPTX_PRIMARY[i % len(_PPTX_PRIMARY)]
        bars = ax.barh(y + offset, vals, height, label=year, color=color,
                       alpha=0.9, zorder=3, edgecolor="white", linewidth=0.5)
        # Value labels at bar ends — all bars
        for bar in bars:
            w = bar.get_width()
            if w > 0:
                ax.text(w, bar.get_y() + bar.get_height() / 2,
                        f" {_fmt_bar_label(w)}", va="center", ha="left",
                        fontsize=6, color=HEX_NAVY, fontweight="bold")

    unit_str = f" ({unit})" if unit else ""
    ax.set_xlabel(f"Value{unit_str}", fontweight="medium")
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=10, fontweight="medium")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_fmt_value))
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(axis="x", length=0)
    ax.xaxis.grid(True, alpha=0.08, color="#CCCCCC", zorder=0)
    ax.legend(loc="lower right", framealpha=0.95, edgecolor="#E0E0E0")
    ax.invert_yaxis()

    fig.tight_layout(rect=[0, 0, 1, 0.93])
    return _to_buffer(fig)


# ─── 5. Line YoY Comparison ─────────────────────────────────────────────────


def chart_line_yoy_comparison(
    title: str,
    items: dict,
    years: list[str] | None = None,
) -> io.BytesIO:
    """Line chart comparing YoY growth trends across items.

    Args:
        items: {"Item": {"yoy_growth": {"2021": 0.05, ...}}}
        years: Optional year filter.
    """
    _setup_chart_style()

    if years is None:
        all_years = set()
        for data in items.values():
            all_years.update(data.get("yoy_growth", {}).keys())
        years = sorted(all_years, key=int)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    _add_chart_title(fig, title, "Year-over-year growth rate comparison")

    x = np.arange(len(years))
    for i, (name, data) in enumerate(items.items()):
        yoy = data.get("yoy_growth", {})
        vals = [yoy.get(y, 0) * 100 for y in years]
        color = _PPTX_EXTENDED[i % len(_PPTX_EXTENDED)]
        ax.plot(x, vals, marker="o", linewidth=2.5, markersize=7,
                label=name, color=color, zorder=3)
        # Annotate first and last points only (clean)
        if len(items) <= 5 and len(vals) > 0:
            for j in [0, len(vals) - 1]:
                ax.annotate(f"{vals[j]:.1f}%", (x[j], vals[j]),
                            textcoords="offset points", xytext=(0, 10),
                            ha="center", fontsize=7, color=color, fontweight="bold")

    ax.set_ylabel("YoY Growth (%)", fontweight="medium")
    ax.set_xticks(x)
    ax.set_xticklabels(years, rotation=0 if len(years) <= 8 else 45,
                         ha="center" if len(years) <= 8 else "right")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: f"{v:.1f}%"))
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.yaxis.grid(True, alpha=0.08, color="#CCCCCC", zorder=0)
    # Zero line for reference
    ax.axhline(0, color="#CCCCCC", linewidth=0.8, zorder=1)
    ax.legend(loc="best", framealpha=0.95, edgecolor="#E0E0E0",
              fontsize=8, ncol=min(len(items), 4))

    fig.tight_layout(rect=[0, 0, 1, 0.90])
    return _to_buffer(fig)


# ─── 6. Bubble Attractiveness Chart ──────────────────────────────────────────


def chart_bubble_attractiveness(
    title: str,
    items: dict,
    cagr_key: str,
    base_year: str = "2025",
    end_year: str = "2032",
) -> io.BytesIO:
    """Premium bubble chart for market attractiveness analysis with 3D-style bubbles.

    X-axis = CAGR (growth rate %), Y-axis = market size (base year),
    bubble size = incremental opportunity (end - base).

    Args:
        items: {"Segment": {"forecast": {year: val}, "cagr_...": x}}
        cagr_key: CAGR dict key.
        base_year, end_year: For sizing bubbles.
    """
    _setup_chart_style()
    from matplotlib.patches import FancyBboxPatch
    import matplotlib.colors as mcolors

    names = []
    x_vals = []  # CAGR %
    y_vals = []  # Market size in base year
    sizes = []   # Incremental opportunity

    for name, data in items.items():
        cagr = data.get(cagr_key, 0)
        forecast = data.get("forecast", {})
        base_val = forecast.get(base_year, 0)
        end_val = forecast.get(end_year, 0)

        try:
            cagr_pct = float(cagr) * 100
            base_f = float(base_val)
            incr = float(end_val) - base_f
        except (ValueError, TypeError):
            continue

        if base_f <= 0:
            continue

        names.append(name)
        x_vals.append(cagr_pct)
        y_vals.append(base_f)
        sizes.append(max(incr, 0))

    if not names:
        return _empty_chart(title)

    fig, ax = plt.subplots(figsize=(11, 7.5))
    fig.patch.set_facecolor("white")

    x_arr = np.array(x_vals)
    y_arr = np.array(y_vals)
    s_arr = np.array(sizes)

    if s_arr.max() > 0:
        s_norm = 400 + (s_arr / s_arr.max()) * 2200
    else:
        s_norm = np.full_like(s_arr, 700)

    colors_hex = [_PPTX_EXTENDED[i % len(_PPTX_EXTENDED)] for i in range(len(names))]

    # ── Tighten axes with padding so bubbles don't clip ─────────────
    x_pad = (x_arr.max() - x_arr.min()) * 0.15 + 0.3
    y_pad = (y_arr.max() - y_arr.min()) * 0.18 + 50
    ax.set_xlim(x_arr.min() - x_pad, x_arr.max() + x_pad)
    ax.set_ylim(max(0, y_arr.min() - y_pad), y_arr.max() + y_pad * 1.3)

    # ── Quadrant background zones ───────────────────────────────────
    med_x = np.median(x_arr)
    med_y = np.median(y_arr)
    xl, xr = ax.get_xlim()
    yb, yt = ax.get_ylim()

    # Soft colored quadrant fills
    ax.fill_between([xl, med_x], yb, med_y, color="#F0F7F7", alpha=0.8, zorder=0)  # Niche
    ax.fill_between([med_x, xr], yb, med_y, color="#E8F5F0", alpha=0.8, zorder=0)  # Emerging
    ax.fill_between([xl, med_x], med_y, yt, color="#E0F0F0", alpha=0.8, zorder=0)  # Leaders
    ax.fill_between([med_x, xr], med_y, yt, color="#E0F5EC", alpha=0.8, zorder=0)  # Stars

    # Quadrant dividers
    ax.axvline(med_x, color="#5A7D8C", linestyle="-", linewidth=1.0, zorder=1, alpha=0.35)
    ax.axhline(med_y, color="#5A7D8C", linestyle="-", linewidth=1.0, zorder=1, alpha=0.35)

    # ── 3D-style bubbles: shadow + gradient + highlight ─────────────
    for i in range(len(names)):
        x, y, sz, color = x_arr[i], y_arr[i], s_norm[i], colors_hex[i]

        # Shadow (offset down-right, dark, large)
        ax.scatter(x + x_pad * 0.015, y - y_pad * 0.03, s=sz * 1.15,
                   c="#333333", alpha=0.12, edgecolors="none", zorder=2)

        # Main bubble — solid fill with slight transparency
        ax.scatter(x, y, s=sz, c=color, alpha=0.88,
                   edgecolors="white", linewidth=2.5, zorder=4)

        # Inner highlight (smaller, lighter, offset up-left for 3D shine)
        rgb = mcolors.to_rgb(color)
        highlight = tuple(min(1.0, c + 0.35) for c in rgb)
        ax.scatter(x - x_pad * 0.008, y + y_pad * 0.025, s=sz * 0.25,
                   c=[highlight], alpha=0.55, edgecolors="none", zorder=5)

    # ── Labels with styled background boxes ─────────────────────────
    for i, name in enumerate(names):
        # Truncate long names
        display_name = name if len(name) <= 28 else name[:26] + "…"
        ax.annotate(display_name, (x_arr[i], y_arr[i]),
                    textcoords="offset points", xytext=(0, -10),
                    ha="center", va="top", fontsize=8.5, fontweight="bold",
                    color=HEX_DARK_TEXT,
                    bbox=dict(boxstyle="round,pad=0.25", fc="white",
                              ec="#C0D8D8", linewidth=0.8, alpha=0.85),
                    zorder=6)

    # ── Quadrant labels with pill-style backgrounds ─────────────────
    quad_style = dict(fontsize=11, fontweight="bold", zorder=7)
    pill = dict(boxstyle="round,pad=0.4", linewidth=0)

    ax.text(0.97, 0.97, "  STARS  ", transform=ax.transAxes,
            ha="right", va="top", color=HEX_NAVY,
            bbox=dict(**pill, fc="#C8E6C9", alpha=0.7), **quad_style)
    ax.text(0.03, 0.97, "  LEADERS  ", transform=ax.transAxes,
            ha="left", va="top", color=HEX_NAVY,
            bbox=dict(**pill, fc="#B2DFDB", alpha=0.7), **quad_style)
    ax.text(0.97, 0.03, "  EMERGING  ", transform=ax.transAxes,
            ha="right", va="bottom", color=HEX_STEEL_GRAY,
            bbox=dict(**pill, fc="#E0F2F1", alpha=0.7), **quad_style)
    ax.text(0.03, 0.03, "  NICHE  ", transform=ax.transAxes,
            ha="left", va="bottom", color=HEX_STEEL_GRAY,
            bbox=dict(**pill, fc="#F0F7F7", alpha=0.7), **quad_style)

    # ── Axes styling ────────────────────────────────────────────────
    ax.set_xlabel("CAGR (%)", fontsize=11, fontweight="bold", color=HEX_NAVY,
                  labelpad=10)
    ax.set_ylabel(f"Market Size ({base_year})", fontsize=11, fontweight="bold",
                  color=HEX_NAVY, labelpad=10)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: f"{v:.1f}%"))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_value))
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(length=0)

    # ── Title + subtitle ────────────────────────────────────────────
    fig.suptitle(title, fontsize=15, fontweight="bold", color=HEX_NAVY, y=0.97)
    ax.text(0.5, 1.04, "Bubble size represents incremental growth opportunity",
            transform=ax.transAxes, ha="center", fontsize=9.5,
            color=HEX_STEEL_GRAY, style="italic")

    fig.subplots_adjust(top=0.90, bottom=0.10, left=0.08, right=0.97)
    return _to_buffer(fig)


# ─── 7. Horizontal CAGR Ranking Chart ───────────────────────────────────────


def chart_horizontal_cagr_ranking(
    title: str,
    items: dict,
    cagr_key: str,
    top_n: int = 12,
    highlight_top: int = 3,
) -> io.BytesIO:
    """Horizontal bar chart ranking segments by CAGR.

    Args:
        items: {"Segment": {"cagr_...": x}} or {"Segment": {cagr_key: x}}
        cagr_key: CAGR dict key.
        top_n: Max items to show.
        highlight_top: Top N bars colored orange, rest blue.
    """
    _setup_chart_style()

    # Extract and sort by CAGR
    ranked = []
    for name, data in items.items():
        cagr = data.get(cagr_key, 0)
        try:
            ranked.append((name, float(cagr) * 100))
        except (ValueError, TypeError):
            continue

    ranked.sort(key=lambda x: x[1], reverse=True)
    ranked = ranked[:top_n]

    if not ranked:
        return _empty_chart(title)

    names = [r[0] for r in ranked]
    vals = [r[1] for r in ranked]

    # Bold gradient: #006B77 (dark teal) → #2E7D32 (forest green) — teal-to-green range
    n = len(ranked)
    colors = []
    for i in range(n):
        ratio = i / max(n - 1, 1)
        r = int(0x00 + ratio * (0x2E - 0x00))
        g = int(0x6B + ratio * (0x7D - 0x6B))
        b = int(0x77 + ratio * (0x32 - 0x77))
        colors.append(f"#{r:02x}{g:02x}{b:02x}")

    fig, ax = plt.subplots(figsize=(11, max(4.5, len(ranked) * 0.5 + 1.5)))
    _add_chart_title(fig, title, "Fastest growing segments by compound annual growth rate")
    ax.set_facecolor("#E8F4F5")  # subtle off-white bg for contrast

    y_pos = np.arange(len(names))
    bars = ax.barh(y_pos, vals, color=colors, alpha=1.0, edgecolor="white",
                   linewidth=0.8, zorder=3, height=0.7)

    for i, val in enumerate(vals):
        ax.text(val + 0.08, i, f"{val:.2f}%", va="center", fontsize=8.5,
                color=HEX_NAVY, fontweight="bold")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=9, fontweight="medium")
    ax.set_xlabel("CAGR (%)", fontweight="medium")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: f"{v:.1f}%"))
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(axis="x", length=0)
    ax.xaxis.grid(True, alpha=0.08, color="#CCCCCC", zorder=0)
    ax.invert_yaxis()

    fig.tight_layout(rect=[0, 0, 1, 0.92])
    return _to_buffer(fig)


# ─── Fallback ────────────────────────────────────────────────────────────────


def chart_porters_radar(
    title: str,
    forces: dict,
) -> io.BytesIO:
    """Premium radar/spider chart for Porter's Five Forces.

    Args:
        forces: {"Force Name": {"rating": "High/Moderate/Low", ...}}
    """
    _setup_chart_style()

    rating_to_score = {
        "high": 5, "moderate": 3, "medium": 3, "low": 1,
    }
    rating_to_color = {
        "high": HEX_NAVY, "moderate": HEX_TEAL_GREEN, "medium": HEX_TEAL_GREEN, "low": HEX_FOREST_GREEN,
    }
    rating_to_label = {
        "high": "HIGH", "moderate": "MODERATE", "medium": "MODERATE", "low": "LOW",
    }

    labels = []
    scores = []
    colors_list = []
    rating_labels = []
    for force_name, data in forces.items():
        rating = data.get("rating", "moderate").lower().strip()
        labels.append(force_name.replace("_", " ").title())
        scores.append(rating_to_score.get(rating, 3))
        colors_list.append(rating_to_color.get(rating, "#888888"))
        rating_labels.append(rating_to_label.get(rating, "MODERATE"))

    if not labels:
        return _empty_chart(title)

    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    scores_closed = scores + scores[:1]
    angles_closed = angles + angles[:1]

    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor("white")

    # ── Concentric threat zone rings (background) ───────────────────
    zone_colors = ["#E8F5E9", "#E0F2F1", "#E0F0F0", "#D0EBEB", "#C8E6E6"]
    for ring_r, zc in zip([1, 2, 3, 4, 5], zone_colors):
        theta_fill = np.linspace(0, 2 * np.pi, 100)
        ax.fill(theta_fill, [ring_r] * 100, color=zc, alpha=0.5, zorder=0)

    # Zone labels on the right axis
    ax.text(0.35, 1.3, "LOW", fontsize=7, color="#2E7D32", fontweight="bold",
            ha="center", va="center", alpha=0.7)
    ax.text(0.35, 3.3, "MODERATE", fontsize=7, color="#009688", fontweight="bold",
            ha="center", va="center", alpha=0.7)
    ax.text(0.35, 5.3, "HIGH", fontsize=7, color="#006B77", fontweight="bold",
            ha="center", va="center", alpha=0.7)

    # ── Data fill — layered for depth effect ────────────────────────
    ax.fill(angles_closed, scores_closed, color=HEX_NAVY, alpha=0.18, zorder=2)
    ax.fill(angles_closed, scores_closed, color=HEX_TEAL_GREEN, alpha=0.08, zorder=2)
    ax.plot(angles_closed, scores_closed, color=HEX_NAVY, linewidth=3.5,
            zorder=4, solid_capstyle="round")
    # Glow line underneath
    ax.plot(angles_closed, scores_closed, color=HEX_TEAL_GREEN, linewidth=7,
            alpha=0.25, zorder=3, solid_capstyle="round")

    # ── Data points — large dots with rating badges ─────────────────
    for i in range(n):
        # Outer glow
        ax.scatter(angles[i], scores[i], c=colors_list[i], s=500, zorder=5,
                   alpha=0.2, edgecolors="none")
        # Main dot
        ax.scatter(angles[i], scores[i], c=colors_list[i], s=220, zorder=6,
                   edgecolors="white", linewidth=3)

        # Rating badge near the dot
        badge_offset = 0.85
        ax.text(angles[i], scores[i] + badge_offset, rating_labels[i],
                ha="center", va="center", fontsize=8, fontweight="bold",
                color="white", zorder=7,
                bbox=dict(boxstyle="round,pad=0.3", fc=colors_list[i],
                          ec="white", linewidth=1.5, alpha=0.92))

    # ── Axis labels — force names with styled background ────────────
    ax.set_xticks(angles)
    ax.set_xticklabels([])  # Clear default labels, render custom below
    ax.set_ylim(0, 6.2)

    for i, (angle, label) in enumerate(zip(angles, labels)):
        # Position labels outside the chart
        label_r = 6.6
        ha = "center"
        if angle > 0.1 and angle < np.pi:
            ha = "left"
        elif angle > np.pi and angle < 2 * np.pi - 0.1:
            ha = "right"

        ax.text(angle, label_r, label, ha=ha, va="center",
                fontsize=11, fontweight="bold", color=HEX_DARK_TEXT,
                bbox=dict(boxstyle="round,pad=0.4", fc="white",
                          ec="#D0E8E8", linewidth=1, alpha=0.9))

    # ── Grid styling ────────────────────────────────────────────────
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_yticklabels(["", "", "", "", ""], fontsize=1)
    ax.spines["polar"].set_color("#C0D8D8")
    ax.spines["polar"].set_linewidth(1.5)
    ax.grid(color="#B8D8D8", linewidth=0.8, linestyle="-", alpha=0.6)

    # ── Title ───────────────────────────────────────────────────────
    fig.suptitle(title, fontsize=16, fontweight="bold", color=HEX_NAVY, y=0.97)
    ax.text(0, -0.4, "Competitive Intensity Assessment",
            ha="center", va="center", fontsize=10, color=HEX_STEEL_GRAY,
            style="italic", transform=ax.transAxes)

    # ── Legend — positioned inside, no clipping ─────────────────────
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=HEX_NAVY,
               markersize=11, markeredgecolor="white", markeredgewidth=2, label="High Threat"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=HEX_TEAL_GREEN,
               markersize=11, markeredgecolor="white", markeredgewidth=2, label="Moderate"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=HEX_FOREST_GREEN,
               markersize=11, markeredgecolor="white", markeredgewidth=2, label="Low Threat"),
    ]
    legend = ax.legend(handles=legend_elements, loc="lower center",
                       bbox_to_anchor=(0.5, -0.18),
                       fontsize=10, framealpha=0.95, edgecolor="#C0D8D8",
                       title="Threat Level", title_fontsize=11,
                       ncol=3, columnspacing=2.0,
                       handletextpad=0.8, borderpad=0.8)
    legend.get_title().set_fontweight("bold")
    legend.get_title().set_color(HEX_NAVY)

    fig.subplots_adjust(bottom=0.12, top=0.92, left=0.08, right=0.92)
    return _to_buffer(fig)


def chart_waterfall_growth(
    title: str,
    base_value: float,
    end_value: float,
    base_year: str,
    end_year: str,
    segments: dict = None,
    unit: str = "Mn",
) -> io.BytesIO:
    """Waterfall chart showing market progression from base to forecast value.

    Args:
        base_value: Market value in base year.
        end_value: Market value in end year.
        segments: Optional {"Segment": contribution_value} for breakdown.
        unit: Value unit label.
    """
    _setup_chart_style()

    fig, ax = plt.subplots(figsize=(11, 5.5))
    _add_chart_title(fig, title, f"Market progression from {base_year} to {end_year}")

    if segments and len(segments) > 1:
        # Multi-segment waterfall
        sorted_segs = sorted(segments.items(), key=lambda x: abs(x[1]), reverse=True)
        labels = [f"Base ({base_year})"] + [s[0] for s in sorted_segs] + [f"Total ({end_year})"]
        values = [base_value] + [s[1] for s in sorted_segs] + [end_value]

        running = base_value
        bottoms = [0]
        bar_vals = [base_value]
        bar_colors = [HEX_NAVY]

        for _, contrib in sorted_segs:
            bottoms.append(running)
            bar_vals.append(contrib)
            bar_colors.append(HEX_GOLD if contrib >= 0 else HEX_BRIGHT_RED)
            running += contrib

        bottoms.append(0)
        bar_vals.append(end_value)
        bar_colors.append(HEX_STEEL_GRAY)
    else:
        # Simple 3-bar waterfall: base → growth → end
        growth = end_value - base_value
        labels = [f"Base ({base_year})", "Growth", f"Forecast ({end_year})"]
        bar_vals = [base_value, growth, end_value]
        bottoms = [0, base_value, 0]
        bar_colors = [HEX_NAVY, HEX_GOLD, HEX_STEEL_GRAY]

    x = np.arange(len(labels))
    bars = ax.bar(x, bar_vals, bottom=bottoms, color=bar_colors, width=0.55,
                  edgecolor="white", linewidth=1, zorder=3, alpha=0.9)

    # Connector lines between bars
    for i in range(len(x) - 1):
        top_val = bottoms[i] + bar_vals[i]
        ax.plot([x[i] + 0.275, x[i + 1] - 0.275], [top_val, top_val],
                color="#CCCCCC", linewidth=1, linestyle="--", zorder=2)

    # Value labels on bars
    for i, (bar, val) in enumerate(zip(bars, bar_vals)):
        y_pos = bottoms[i] + val / 2 if val > 0 else bottoms[i] + val / 2
        display = f"US$ {_fmt_bar_label(abs(val))} {unit}"
        ax.text(bar.get_x() + bar.get_width() / 2, bottoms[i] + val,
                display, ha="center", va="bottom",
                fontsize=8, fontweight="bold", color=HEX_DARK_BLUE)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9, fontweight="medium", rotation=20, ha="right")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_value))
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(length=0)
    ax.yaxis.grid(True, alpha=0.08, color="#CCCCCC", zorder=0)

    fig.tight_layout(rect=[0, 0, 1, 0.92])
    return _to_buffer(fig)


def chart_market_growth_area(
    title: str,
    forecast: dict,
    years: list[str],
    unit: str = "Mn",
    cagr_pct: float = None,
    fig_size: tuple = (11, 5),
    forecast_start_yr: str = None,
) -> io.BytesIO:
    """Gradient area chart showing market growth trajectory.

    Creates a dramatic filled area chart — highly visual, slide-ready.

    Args:
        fig_size: Figure dimensions. Use (6.0, 3.8) for sidebar context.
        forecast_start_yr: First year of forecast period. When provided, a subtle
                           gold-shaded region highlights the forecast span.
    """
    _setup_chart_style()

    fig, ax = plt.subplots(figsize=fig_size)
    subtitle = f"CAGR: {cagr_pct:.1f}%" if cagr_pct else ""
    _add_chart_title(fig, title, subtitle)

    vals = [float(forecast.get(y, 0)) for y in years]
    x = np.arange(len(years))

    # Determine forecast split
    split_idx = None
    if forecast_start_yr:
        for i, y in enumerate(years):
            if str(y) >= str(forecast_start_yr):
                split_idx = i
                break

    # Subtle forecast region shading (before drawing the area)
    if split_idx is not None and split_idx > 0:
        ax.axvspan(split_idx - 0.5, len(years) - 0.7,
                   color=HEX_GOLD, alpha=0.04, zorder=1)
        ax.axvline(x=split_idx - 0.5, color="#5A7D8C", linewidth=1,
                   linestyle=":", alpha=0.8, zorder=2)
        t = ax.get_xaxis_transform()
        ax.text(split_idx - 0.4, 0.97, "Historical", ha="right", va="top",
                fontsize=7, color="#5A7D8C", style="italic", transform=t)
        ax.text(split_idx - 0.3, 0.97, "Forecast", ha="left", va="top",
                fontsize=7, color=HEX_GOLD, style="italic",
                fontweight="bold", transform=t)

    # Gradient fill with navy, line with gold markers
    ax.fill_between(x, vals, alpha=0.08, color=HEX_NAVY, zorder=2)
    ax.fill_between(x, vals, alpha=0.12, color=HEX_NAVY, zorder=2)
    ax.plot(x, vals, color=HEX_NAVY, linewidth=3, zorder=4, marker="o",
            markersize=8, markerfacecolor="white", markeredgecolor=HEX_GOLD,
            markeredgewidth=2)

    # Annotate first and last values prominently
    for i in [0, len(vals) - 1]:
        label = f"US$ {_fmt_bar_label(vals[i])} {unit}"
        ax.annotate(label, (x[i], vals[i]),
                    textcoords="offset points", xytext=(0, 15),
                    ha="center", fontsize=10, fontweight="bold",
                    color=HEX_NAVY,
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                              edgecolor=HEX_GOLD, alpha=0.9))

    ax.set_xticks(x)
    ax.set_xticklabels(years, fontsize=10, fontweight="medium",
                        rotation=0 if len(years) <= 8 else 45,
                        ha="center" if len(years) <= 8 else "right")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_value))
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(length=0)
    ax.set_xlim(-0.3, len(years) - 0.7)
    ax.set_ylim(bottom=0)

    fig.tight_layout(rect=[0, 0, 1, 0.91])
    return _to_buffer(fig)


def chart_gauge_metric(
    title: str,
    value: float,
    max_value: float = 100,
    unit: str = "%",
    thresholds: tuple = (30, 60, 80),
) -> io.BytesIO:
    """Semicircle gauge chart for a single KPI metric.

    Creates a dramatic half-circle gauge with colored zones.
    Ideal for CAGR, satisfaction scores, or index values.
    """
    _setup_chart_style()

    fig, ax = plt.subplots(figsize=(6, 3.5), subplot_kw=dict(aspect="equal"))

    # Draw gauge background arcs (zones)
    zone_colors = [HEX_BRIGHT_RED, HEX_AMBER, HEX_MINT_GREEN, HEX_NAVY]
    zone_limits = [0] + list(thresholds) + [max_value]
    for i in range(len(zone_limits) - 1):
        start_angle = 180 - (zone_limits[i] / max_value) * 180
        end_angle = 180 - (zone_limits[i + 1] / max_value) * 180
        theta = np.linspace(np.radians(start_angle), np.radians(end_angle), 50)
        # Outer arc
        x_outer = np.cos(theta) * 1.0
        y_outer = np.sin(theta) * 1.0
        x_inner = np.cos(theta) * 0.6
        y_inner = np.sin(theta) * 0.6
        verts_x = np.concatenate([x_outer, x_inner[::-1]])
        verts_y = np.concatenate([y_outer, y_inner[::-1]])
        ax.fill(verts_x, verts_y, color=zone_colors[i % len(zone_colors)], alpha=0.3)

    # Needle
    clamped = min(max(value, 0), max_value)
    angle = np.radians(180 - (clamped / max_value) * 180)
    ax.plot([0, np.cos(angle) * 0.85], [0, np.sin(angle) * 0.85],
            color=HEX_DARK_BLUE, linewidth=3, zorder=5)
    ax.scatter([0], [0], c=HEX_DARK_BLUE, s=80, zorder=6, edgecolors="white", linewidth=2)

    # Value display
    ax.text(0, -0.15, f"{value:.1f}{unit}", ha="center", va="center",
            fontsize=24, fontweight="bold", color=HEX_DARK_BLUE)
    ax.text(0, -0.35, title, ha="center", va="center",
            fontsize=10, color="#666666")

    ax.set_xlim(-1.3, 1.3)
    ax.set_ylim(-0.5, 1.2)
    ax.set_axis_off()

    fig.tight_layout()
    return _to_buffer(fig)


def chart_impact_heatmap(
    title: str,
    items: list[dict],
) -> io.BytesIO:
    """Impact-likelihood heatmap for strategic risk/opportunity analysis.

    Args:
        items: [{"factor": "name", "type": "driver|restraint|opportunity|challenge",
                 "impact": "High|Medium|Low"}]
    """
    _setup_chart_style()

    fig, ax = plt.subplots(figsize=(11, 6))
    _add_chart_title(fig, title, "Strategic factor positioning by type and impact severity")

    type_order = ["driver", "opportunity", "restraint"]
    impact_scores = {"low": 1, "medium": 2, "moderate": 2, "high": 3}
    # All colors from the project palette — teal + green for variety
    type_colors = {
        "driver":      HEX_NAVY,          # #006B77 — dark teal
        "opportunity": HEX_TEAL_GREEN,    # #009688 — teal-green
        "restraint":   HEX_FOREST_GREEN,  # #2E7D32 — forest green
    }

    # Group items by (type_idx, impact_val) so we can stack within each cell
    from collections import defaultdict
    cell_groups = defaultdict(list)
    for item in items:
        factor = item.get("factor", "")[:32]
        item_type = item.get("type", "").lower().strip()
        impact = item.get("impact", "medium").lower().strip()
        type_idx = type_order.index(item_type) if item_type in type_order else 0
        impact_val = impact_scores.get(impact, 2)
        color = type_colors.get(item_type, "#888888")
        cell_groups[(type_idx, impact_val)].append((factor, color))

    # Place items with deterministic vertical stacking — no random overlap
    for (type_idx, impact_val), group_items in cell_groups.items():
        n = len(group_items)
        # Spread vertically within the cell band (±0.30 max)
        offsets = [(k - (n - 1) / 2) * (0.30 / max(n - 1, 1)) * 2 for k in range(n)]
        for k, (factor, color) in enumerate(group_items):
            y = impact_val + offsets[k]
            ax.scatter(type_idx, y, s=420, c=color, alpha=0.92,
                       edgecolors="white", linewidth=2, zorder=4)
            # Labels placed above dots — no horizontal extension into neighbour columns
            ax.annotate(
                factor,
                (type_idx, y),
                textcoords="offset points",
                xytext=(0, 13),
                ha="center", va="bottom",
                fontsize=7.5, fontweight="bold",
                color="#003F48",
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.80),
            )

    ax.set_xticks(range(len(type_order)))
    ax.set_xticklabels([t.upper() for t in type_order], fontsize=10, fontweight="bold",
                       color=HEX_DARK_BLUE)
    ax.set_yticks([1, 2, 3])
    ax.set_yticklabels(["LOW", "MODERATE", "HIGH"], fontsize=10, fontweight="bold",
                       color=HEX_DARK_BLUE)
    ax.set_xlim(-0.7, len(type_order) - 0.3)
    ax.set_ylim(0.4, 3.6)

    # Background impact zones — three tints of the project palette
    ax.axhspan(0.5, 1.5, alpha=1.0, color="#F0FAFA", zorder=0)    # LOW  — warm gold tint
    ax.axhspan(1.5, 2.5, alpha=1.0, color="#E0F0F0", zorder=0)    # MED  — steel-blue tint
    ax.axhspan(2.5, 3.5, alpha=1.0, color="#C0E0E0", zorder=0)    # HIGH — navy tint

    # Subtle vertical dividers between columns
    for x in [0.5, 1.5, 2.5]:
        ax.axvline(x, color="#DDDDDD", linewidth=0.8, zorder=1)

    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(length=0)
    ax.yaxis.grid(False)

    fig.tight_layout(rect=[0, 0, 1, 0.92])
    return _to_buffer(fig)


def _empty_chart(title: str) -> io.BytesIO:
    """Return a placeholder chart when no data is available."""
    _setup_chart_style()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.text(0.5, 0.5, f"{title}\n(No data available)", ha="center", va="center",
            fontsize=14, color="#999999", transform=ax.transAxes)
    ax.set_axis_off()
    return _to_buffer(fig)
