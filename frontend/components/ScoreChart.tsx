"use client";

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

const LAYER_COLORS: Record<number, string> = {
  0: "bg-warm-gray",
  1: "bg-purple",
  2: "bg-coral",
};

const LAYER_TEXT_COLORS: Record<number, string> = {
  0: "text-warm-gray",
  1: "text-purple-light",
  2: "text-coral",
};

export function ScoreChart({ evaluations }: ScoreChartProps) {
  const maxVal = 10;

  return (
    <div className="glass-card p-5">
      <h3 className="mb-5 text-sm font-semibold text-foreground">
        Quality Comparison
      </h3>

      {/* Legend */}
      <div className="mb-5 flex flex-wrap gap-3">
        {evaluations.map((ev) => (
          <div key={ev.layer} className="flex items-center gap-1.5">
            <div
              className={cn(
                "h-2.5 w-2.5 rounded-full",
                LAYER_COLORS[ev.layer] || "bg-warm-gray"
              )}
            />
            <span className="text-[11px] text-warm-gray">
              {LAYER_NAMES[ev.layer] || `L${ev.layer}`}
            </span>
          </div>
        ))}
      </div>

      {/* Bar groups */}
      <div className="space-y-5">
        {DIMENSIONS.map((dim) => (
          <div key={dim.key}>
            <p className="mb-2 text-xs font-medium text-warm-gray-light">
              {dim.label}
            </p>
            <div className="space-y-1.5">
              {evaluations.map((ev) => {
                const scoreEntry = ev.scores?.[dim.key];
                const val =
                  typeof scoreEntry === "object" && scoreEntry !== null
                    ? (scoreEntry as { score: number }).score
                    : 0;
                const pct = Math.round((val / maxVal) * 100);

                return (
                  <div key={ev.layer} className="flex items-center gap-2">
                    <span
                      className={cn(
                        "w-6 text-right text-[10px] font-medium",
                        LAYER_TEXT_COLORS[ev.layer] || "text-warm-gray"
                      )}
                    >
                      L{ev.layer}
                    </span>
                    <div className="relative h-5 flex-1 overflow-hidden rounded-full bg-surface-3/50">
                      <div
                        className={cn(
                          "h-full rounded-full transition-all duration-700 ease-out",
                          LAYER_COLORS[ev.layer] || "bg-warm-gray"
                        )}
                        style={{ width: `${Math.max(pct, 3)}%` }}
                      />
                    </div>
                    <span className="w-10 text-right text-[11px] font-bold text-foreground">
                      {val}/10
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
