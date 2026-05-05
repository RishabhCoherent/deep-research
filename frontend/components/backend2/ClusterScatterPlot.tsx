"use client";

import { useEffect, useRef, useState } from "react";
import type { Backend2DimensionalCluster } from "@/lib/types-backend2";

// ─── Palette (dark = trusted, light = uncertain) ──────────────────────────
const FILL: Record<string, string> = {
  high:          "#484848",
  medium:        "#7a7a7a",
  low:           "#a6a6a6",
  contested:     "#c4c4c4",
  single_source: "#dedede",
};

const LABEL_MAP: Record<string, string> = {
  high:          "High consensus",
  medium:        "Medium",
  low:           "Low",
  contested:     "Contested",
  single_source: "Single source",
};

// Horizontal anchor positions per consensus group (normalised 0–1)
const ANCHOR_X: Record<string, number> = {
  high: 0.12, medium: 0.31, low: 0.50, contested: 0.69, single_source: 0.88,
};
const CONSENSUS_ORDER = ["high","medium","low","contested","single_source"] as const;

// ─── Dummy EV-market data ─────────────────────────────────────────────────
const DUMMY: Partial<Backend2DimensionalCluster>[] = [
  { dimension:{descriptor:"EV global market size",unit_family:"USD"},     consensus_level:"high",          n_unique_sources:7, n_claims:5, pct_spread:0.08, weighted_mean:320  },
  { dimension:{descriptor:"CAGR 2025–2030",unit_family:"percent"},        consensus_level:"medium",        n_unique_sources:4, n_claims:3, pct_spread:0.22, weighted_mean:21   },
  { dimension:{descriptor:"Battery pack cost $/kWh",unit_family:"USD"},   consensus_level:"high",          n_unique_sources:6, n_claims:6, pct_spread:0.12, weighted_mean:110  },
  { dimension:{descriptor:"Charging infra spend",unit_family:"USD"},      consensus_level:"low",           n_unique_sources:2, n_claims:2, pct_spread:0.45, weighted_mean:84   },
  { dimension:{descriptor:"Policy subsidy $/vehicle",unit_family:"USD"},  consensus_level:"contested",     n_unique_sources:3, n_claims:4, pct_spread:0.61, weighted_mean:7500 },
  { dimension:{descriptor:"Range improvement % YoY",unit_family:"percent"},consensus_level:"medium",       n_unique_sources:5, n_claims:4, pct_spread:0.18, weighted_mean:15   },
  { dimension:{descriptor:"Mineral supply risk",unit_family:"score"},     consensus_level:"single_source", n_unique_sources:1, n_claims:1, pct_spread:0.0,  weighted_mean:6.8  },
  { dimension:{descriptor:"BEV market share",unit_family:"percent"},      consensus_level:"high",          n_unique_sources:8, n_claims:7, pct_spread:0.09, weighted_mean:18   },
  { dimension:{descriptor:"Fleet electrification",unit_family:"percent"}, consensus_level:"low",           n_unique_sources:2, n_claims:2, pct_spread:0.38, weighted_mean:9    },
  { dimension:{descriptor:"CO₂ reduction vs ICE",unit_family:"percent"},  consensus_level:"high",          n_unique_sources:6, n_claims:5, pct_spread:0.14, weighted_mean:52   },
  { dimension:{descriptor:"Consumer payback period",unit_family:"months"},consensus_level:"medium",        n_unique_sources:3, n_claims:3, pct_spread:0.27, weighted_mean:6.2  },
  { dimension:{descriptor:"Solid-state battery ETA",unit_family:"years"}, consensus_level:"contested",     n_unique_sources:3, n_claims:4, pct_spread:0.55, weighted_mean:4    },
];

// ─── Internal bubble ──────────────────────────────────────────────────────
interface Bubble {
  id: number;
  x: number; y: number;
  vx: number; vy: number;
  r: number;
  fill: string;
  consensus: string;
  label: string;
  unit: string;
  mean: number;
  nClaims: number;
  nSources: number;
  spreadPct: number;
}

function buildBubbles(list: Partial<Backend2DimensionalCluster>[], W: number, H: number): Bubble[] {
  if (!list.length) return [];
  const maxC = Math.max(...list.map(c => c.n_claims ?? 1), 1);
  // Scale radius down when many bubbles
  const scale = list.length > 20 ? 0.65 : list.length > 12 ? 0.82 : 1;

  return list.map((c, i) => {
    const con = c.consensus_level ?? "single_source";
    const nc  = c.n_claims ?? 1;
    const ax  = (ANCHOR_X[con] ?? 0.5) * W;
    const ay  = H * 0.50;
    const r   = (11 + (nc / maxC) * 25) * scale;
    const angle = (i / list.length) * Math.PI * 2;
    return {
      id: i,
      x: ax + Math.cos(angle) * r * 2.5,
      y: ay + Math.sin(angle) * r * 2.5,
      vx: 0, vy: 0,
      r,
      fill:      FILL[con] ?? "#888",
      consensus: con,
      label:     c.dimension?.descriptor ?? "—",
      unit:      c.dimension?.unit_family ?? "",
      mean:      c.weighted_mean ?? 0,
      nClaims:   nc,
      nSources:  c.n_unique_sources ?? 1,
      spreadPct: (c.pct_spread ?? 0) * 100,
    };
  });
}

// ─── Physics ──────────────────────────────────────────────────────────────
function physicsStep(bs: Bubble[], W: number, H: number, str = 1) {
  const K_ANC  = 0.018 * str;
  const K_REP  = 2.2;
  const DAMP   = 0.80;
  const AY     = H * 0.50;

  for (let i = 0; i < bs.length; i++) {
    const b  = bs[i];
    const ax = (ANCHOR_X[b.consensus] ?? 0.5) * W;

    // Anchor spring (horizontal only — vertical gathers to mid)
    b.vx += (ax - b.x) * K_ANC;
    b.vy += (AY - b.y) * K_ANC * 0.6;

    // Bubble–bubble repulsion
    for (let j = 0; j < bs.length; j++) {
      if (i === j) continue;
      const o   = bs[j];
      const dx  = b.x - o.x;
      const dy  = b.y - o.y;
      const d   = Math.hypot(dx, dy) || 0.01;
      const min = b.r + o.r + 5;
      if (d < min) {
        const f = K_REP * (min - d) / d;
        b.vx += dx * f;
        b.vy += dy * f;
      }
    }

    b.vx *= DAMP;
    b.vy *= DAMP;
    b.x   = Math.max(b.r + 10, Math.min(W - b.r - 10, b.x + b.vx));
    b.y   = Math.max(b.r + 36, Math.min(H - b.r - 14, b.y + b.vy));
  }
}

// ─── Soft top-lit shading (clean, not billiard-ball) ────────────────────────
function sphereGrad(
  ctx: CanvasRenderingContext2D,
  sx: number, sy: number, r: number, hex: string,
): CanvasGradient {
  const ri = parseInt(hex.slice(1,3), 16);
  const gi = parseInt(hex.slice(3,5), 16);
  const bi = parseInt(hex.slice(5,7), 16);
  // Top highlight: blend 22% toward white
  const tr = Math.min(255, Math.round(ri + (255-ri)*0.22));
  const tg = Math.min(255, Math.round(gi + (255-gi)*0.22));
  const tb = Math.min(255, Math.round(bi + (255-bi)*0.22));
  // Bottom shadow: 84% of original value (very subtle)
  const br = Math.round(ri*0.84);
  const bg = Math.round(gi*0.84);
  const bb = Math.round(bi*0.84);
  const g  = ctx.createLinearGradient(sx, sy - r, sx, sy + r);
  g.addColorStop(0,   `rgb(${tr},${tg},${tb})`);
  g.addColorStop(0.5, hex);
  g.addColorStop(1,   `rgb(${br},${bg},${bb})`);
  return g;
}

// ─── Render ───────────────────────────────────────────────────────────────
function renderFrame(
  canvas: HTMLCanvasElement,
  bubbles: Bubble[],
  hoverIdx: number,
) {
  const ctx = canvas.getContext("2d");
  if (!ctx || canvas.width === 0 || canvas.height === 0) return;

  const dpr  = window.devicePixelRatio || 1;
  const cssW = canvas.width  / dpr;
  const cssH = canvas.height / dpr;

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);

  // Background: matches glass-card surface (rgba(255,255,255,0.70) → use near-white)
  ctx.fillStyle = "#f9f9f9";
  ctx.fillRect(0, 0, cssW, cssH);

  // ── Group column separators ───────────────────────────────────────
  for (let i = 0; i < CONSENSUS_ORDER.length - 1; i++) {
    const x1 = ANCHOR_X[CONSENSUS_ORDER[i]]   * cssW;
    const x2 = ANCHOR_X[CONSENSUS_ORDER[i+1]] * cssW;
    const mx = (x1 + x2) / 2;
    ctx.beginPath();
    ctx.moveTo(mx, 32);
    ctx.lineTo(mx, cssH - 16);
    ctx.strokeStyle = "rgba(0,0,0,0.07)";
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 7]);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // ── Group header labels ───────────────────────────────────────────
  for (const key of CONSENSUS_ORDER) {
    const ax = ANCHOR_X[key] * cssW;
    const hasBubble = bubbles.some(b => b.consensus === key);
    ctx.font = "9px 'JetBrains Mono',monospace";
    ctx.textAlign = "center";
    ctx.fillStyle = hasBubble ? "rgba(0,0,0,0.38)" : "rgba(0,0,0,0.14)";
    ctx.fillText(LABEL_MAP[key].toUpperCase(), ax, 20);
  }

  if (!bubbles.length) { ctx.setTransform(1,0,0,1,0,0); return; }

  // ── Shadow ellipses (soft, light) ────────────────────────────────
  for (const b of bubbles) {
    ctx.beginPath();
    ctx.ellipse(b.x, b.y + b.r * 0.94, b.r * 0.75, b.r * 0.16, 0, 0, Math.PI*2);
    ctx.fillStyle = "rgba(0,0,0,0.06)";
    ctx.fill();
  }

  // ── Sort front-to-back by y ───────────────────────────────────────
  const sorted = bubbles
    .map((b, i) => ({ b, i }))
    .sort((a, b) => a.b.y - b.b.y);

  // ── Draw bubbles ──────────────────────────────────────────────────
  for (const { b, i } of sorted) {
    const isHov = i === hoverIdx;

    // Outer glow on hover
    if (isHov) {
      const glow = ctx.createRadialGradient(b.x, b.y, b.r * 0.5, b.x, b.y, b.r + 20);
      glow.addColorStop(0,   `${b.fill}28`);
      glow.addColorStop(1,   `${b.fill}00`);
      ctx.beginPath();
      ctx.arc(b.x, b.y, b.r + 20, 0, Math.PI*2);
      ctx.fillStyle = glow;
      ctx.fill();
    }

    // Sphere
    ctx.beginPath();
    ctx.arc(b.x, b.y, b.r, 0, Math.PI*2);
    ctx.fillStyle = sphereGrad(ctx, b.x, b.y, b.r, b.fill);
    ctx.fill();

    // Rim
    ctx.beginPath();
    ctx.arc(b.x, b.y, b.r, 0, Math.PI*2);
    ctx.strokeStyle = isHov ? "rgba(0,0,0,0.32)" : "rgba(0,0,0,0.10)";
    ctx.lineWidth = isHov ? 1.5 : 0.8;
    ctx.stroke();

    // Label inside bubble (if large enough)
    if (b.r >= 16) {
      const isLight = b.fill === "#c4c4c4" || b.fill === "#dedede";
      const fs      = Math.max(7, Math.min(9, b.r * 0.28));
      const maxCh   = Math.max(4, Math.floor(b.r * 1.75 / (fs * 0.60)));
      const text    = b.label.length > maxCh ? b.label.slice(0, maxCh - 1) + "…" : b.label;
      ctx.font = `${fs}px 'JetBrains Mono',monospace`;
      ctx.fillStyle = isLight ? "rgba(0,0,0,0.50)" : "rgba(255,255,255,0.82)";
      ctx.textAlign = "center";
      ctx.fillText(text, b.x, b.y + fs * 0.38);
    }
  }

  ctx.setTransform(1,0,0,1,0,0);
}

// ─── Format value ─────────────────────────────────────────────────────────
// Handles raw large numbers (e.g. v=3.5e20 from backend without unit normalisation)
// and legacy pre-scaled values (v=95.73, unit=USD means $95.73B)
function siScale(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e12) return `${(v / 1e12).toPrecision(3)}T`;
  if (a >= 1e9)  return `${(v / 1e9).toPrecision(3)}B`;
  if (a >= 1e6)  return `${(v / 1e6).toPrecision(3)}M`;
  if (a >= 1e3)  return `${(v / 1e3).toPrecision(3)}K`;
  return v.toPrecision(3);
}

function fmtVal(unit: string, v: number): string {
  if (!isFinite(v)) return "—";
  const abs = Math.abs(v);
  const sym = unit === "EUR" ? "€" : unit === "GBP" ? "£" : "$";

  if (["USD", "EUR", "GBP"].includes(unit)) {
    // Large raw values (>= 1000): treat as absolute dollar amounts
    if (abs >= 1e3) return `${sym}${siScale(v)}`;
    // Small values: legacy pre-scaled to billions
    if (abs >= 1)     return `${sym}${v.toFixed(1)}B`;
    if (abs >= 0.001) return `${sym}${(v * 1000).toFixed(0)}M`;
    return `${sym}${(v * 1e6).toFixed(0)}K`;
  }
  if (unit === "percent") return `${v.toFixed(1)}%`;
  if (unit === "months")  return `${v.toFixed(1)} mo`;
  if (unit === "score")   return v.toFixed(2);

  // Unknown / other unit: smart SI scaling, suppress "unknown" label
  const label = (unit && unit !== "unknown") ? ` ${unit}` : "";
  return `${siScale(v)}${label}`;
}

// ─── Component ────────────────────────────────────────────────────────────
interface TooltipInfo { x: number; y: number; b: Bubble; }
interface Props { clusters: Backend2DimensionalCluster[]; isDummy?: boolean; }

export default function ClusterScatterPlot({ clusters, isDummy }: Props) {
  const canvasRef  = useRef<HTMLCanvasElement>(null);
  const rafRef     = useRef(0);
  const bubblesRef = useRef<Bubble[]>([]);
  const hoverRef   = useRef(-1);
  const sizeRef    = useRef({ W: 0, H: 0 });
  const runRef     = useRef(false);
  const srcRef     = useRef<Partial<Backend2DimensionalCluster>[]>([]);

  const [tooltip, setTooltip] = useState<TooltipInfo|null>(null);

  const src = (isDummy || clusters.length === 0) ? DUMMY : clusters;
  srcRef.current = src;

  // ─── Init/re-init bubbles ───────────────────────────────────────────
  const initBubbles = (W: number, H: number) => {
    bubblesRef.current = buildBubbles(srcRef.current, W, H);
    for (let i = 0; i < 220; i++) physicsStep(bubblesRef.current, W, H);
  };

  // ─── Mount once ────────────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const resize = () => {
      const dpr  = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      canvas.width  = Math.round(rect.width  * dpr);
      canvas.height = Math.round(rect.height * dpr);
      sizeRef.current = { W: rect.width, H: rect.height };
      initBubbles(rect.width, rect.height);
    };

    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    resize();

    runRef.current = true;
    const animate = () => {
      if (!runRef.current) return;
      const { W, H } = sizeRef.current;
      if (W && H) {
        physicsStep(bubblesRef.current, W, H, 0.12);
        renderFrame(canvas, bubblesRef.current, hoverRef.current);
      }
      rafRef.current = requestAnimationFrame(animate);
    };
    rafRef.current = requestAnimationFrame(animate);

    return () => {
      runRef.current = false;
      cancelAnimationFrame(rafRef.current);
      ro.disconnect();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-init when cluster data changes
  useEffect(() => {
    const { W, H } = sizeRef.current;
    if (W && H) initBubbles(W, H);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clusters]);

  // ─── Mouse ─────────────────────────────────────────────────────────
  const onMouseMove = (e: React.MouseEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx   = e.clientX - rect.left;
    const my   = e.clientY - rect.top;

    let bestIdx = -1, bestD = Infinity;
    bubblesRef.current.forEach((b, i) => {
      const d = Math.hypot(mx - b.x, my - b.y);
      if (d < b.r + 6 && d < bestD) { bestD = d; bestIdx = i; }
    });

    if (bestIdx !== hoverRef.current) {
      hoverRef.current = bestIdx;
    }
    if (bestIdx >= 0) {
      setTooltip({ x: mx, y: my, b: bubblesRef.current[bestIdx] });
    } else {
      setTooltip(null);
    }
  };

  const onMouseLeave = () => {
    hoverRef.current = -1;
    setTooltip(null);
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Canvas area */}
      <div
        className="relative w-full rounded-xl overflow-hidden"
        style={{ height: "clamp(400px, 50vh, 580px)" }}
      >
        <canvas
          ref={canvasRef}
          className="block w-full h-full"
          style={{ cursor: "default" }}
          onMouseMove={onMouseMove}
          onMouseLeave={onMouseLeave}
        />

        {/* Tooltip */}
        {tooltip && (() => {
          const b = tooltip.b;
          const canvasW = canvasRef.current?.getBoundingClientRect().width ?? 600;
          return (
            <div
              className="absolute z-30 pointer-events-none"
              style={{
                left: Math.min(tooltip.x + 14, canvasW - 248),
                top:  Math.max(8, tooltip.y - 104),
                width: 236,
              }}
            >
              <div className="bg-background/95 backdrop-blur-sm border border-foreground/8 rounded-2xl shadow-xl px-4 py-3 space-y-2">
                <p className="text-[11.5px] font-display leading-snug text-foreground">{b.label}</p>
                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[9px] font-mono border"
                    style={{
                      background:  `${b.fill}18`,
                      color:       b.fill === "#cacaca" ? "#888" : b.fill,
                      borderColor: `${b.fill}44`,
                    }}
                  >
                    <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: b.fill }} />
                    {LABEL_MAP[b.consensus]}
                  </span>
                  {b.mean !== 0 && (
                    <span className="font-mono text-[10px] text-black/40">{fmtVal(b.unit, b.mean)}</span>
                  )}
                </div>
                <div className="grid grid-cols-3 gap-x-2 gap-y-0.5 text-[9px] font-mono text-black/32">
                  <span>{b.nClaims} claims</span>
                  <span>{b.nSources} sources</span>
                  <span>{b.spreadPct > 100 ? ">100" : b.spreadPct.toFixed(0)}% spread</span>
                </div>
              </div>
            </div>
          );
        })()}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 px-1">
        {CONSENSUS_ORDER.map(key => (
          <div key={key} className="flex items-center gap-2">
            <div
              className="rounded-full shrink-0"
              style={{ width: 9, height: 9, background: FILL[key], border: "1.5px solid rgba(0,0,0,0.10)" }}
            />
            <span className="text-[9px] font-mono text-muted-foreground">{LABEL_MAP[key]}</span>
          </div>
        ))}
        <span className="ml-auto text-[8.5px] font-mono text-black/22 italic">bubble size ∝ claims</span>
      </div>
    </div>
  );
}
