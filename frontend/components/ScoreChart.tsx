"use client";

import { useEffect, useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import { LAYER_NAMES } from "@/lib/types";
import type { LayerEvaluation } from "@/lib/types";

interface ScoreChartProps {
  evaluations: LayerEvaluation[];
}

const DIMENSIONS = [
  { key: "factual_density", label: "Factual Density" },
  { key: "source_grounding", label: "Source Grounding" },
  { key: "analytical_depth", label: "Analytical Depth" },
  { key: "specificity", label: "Specificity" },
  { key: "insight_quality", label: "Insight Quality" },
  { key: "completeness", label: "Completeness" },
];

const LAYER_STYLES: Record<
  number,
  { fill: string; stroke: string; dotClass: string; textClass: string }
> = {
  0: {
    fill: "rgba(0,0,0,0.04)",
    stroke: "rgba(0,0,0,0.25)",
    dotClass: "bg-foreground/30",
    textClass: "text-muted-foreground",
  },
  1: {
    fill: "rgba(124,58,237,0.10)",
    stroke: "#7C3AED",
    dotClass: "bg-purple",
    textClass: "text-purple",
  },
  2: {
    fill: "rgba(0,0,0,0.08)",
    stroke: "rgba(0,0,0,0.70)",
    dotClass: "bg-foreground",
    textClass: "text-foreground",
  },
};

function getScore(ev: LayerEvaluation, dimKey: string): number {
  const entry = ev.scores?.[dimKey];
  if (typeof entry === "object" && entry !== null) {
    return (entry as { score: number }).score ?? 0;
  }
  return 0;
}

function getAvgScore(ev: LayerEvaluation): number {
  let total = 0;
  let count = 0;
  for (const dim of DIMENSIONS) {
    const s = getScore(ev, dim.key);
    if (s > 0) {
      total += s;
      count++;
    }
  }
  return count > 0 ? Math.round((total / count) * 10) / 10 : 0;
}

export function ScoreChart({ evaluations }: ScoreChartProps) {
  const [animated, setAnimated] = useState(false);
  const [hoveredLayer, setHoveredLayer] = useState<number | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setAnimated(true), 200);
    return () => clearTimeout(timer);
  }, []);

  // Radar chart geometry
  const cx = 180;
  const cy = 180;
  const maxRadius = 140;
  const numAxes = DIMENSIONS.length;
  const maxVal = 10;

  const getPoint = useCallback(
    (axisIndex: number, value: number): { x: number; y: number } => {
      const angle = (Math.PI * 2 * axisIndex) / numAxes - Math.PI / 2;
      const r = (value / maxVal) * maxRadius;
      return {
        x: Math.round(cx + r * Math.cos(angle)),
        y: Math.round(cy + r * Math.sin(angle)),
      };
    },
    [cx, cy, maxRadius, numAxes, maxVal]
  );

  const getPolygonPoints = useCallback(
    (ev: LayerEvaluation): string => {
      return DIMENSIONS.map((dim, i) => {
        const val = animated ? getScore(ev, dim.key) : 0;
        const pt = getPoint(i, val);
        return `${pt.x},${pt.y}`;
      }).join(" ");
    },
    [animated, getPoint]
  );

  return (
    <div className="glass-card rounded-2xl p-8">
      <h3 className="font-display text-lg text-foreground mb-2">
        Quality Comparison
      </h3>
      <p className="text-sm text-muted-foreground mb-8">
        6-dimension evaluation across all research layers
      </p>

      {/* Radar Chart */}
      <div className="flex flex-col lg:flex-row items-center gap-8">
        <div className="w-full max-w-sm mx-auto lg:mx-0">
          <svg viewBox="0 0 360 360" className="w-full h-auto">
            {/* Grid rings */}
            {[2, 4, 6, 8, 10].map((val) => (
              <polygon
                key={val}
                points={DIMENSIONS.map((_, i) => {
                  const pt = getPoint(i, val);
                  return `${pt.x},${pt.y}`;
                }).join(" ")}
                fill="none"
                stroke="currentColor"
                strokeWidth={val === 10 ? 1 : 0.5}
                className="text-foreground/10"
              />
            ))}

            {/* Axis lines */}
            {DIMENSIONS.map((_, i) => {
              const pt = getPoint(i, maxVal);
              return (
                <line
                  key={i}
                  x1={cx}
                  y1={cy}
                  x2={pt.x}
                  y2={pt.y}
                  stroke="currentColor"
                  strokeWidth={0.5}
                  className="text-foreground/10"
                />
              );
            })}

            {/* Layer polygons (draw L1 first so L3 is on top) */}
            {evaluations
              .slice()
              .sort((a, b) => a.layer - b.layer)
              .map((ev) => {
                const style = LAYER_STYLES[ev.layer] || LAYER_STYLES[0];
                const isHovered =
                  hoveredLayer === null || hoveredLayer === ev.layer;

                return (
                  <polygon
                    key={ev.layer}
                    points={getPolygonPoints(ev)}
                    fill={style.fill}
                    stroke={style.stroke}
                    strokeWidth={ev.layer === 2 ? 2.5 : ev.layer === 1 ? 2 : 1.5}
                    strokeDasharray={ev.layer === 0 ? "4,3" : "none"}
                    className="transition-all duration-1000 ease-out"
                    style={{
                      opacity: isHovered ? 1 : 0.15,
                      transition: "opacity 0.3s, points 1s ease-out",
                    }}
                    onMouseEnter={() => setHoveredLayer(ev.layer)}
                    onMouseLeave={() => setHoveredLayer(null)}
                  />
                );
              })}

            {/* Axis labels */}
            {DIMENSIONS.map((dim, i) => {
              const pt = getPoint(i, maxVal + 1.8);
              return (
                <text
                  key={dim.key}
                  x={pt.x}
                  y={pt.y}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  className="fill-muted-foreground text-[10px] font-mono"
                  style={{ fontSize: "10px" }}
                >
                  {dim.label.length > 12
                    ? dim.label.split(" ").map((word, wi) => (
                        <tspan
                          key={wi}
                          x={pt.x}
                          dy={wi === 0 ? 0 : 12}
                        >
                          {word}
                        </tspan>
                      ))
                    : dim.label}
                </text>
              );
            })}
          </svg>
        </div>

        {/* Legend + Scores */}
        <div className="flex-1 w-full space-y-4">
          {evaluations.map((ev) => {
            const style = LAYER_STYLES[ev.layer] || LAYER_STYLES[0];
            const avg = getAvgScore(ev);
            const isHovered =
              hoveredLayer === null || hoveredLayer === ev.layer;

            return (
              <div
                key={ev.layer}
                className={cn(
                  "glass-card rounded-xl p-4 transition-all duration-300 cursor-default",
                  isHovered ? "opacity-100" : "opacity-40"
                )}
                onMouseEnter={() => setHoveredLayer(ev.layer)}
                onMouseLeave={() => setHoveredLayer(null)}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2.5">
                    <span
                      className={cn(
                        "h-3 w-3 rounded-full",
                        style.dotClass
                      )}
                    />
                    <span className="font-mono text-xs font-medium text-foreground">
                      {LAYER_NAMES[ev.layer] || `Layer ${ev.layer}`}
                    </span>
                  </div>
                  <span className="font-display text-2xl tracking-tight">
                    {avg}<span className="text-sm text-muted-foreground font-mono">/10</span>
                  </span>
                </div>

                {/* Mini bars for each dimension */}
                <div className="grid grid-cols-3 gap-x-4 gap-y-2">
                  {DIMENSIONS.map((dim) => {
                    const val = getScore(ev, dim.key);
                    const pct = Math.round((val / 10) * 100);
                    return (
                      <div key={dim.key}>
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="text-[9px] font-mono text-muted-foreground truncate">
                            {dim.label}
                          </span>
                          <span className="text-[9px] font-mono font-semibold text-foreground ml-1">
                            {val}/10
                          </span>
                        </div>
                        <div className="h-1 rounded-full bg-foreground/5">
                          <div
                            className="h-full rounded-full transition-all duration-1000 ease-out"
                            style={{
                              width: animated
                                ? `${Math.max(pct, 5)}%`
                                : "0%",
                              background: style.stroke,
                              opacity: 0.7,
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
