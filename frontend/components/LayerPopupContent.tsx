"use client";

import { useEffect, useState } from "react";
import {
  Layers,
  TrendingDown,
  Zap,
  Crosshair,
  Globe,
  TrendingUp,
} from "lucide-react";
import { ScoreChart } from "@/components/ScoreChart";
import { MarkdownReport } from "@/components/MarkdownReport";
import type { LayerResult, LayerEvaluation, ComparisonReport } from "@/lib/types";

interface LayerPopupContentProps {
  result: LayerResult;
  evaluation?: LayerEvaluation;
  report?: ComparisonReport;
}

const DIMENSIONS = [
  { key: "factual_density", label: "Factual Density" },
  { key: "source_grounding", label: "Source Grounding" },
  { key: "analytical_depth", label: "Analytical Depth" },
  { key: "specificity", label: "Specificity" },
  { key: "insight_quality", label: "Insight Quality" },
  { key: "completeness", label: "Completeness" },
];

function getScore(evaluation: LayerEvaluation, key: string): number {
  const entry = evaluation.scores?.[key];
  if (typeof entry === "object" && entry !== null) {
    return (entry as { score: number }).score ?? 0;
  }
  return 0;
}

function AnimatedCounter({ value, decimals = 0, suffix = "" }: { value: number; decimals?: number; suffix?: string }) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    const duration = 1200;
    const steps = 30;
    const stepTime = duration / steps;
    let step = 0;

    const timer = setInterval(() => {
      step++;
      const progress = 1 - Math.pow(1 - step / steps, 3);
      setDisplay(value * progress);
      if (step >= steps) {
        setDisplay(value);
        clearInterval(timer);
      }
    }, stepTime);

    return () => clearInterval(timer);
  }, [value]);

  return <>{decimals > 0 ? display.toFixed(decimals) : Math.round(display).toLocaleString()}{suffix}</>;
}

export function LayerPopupContent({ result, evaluation, report }: LayerPopupContentProps) {
  const avgScore = evaluation
    ? (() => {
        const vals = DIMENSIONS.map((d) => getScore(evaluation, d.key)).filter((v) => v > 0);
        return vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
      })()
    : 0;

  const totalSources = report
    ? report.layers.reduce((s, l) => s + l.source_count, 0)
    : result.source_count;

  const metrics = [
    { icon: Layers, label: "Layers completed", value: report?.layers.length ?? 1, suffix: "" },
    { icon: TrendingDown, label: "Hallucination reduction", value: report?.hallucination_reduction ?? 0, suffix: "%" },
    { icon: Zap, label: "Outcome efficiency", value: report?.outcome_efficiency ?? 0, suffix: "%" },
    { icon: Crosshair, label: "Relevancy", value: report?.relevancy ?? 0, suffix: "%" },
    { icon: Globe, label: "Total sources", value: totalSources, suffix: "" },
    { icon: TrendingUp, label: "Avg Score", value: avgScore, decimals: 1, suffix: "" },
  ];

  return (
    <div className="space-y-8">
      {/* Metrics row */}
      <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
        {metrics.map((m) => (
          <div key={m.label} className="glass-card p-4 text-center">
            <m.icon className="h-4 w-4 mx-auto mb-2 text-muted-foreground" />
            <div className="text-2xl font-display tracking-tight">
              <AnimatedCounter
                value={m.value}
                decimals={"decimals" in m ? (m.decimals as number) : 0}
                suffix={m.suffix}
              />
            </div>
            <div className="text-[9px] font-mono text-muted-foreground mt-1 uppercase leading-tight">
              {m.label}
            </div>
          </div>
        ))}
      </div>

      {/* Quality radar (single-layer) */}
      {evaluation && (
        <div>
          <ScoreChart evaluations={[evaluation]} />
        </div>
      )}

      {/* Full report */}
      {result.content && (
        <div>
          <h3 className="text-sm font-mono uppercase tracking-wider text-muted-foreground mb-4">
            Full Report
          </h3>
          <MarkdownReport content={result.content} />
        </div>
      )}
    </div>
  );
}