"""Render a ClusteringRun as a single self-contained HTML file.

No external assets. One file you can double-click and inspect. Each cluster
is an expandable card showing: dimension label, value distribution chart,
per-claim table with domain/tier/value/raw excerpt, outlier flags, and the
time-series trend if linked.
"""
from __future__ import annotations

import html
import json  # noqa: F401  (used by write_json at bottom)
from pathlib import Path

from .models import ClusteredEstimate, ClusteringRun, RawClaim


_CSS = """
:root {
  --bg:#0f1115; --panel:#161a22; --border:#242937; --text:#e5e7eb;
  --muted:#8b92a8; --accent:#00bcd4; --good:#4ade80; --warn:#fbbf24;
  --bad:#f87171; --outlier:#ef4444;
}
* { box-sizing: border-box; }
body { margin:0; padding:24px; background:var(--bg); color:var(--text);
       font:14px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }
h1 { margin:0 0 4px 0; font-size:22px; font-weight:600; }
h2 { margin:32px 0 12px; font-size:16px; font-weight:600; color:var(--muted);
     border-bottom:1px solid var(--border); padding-bottom:6px; }
.topic { color:var(--accent); font-weight:600; }
.meta { color:var(--muted); font-size:12px; margin-bottom:18px; }
.summary-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
                gap:12px; margin:16px 0 28px; }
.stat { background:var(--panel); border:1px solid var(--border);
        border-radius:8px; padding:12px; }
.stat-label { color:var(--muted); font-size:11px; text-transform:uppercase;
              letter-spacing:0.4px; }
.stat-value { font-size:22px; font-weight:600; margin-top:4px; }
.cluster { background:var(--panel); border:1px solid var(--border);
           border-radius:10px; margin-bottom:14px; overflow:hidden; }
.cluster-header { padding:14px 16px; cursor:pointer; display:flex;
                  align-items:center; justify-content:space-between;
                  user-select:none; gap:12px; }
.cluster-header:hover { background:#1b1f2a; }
.cluster-title { font-weight:600; font-size:14px; flex:1; min-width:0; }
.cluster-dim { color:var(--muted); font-size:11px; font-family:monospace;
               margin-top:2px; }
.cluster-qchips { margin-top:6px; display:flex; flex-wrap:wrap; gap:4px 6px; }
.qchip { display:inline-flex; align-items:center; background:#1b1f2a;
         border:1px solid var(--border); border-radius:4px; overflow:hidden;
         font-family:monospace; font-size:11px; }
.qchip .qk { padding:2px 6px; color:var(--muted); background:#12151c;
             border-right:1px solid var(--border); }
.qchip .qv { padding:2px 6px; color:var(--text); }
.cluster-stats { display:flex; gap:14px; align-items:center;
                 font-size:12px; color:var(--muted); white-space:nowrap; }
.badge { padding:2px 8px; border-radius:10px; font-size:11px; font-weight:600;
         border:1px solid transparent; }
.badge-high { background:rgba(74,222,128,0.15); color:var(--good);
              border-color:rgba(74,222,128,0.3); }
.badge-medium { background:rgba(251,191,36,0.12); color:var(--warn);
                border-color:rgba(251,191,36,0.3); }
.badge-low, .badge-contested {
  background:rgba(248,113,113,0.12); color:var(--bad);
  border-color:rgba(248,113,113,0.3);
}
.badge-single_source { background:rgba(139,146,168,0.15); color:var(--muted);
                       border-color:rgba(139,146,168,0.3); }
.badge-trend { background:rgba(0,188,212,0.12); color:var(--accent);
               border-color:rgba(0,188,212,0.3); }
.cluster-body { display:none; padding:14px 16px; border-top:1px solid var(--border);
                background:#12151c; }
.cluster.open .cluster-body { display:block; }
.cluster-caret { transition:transform .15s; }
.cluster.open .cluster-caret { transform:rotate(90deg); }

.kpi-row { display:flex; flex-wrap:wrap; gap:12px 20px; margin-bottom:14px; }
.kpi { font-size:12px; }
.kpi .k { color:var(--muted); text-transform:uppercase; letter-spacing:0.3px; }
.kpi .v { font-size:18px; font-weight:600; margin-top:2px; }

.bar-chart { display:flex; align-items:flex-end; gap:2px; height:70px;
             margin:8px 0 14px; border-bottom:1px solid var(--border);
             padding-bottom:4px; }
.bar { flex:1; background:var(--accent); min-width:6px; border-radius:2px 2px 0 0;
       position:relative; transition:background .15s; }
.bar:hover { background:#22d3ee; }
.bar.outlier { background:var(--outlier); }
.bar-label { position:absolute; top:-18px; left:50%; transform:translateX(-50%);
             font-size:10px; color:var(--muted); white-space:nowrap; }

table { width:100%; border-collapse:collapse; font-size:12px; }
th, td { padding:6px 8px; text-align:left; border-bottom:1px solid var(--border);
         vertical-align:top; }
th { color:var(--muted); font-weight:500; text-transform:uppercase;
     letter-spacing:0.3px; font-size:11px; }
td.num { font-family:monospace; text-align:right; white-space:nowrap; }
tr.outlier-row { background:rgba(239,68,68,0.05); }
tr.outlier-row td.num { color:var(--outlier); font-weight:600; }
.tier { display:inline-block; padding:1px 6px; border-radius:4px;
        font-size:10px; font-weight:600; }
.tier-government, .tier-multilateral, .tier-industry_body {
  background:rgba(74,222,128,0.15); color:var(--good);
}
.tier-tier1_media, .tier-analyst_firm {
  background:rgba(0,188,212,0.12); color:var(--accent);
}
.tier-trade_press { background:rgba(251,191,36,0.12); color:var(--warn); }
.tier-blog, .tier-unknown {
  background:rgba(139,146,168,0.15); color:var(--muted);
}
.url { color:var(--muted); font-size:11px; word-break:break-all; }
.url:hover { color:var(--accent); }
.excerpt { color:var(--muted); font-style:italic; font-size:11px;
           max-width:400px; }

/* Topic-profile + off-topic blocks */
.profile-card { background:var(--panel); border:1px solid var(--border);
                border-radius:10px; padding:14px 16px; margin:0 0 18px;
                font-size:13px; line-height:1.6; }
.profile-card .pk { color:var(--muted); display:inline-block; min-width:130px;
                    font-size:11px; text-transform:uppercase;
                    letter-spacing:0.4px; }
.profile-card .pv { color:var(--text); }
.offtopic-toggle { background:var(--panel); border:1px solid var(--border);
                   border-radius:10px; padding:12px 16px; cursor:pointer;
                   user-select:none; display:flex; align-items:center;
                   justify-content:space-between; gap:12px;
                   margin: 24px 0 10px; }
.offtopic-toggle:hover { background:#1b1f2a; }
.offtopic-list { display:none; background:#12151c;
                 border:1px solid var(--border); border-radius:10px;
                 padding:6px 0; margin-bottom:14px; }
.offtopic-toggle.open + .offtopic-list { display:block; }
.offtopic-row { padding:8px 16px; border-bottom:1px solid var(--border);
                display:grid;
                grid-template-columns: 80px 80px 180px 1fr;
                gap: 10px; align-items:start; font-size:12px; }
.offtopic-row:last-child { border-bottom:none; }
.offtopic-row .rs { color:var(--muted); font-family:monospace; }
"""

_JS = """
document.querySelectorAll('.cluster-header').forEach(h => {
  h.addEventListener('click', () => h.parentElement.classList.toggle('open'));
});
document.querySelectorAll('.offtopic-toggle').forEach(h => {
  h.addEventListener('click', () => h.classList.toggle('open'));
});
// auto-open first cluster
const first = document.querySelector('.cluster');
if (first) first.classList.add('open');
"""


def _esc(s) -> str:
    return html.escape(str(s) if s is not None else "")


def _pick_currency_scale(values: list[float]) -> tuple[float, str]:
    """For currency units (USD_B etc.) the canonical store is BILLIONS. Pick
    a display multiplier + suffix based on the median value so e.g. a cluster
    of GPU SKU prices ($1999 stored as 0.001999B) renders as '$1.99K' rather
    than '$0.00B'.

    Returns (multiplier, suffix). Multiply stored value by multiplier to get
    the displayed number; suffix is the units label.
    """
    if not values:
        return 1.0, "B"
    sorted_v = sorted(values)
    median = sorted_v[len(sorted_v) // 2]
    if median >= 1.0:
        return 1.0, "B"          # billions: display as-is
    if median >= 0.001:
        return 1_000.0, "M"      # millions
    if median >= 0.000_001:
        return 1_000_000.0, "K"  # thousands
    return 1_000_000_000.0, ""   # raw dollars (no suffix)


def _format_value(v: float, canonical_unit: str,
                  scale: tuple[float, str] | None = None) -> str:
    if canonical_unit.endswith("_B"):
        currency = canonical_unit[:-2]   # USD, EUR, ...
        symbol = "$" if currency == "USD" else f"{currency} "
        if scale is None:
            scale = (1.0, "B")
        mult, suffix = scale
        scaled = v * mult
        if suffix:
            return f"{symbol}{scaled:.2f}{suffix}"
        # Raw dollars — no decimal places below $1
        return f"{symbol}{scaled:,.0f}"
    if canonical_unit == "percent":
        return f"{v:.1f}%"
    if canonical_unit == "units_M":
        return f"{v:.2f}M units"
    if canonical_unit == "usd_per_unit":
        return f"${v:.2f}/unit"
    return f"{v:.3g} {canonical_unit}"


def _render_bar_chart(est: ClusteredEstimate, scale=None) -> str:
    if not est.values:
        return ""
    max_v = max(est.values) or 1.0
    min_v = min(est.values)
    rng = (max_v - min_v) or 1.0
    outliers = set(est.outlier_claim_indices)
    bars = []
    for i, v in enumerate(est.values):
        h_pct = 20 + 80 * ((v - min_v) / rng if rng else 0.5)
        cls = "bar outlier" if i in outliers else "bar"
        title = f"{_format_value(v, est.canonical_unit, scale)} — {_esc(est.claims[i].source_domain)}"
        bars.append(f'<div class="{cls}" style="height:{h_pct:.0f}%" title="{title}"></div>')
    return f'<div class="bar-chart">{"".join(bars)}</div>'


def _render_claim_row(claim: RawClaim, value_display: str, is_outlier: bool) -> str:
    cls = "outlier-row" if is_outlier else ""
    as_of = (claim.qualifiers or {}).get("as_of") or "-"
    fp = (claim.qualifiers or {}).get("fiscal_period") or ""
    if fp and fp != "FY" and as_of != "-":
        as_of = f"{fp} {as_of}"
    return f"""
    <tr class="{cls}">
      <td class="num">{_esc(value_display)}{' ⚠️' if is_outlier else ''}</td>
      <td><span class="tier tier-{_esc(claim.source_tier)}">{_esc(claim.source_tier)}</span></td>
      <td><a class="url" href="{_esc(claim.source_url)}" target="_blank">{_esc(claim.source_domain)}</a></td>
      <td>{_esc(as_of)}</td>
      <td class="excerpt">{_esc((claim.raw_text or '')[:260])}</td>
    </tr>"""


def _render_cluster(est: ClusteredEstimate, idx: int) -> str:
    unit = est.canonical_unit
    outliers = set(est.outlier_claim_indices)
    # Pick a single display scale for currency clusters so all bars + values
    # share units (e.g. "$1.99K" not a mix of "$0.00B" and "$1.99K").
    scale = _pick_currency_scale(est.values) if unit.endswith("_B") else None

    trend_badge = ""
    if est.trend_slope_pct_per_year is not None:
        sign = "+" if est.trend_slope_pct_per_year >= 0 else ""
        trend_badge = f'<span class="badge badge-trend">trend {sign}{est.trend_slope_pct_per_year}%/yr</span>'

    family_badge = ""
    if est.family_id:
        family_badge = '<span class="badge badge-trend">time-series</span>'

    rows = []
    for i, claim in enumerate(est.claims):
        val_disp = _format_value(est.values[i], unit, scale)
        rows.append(_render_claim_row(claim, val_disp, i in outliers))

    # Build qualifier-tag strip from the cluster's qualifier_summary.
    # Each key:value pair becomes a chip under the descriptor — matches
    # Wikidata's qualifier-display convention.
    d = est.dimension
    qsum = d.qualifier_summary or {}
    # Ordering: subject + metric_kind first (they define the cluster identity),
    # then segment / scope / geography, then time-related keys, then the rest.
    _priority = {
        "subject": 0, "metric_kind": 1, "segment": 2, "scope": 3,
        "geography": 4, "as_of": 5, "fiscal_period": 6, "fiscal_basis": 7,
        "reporting_standard": 8, "measurement_basis": 9, "is_forecast": 10,
    }
    chips: list[str] = []
    for key in sorted(qsum.keys(), key=lambda k: (_priority.get(k, 99), k)):
        vals = qsum[key]
        if not vals:
            continue
        display = ", ".join(vals[:4])
        if len(vals) > 4:
            display += f" +{len(vals) - 4}"
        chips.append(
            f'<span class="qchip"><span class="qk">{_esc(key)}</span>'
            f'<span class="qv">{_esc(display)}</span></span>'
        )
    chips.append(f'<span class="qchip"><span class="qk">unit</span>'
                 f'<span class="qv">{_esc(d.unit_family)}</span></span>')
    meta_strip = "".join(chips)

    return f"""
    <div class="cluster">
      <div class="cluster-header">
        <div style="flex:1;min-width:0;">
          <div class="cluster-title">#{idx + 1}. {_esc(est.dimension.descriptor)}</div>
          <div class="cluster-qchips">{meta_strip}</div>
        </div>
        <div class="cluster-stats">
          <span class="badge badge-{_esc(est.consensus_level)}">{_esc(est.consensus_level)}</span>
          {trend_badge}
          {family_badge}
          <span>{est.n_claims} claims</span>
          <span>{est.n_unique_sources} sources</span>
          <span class="cluster-caret">▶</span>
        </div>
      </div>
      <div class="cluster-body">
        <div class="kpi-row">
          <div class="kpi"><div class="k">Weighted mean</div>
               <div class="v">{_esc(_format_value(est.weighted_mean, unit))}</div></div>
          <div class="kpi"><div class="k">Median</div>
               <div class="v">{_esc(_format_value(est.median, unit))}</div></div>
          <div class="kpi"><div class="k">Range</div>
               <div class="v" style="font-size:14px;">{_esc(_format_value(est.min_value, unit))}
               &nbsp;&rarr;&nbsp; {_esc(_format_value(est.max_value, unit))}</div></div>
          <div class="kpi"><div class="k">Spread</div>
               <div class="v">{est.pct_spread * 100:.1f}%</div></div>
          <div class="kpi"><div class="k">StdDev</div>
               <div class="v">{_esc(_format_value(est.stddev, unit))}</div></div>
        </div>
        {_render_bar_chart(est)}
        <table>
          <thead><tr>
            <th>Value</th><th>Tier</th><th>Source</th><th>As-of</th><th>Excerpt</th>
          </tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </div>"""


def _render_profile_card(run: ClusteringRun) -> str:
    p = run.topic_profile
    if p is None:
        return ""

    def _row(label, value):
        return (f'<div><span class="pk">{_esc(label)}</span> '
                f'<span class="pv">{_esc(value) if value else "(none)"}</span></div>')

    return f"""
    <div class="profile-card">
      {_row('Subject',       p.topic_subject)}
      {_row('Domain',        p.topic_domain)}
      {_row('Expected metrics', ', '.join(p.expected_metric_kinds))}
      {_row('Key dimensions',   ', '.join(p.key_dimensions))}
      {_row('Positive signals', ', '.join(p.positive_signals[:8]))}
      {_row('Off-topic signals',', '.join(p.negative_signals[:8]))}
      {_row('Reasoning',     p.profile_reasoning)}
    </div>"""


def _render_offtopic_section(run: ClusteringRun) -> str:
    if not run.off_topic_claims:
        return ""
    rows = []
    # Sort by relevance ascending (most off-topic first) so the user audits
    # the worst offenders.
    claims_sorted = sorted(
        run.off_topic_claims,
        key=lambda c: (c.topic_relevance if c.topic_relevance is not None else 0.0),
    )
    for c in claims_sorted[:200]:   # cap for HTML weight
        score = c.topic_relevance if c.topic_relevance is not None else 0.0
        rows.append(f"""
          <div class="offtopic-row">
            <div class="rs">{score:.3f}</div>
            <div><span class="tier tier-{_esc(c.source_tier)}">{_esc(c.source_tier)}</span></div>
            <div><a class="url" href="{_esc(c.source_url)}" target="_blank">{_esc(c.source_domain)}</a></div>
            <div class="excerpt">{_esc((c.raw_text or '')[:280])}</div>
          </div>""")
    capped_note = (
        f" (showing 200 of {len(run.off_topic_claims)})"
        if len(run.off_topic_claims) > 200 else ""
    )
    return f"""
    <div class="offtopic-toggle">
      <div>
        <strong>Out-of-scope findings</strong>
        <div style="color:var(--muted); font-size:11px; margin-top:2px;">
          Claims the relevance gate flagged as off-topic for this profile.
          They are NOT in the clusters above. Click to expand{capped_note}.
        </div>
      </div>
      <div class="cluster-stats">
        <span class="badge badge-single_source">{len(run.off_topic_claims)} claims</span>
      </div>
    </div>
    <div class="offtopic-list">
      <div class="offtopic-row" style="color:var(--muted); font-weight:600;">
        <div>Score</div><div>Tier</div><div>Source</div><div>Excerpt</div>
      </div>
      {''.join(rows)}
    </div>"""


def render_html(run: ClusteringRun) -> str:
    consensus_dist = {}
    for e in run.estimates:
        consensus_dist[e.consensus_level] = consensus_dist.get(e.consensus_level, 0) + 1
    multi_source = sum(1 for e in run.estimates if e.n_unique_sources >= 2)

    stat_cards = [
        ("Topic", f'<span class="topic">{_esc(run.topic)}</span>'),
        ("Sources searched", run.n_sources_searched),
        ("Sources with claims", run.n_sources_with_claims),
        ("Raw claims", run.n_raw_claims),
        ("Dimensions (clusters)", run.n_dimensions),
        ("Multi-source clusters", multi_source),
        ("Total cost", f"${run.cost_total_usd:.4f}"),
        ("LLM judge calls", run.n_judge_calls),
    ]
    stat_html = "".join(
        f'<div class="stat"><div class="stat-label">{_esc(k)}</div>'
        f'<div class="stat-value">{v}</div></div>'
        for k, v in stat_cards
    )

    consensus_bars = "".join(
        f'<div class="stat"><div class="stat-label">{_esc(k)}</div>'
        f'<div class="stat-value">{v}</div></div>'
        for k, v in sorted(consensus_dist.items(),
                           key=lambda x: ["high","medium","low","contested","single_source"].index(x[0])
                           if x[0] in ["high","medium","low","contested","single_source"] else 9)
    )

    clusters_html = "".join(_render_cluster(e, i) for i, e in enumerate(run.estimates))
    profile_html = _render_profile_card(run)
    offtopic_html = _render_offtopic_section(run)

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Claim Clusters - {_esc(run.topic)}</title>
<style>{_CSS}</style></head>
<body>
<h1>Claim Clusters</h1>
<div class="meta">
  <span class="topic">{_esc(run.topic)}</span> &middot;
  started {_esc(run.started_at[:19])} &middot;
  finished {_esc(run.finished_at[:19])}
</div>

<h2>Summary</h2>
<div class="summary-grid">{stat_html}</div>

<h2>Topic Profile (what this run is optimising for)</h2>
{profile_html or '<div class="stat">No topic profile generated.</div>'}

<h2>Consensus Distribution</h2>
<div class="summary-grid">{consensus_bars or '<div class="stat">No clusters</div>'}</div>

<h2>Clusters (sorted by claim count, then consensus quality)</h2>
{clusters_html or '<div class="stat">No clusters produced.</div>'}

{offtopic_html}

<script>{_JS}</script>
</body></html>"""


def write_html(run: ClusteringRun, out_path: str | Path) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(run), encoding="utf-8")
    return path


def write_json(run: ClusteringRun, out_path: str | Path) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = run.model_dump(mode="json")
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
