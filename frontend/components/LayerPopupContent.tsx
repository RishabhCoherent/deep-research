"use client";

import { useEffect, useState } from "react";
import { FileText, Globe, Clock, TrendingUp } from "lucide-react";
import { ScoreChart } from "@/components/ScoreChart";
import { MarkdownReport } from "@/components/MarkdownReport";
import type { LayerResult, LayerEvaluation } from "@/lib/types";

interface LayerPopupContentProps {
  result: LayerResult;
  evaluation?: LayerEvaluation;
}

function AnimatedCounter({ value, decimals = 0 }: { value: number; decimals?: number }) {
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

  return <>{decimals > 0 ? display.toFixed(decimals) : Math.round(display).toLocaleString()}</>;
}

export function LayerPopupContent({ result, evaluation }: LayerPopupContentProps) {
  const avgScore = evaluation
    ? (() => {
        const scores = evaluation.scores || {};
        const vals = Object.values(scores)
          .map((s) => (typeof s === "object" && s ? s.score : 0))
          .filter((v) => v > 0);
        return vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
      })()
    : 0;

  const metrics = [
    { icon: FileText, label: "Words", value: result.word_count, decimals: 0 },
    { icon: Globe, label: "Sources", value: result.source_count, decimals: 0 },
    { icon: Clock, label: "Time (s)", value: result.elapsed_seconds, decimals: 1 },
    { icon: TrendingUp, label: "Avg Score", value: avgScore, decimals: 1 },
  ];

  return (
    <div className="space-y-8">
      {/* Metrics row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {metrics.map((m) => (
          <div key={m.label} className="glass-card p-5 text-center">
            <m.icon className="h-4 w-4 mx-auto mb-2 text-muted-foreground" />
            <div className="text-2xl font-display tracking-tight">
              <AnimatedCounter value={m.value} decimals={m.decimals} />
            </div>
            <div className="text-[10px] font-mono text-muted-foreground mt-1 uppercase">
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
