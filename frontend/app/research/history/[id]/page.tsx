"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Layers,
  Globe,
  ArrowLeft,
  ArrowRight,
  Download,
  Loader2,
  Eye,
  Cpu,
  Search,
  Target,
  GitCompareArrows,
  TrendingDown,
  Zap,
  Crosshair,
} from "lucide-react";
import { ResearchLayout } from "@/components/ResearchLayout";
import { ScoreChart } from "@/components/ScoreChart";
import { ResultsPopup } from "@/components/ResultsPopup";
import { ScrollPipeline } from "@/components/ScrollPipeline";
import { LayerPopupContent } from "@/components/LayerPopupContent";
import { ComparatorContent } from "@/components/ComparatorContent";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { LAYER_NAMES, LAYER_DESCRIPTIONS } from "@/lib/types";
import { getResearchHistoryDetail } from "@/lib/api";
import type { ComparisonReport } from "@/lib/types";

function AnimatedCounter({ value }: { value: number }) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    const duration = 1500;
    const steps = 40;
    const stepTime = duration / steps;
    let step = 0;

    const timer = setInterval(() => {
      step++;
      const progress = 1 - Math.pow(1 - step / steps, 3);
      setDisplay(Math.round(value * progress));
      if (step >= steps) {
        setDisplay(value);
        clearInterval(timer);
      }
    }, stepTime);

    return () => clearInterval(timer);
  }, [value]);

  return <>{display.toLocaleString()}</>;
}

const CARD_CONFIG: Record<
  number,
  { icon: typeof Cpu; accent: string; border: string; orb: string }
> = {
  0: {
    icon: Cpu,
    accent: "rgba(0, 0, 0, 0.06)",
    border: "border-foreground/10 hover:border-foreground/20",
    orb: "rgba(0, 0, 0, 0.08)",
  },
  1: {
    icon: Search,
    accent: "rgba(124, 58, 237, 0.08)",
    border: "border-purple/10 hover:border-purple/25",
    orb: "rgba(124, 58, 237, 0.12)",
  },
  2: {
    icon: Target,
    accent: "rgba(0, 0, 0, 0.06)",
    border: "border-foreground/10 hover:border-foreground/20",
    orb: "rgba(0, 0, 0, 0.10)",
  },
};

export default function HistoryDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const [report, setReport] = useState<ComparisonReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [openPopup, setOpenPopup] = useState<string | null>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    setIsVisible(true);
  }, []);

  useEffect(() => {
    getResearchHistoryDetail(id)
      .then((data) => setReport(data.report))
      .catch(() => router.push("/research/history"))
      .finally(() => setLoading(false));
  }, [id, router]);

  if (loading) {
    return (
      <ResearchLayout>
        <div className="flex items-center justify-center py-32">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </ResearchLayout>
    );
  }

  if (!report) return null;

  const totalSources = report.layers.reduce((s, l) => s + l.source_count, 0);

  function handleDownloadJson() {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `research_${report.topic
      .slice(0, 40)
      .replace(/\s+/g, "_")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const metrics = [
    {
      icon: <Layers className="h-5 w-5" />,
      label: "Layers completed",
      value: report.layers.length,
    },
    {
      icon: <TrendingDown className="h-5 w-5" />,
      label: "Hallucination reduction",
      value: report.hallucination_reduction ?? 0,
      suffix: "%",
    },
    {
      icon: <Zap className="h-5 w-5" />,
      label: "Outcome efficiency",
      value: report.outcome_efficiency ?? 0,
      suffix: "%",
    },
    {
      icon: <Crosshair className="h-5 w-5" />,
      label: "Relevancy",
      value: report.relevancy ?? 0,
      suffix: "%",
    },
    {
      icon: <Globe className="h-5 w-5" />,
      label: "Total sources",
      value: totalSources,
    },
  ];

  return (
    <ResearchLayout>
      {/* ── Header ──────────────────────────────────────── */}
      <div className="mb-12 flex items-start justify-between">
        <div
          className={`transition-all duration-700 ${
            isVisible
              ? "opacity-100 translate-y-0"
              : "opacity-0 translate-y-8"
          }`}
        >
          <span className="inline-flex items-center gap-3 text-sm font-mono text-muted-foreground mb-4">
            <span className="w-8 h-px bg-foreground/30" />
            Research History
          </span>
          <h1 className="text-3xl lg:text-4xl font-display leading-[1.1] tracking-tight">
            Research Results
          </h1>
          <p className="mt-3 text-lg text-muted-foreground max-w-xl">
            {report.topic}
          </p>
        </div>
        <div
          className={`flex gap-3 transition-all duration-700 delay-100 ${
            isVisible
              ? "opacity-100 translate-y-0"
              : "opacity-0 translate-y-4"
          }`}
        >
          <Button
            onClick={handleDownloadJson}
            variant="outline"
            size="sm"
            className="gap-1.5 rounded-full border-foreground/20 hover:bg-foreground/5"
          >
            <Download className="h-3.5 w-3.5" />
            JSON
          </Button>
          <Button
            onClick={() => router.push("/research/history")}
            size="sm"
            className="gap-1.5 bg-foreground hover:bg-foreground/90 text-background rounded-full group"
          >
            <ArrowLeft className="h-3.5 w-3.5 transition-transform group-hover:-translate-x-1" />
            Back to History
          </Button>
        </div>
      </div>

      {/* ── Metrics Row ─────────────────────────────────── */}
      <div
        className={`mb-12 transition-all duration-700 delay-150 ${
          isVisible
            ? "opacity-100 translate-y-0"
            : "opacity-0 translate-y-8"
        }`}
      >
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-px bg-foreground/10 rounded-2xl overflow-hidden">
          {metrics.map((m, i) => (
            <div
              key={m.label}
              className="bg-background p-6 lg:p-8 text-center animate-fade-in-up"
              style={{ animationDelay: `${i * 100}ms` }}
            >
              <div className="flex justify-center mb-3 text-muted-foreground">
                {m.icon}
              </div>
              <div className="text-3xl lg:text-4xl font-display tracking-tight">
                <AnimatedCounter value={m.value} />
                {"suffix" in m && m.suffix && <span className="text-xl lg:text-2xl">{m.suffix}</span>}
              </div>
              <div className="text-xs lg:text-sm text-muted-foreground mt-2">
                {m.label}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Score Chart ─────────────────────────────────── */}
      {report.evaluations.length > 0 && (
        <div
          className={`mb-12 transition-all duration-700 delay-200 ${
            isVisible
              ? "opacity-100 translate-y-0"
              : "opacity-0 translate-y-8"
          }`}
        >
          <ScoreChart evaluations={report.evaluations} />
        </div>
      )}

      {/* ── Card Grid (replaces pill tabs) ───────────────── */}
      <div
        className={`mb-12 transition-all duration-700 delay-250 ${
          isVisible
            ? "opacity-100 translate-y-0"
            : "opacity-0 translate-y-4"
        }`}
      >
        {/* Overview + Comparator cards — 2 columns */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <button
            onClick={() => setOpenPopup("overview")}
            className={cn(
              "w-full glass-card-hover p-6 lg:p-8 text-left group cursor-pointer",
              "relative overflow-hidden"
            )}
          >
            <div
              className="absolute -top-10 -right-10 w-40 h-40 rounded-full blur-3xl pointer-events-none opacity-40"
              style={{ background: "rgba(124, 58, 237, 0.15)" }}
            />
            <div className="relative z-10 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-purple/10">
                  <Eye className="h-6 w-6 text-purple" />
                </div>
                <div>
                  <h3 className="text-lg font-display">Overview</h3>
                  <p className="text-sm text-muted-foreground">
                    Claim transformation pipeline &middot; See how research transforms raw claims into substantiated insights
                  </p>
                </div>
              </div>
              <ArrowRight className="h-5 w-5 text-muted-foreground transition-transform group-hover:translate-x-1" />
            </div>
          </button>

          <button
            onClick={() => setOpenPopup("comparator")}
            className={cn(
              "w-full glass-card-hover p-6 lg:p-8 text-left group cursor-pointer",
              "relative overflow-hidden"
            )}
          >
            <div
              className="absolute -top-10 -right-10 w-40 h-40 rounded-full blur-3xl pointer-events-none opacity-40"
              style={{ background: "rgba(5, 150, 105, 0.12)" }}
            />
            <div className="relative z-10 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-emerald-500/10">
                  <GitCompareArrows className="h-6 w-6 text-emerald-600" />
                </div>
                <div>
                  <h3 className="text-lg font-display">Comparator</h3>
                  <p className="text-sm text-muted-foreground">
                    Compare layers side by side &middot; Scores, metrics, and full reports across all strategies
                  </p>
                </div>
              </div>
              <ArrowRight className="h-5 w-5 text-muted-foreground transition-transform group-hover:translate-x-1" />
            </div>
          </button>
        </div>

        {/* Layer cards — 3 columns */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {report.layers.map((layer) => {
            const config = CARD_CONFIG[layer.layer] || CARD_CONFIG[0];
            const LayerIcon = config.icon;
            const evaluation = report.evaluations.find(
              (e) => e.layer === layer.layer
            );
            const avgScore = evaluation
              ? (() => {
                  const scores = evaluation.scores || {};
                  const vals = Object.values(scores)
                    .map((s) => (typeof s === "object" && s ? s.score : 0))
                    .filter((v) => v > 0);
                  return vals.length > 0
                    ? (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1)
                    : "—";
                })()
              : "—";

            return (
              <button
                key={layer.layer}
                onClick={() => setOpenPopup(`layer-${layer.layer}`)}
                className={cn(
                  "glass-card-hover p-6 text-left group cursor-pointer",
                  "relative overflow-hidden border",
                  config.border
                )}
              >
                <div
                  className="absolute -bottom-6 -right-6 w-24 h-24 rounded-full blur-2xl pointer-events-none opacity-50"
                  style={{ background: config.orb }}
                />

                <div className="relative z-10">
                  <div className="flex items-center justify-between mb-4">
                    <div
                      className="w-10 h-10 rounded-xl flex items-center justify-center"
                      style={{ background: config.accent }}
                    >
                      <LayerIcon className="h-5 w-5" />
                    </div>
                    <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-all group-hover:translate-x-1" />
                  </div>

                  <h3 className="font-display text-base mb-1">
                    {LAYER_NAMES[layer.layer] || `Layer ${layer.layer}`}
                  </h3>
                  <p className="text-xs text-muted-foreground mb-4 line-clamp-2">
                    {LAYER_DESCRIPTIONS[layer.layer] || ""}
                  </p>

                  <div className="flex items-center gap-4 text-xs font-mono text-muted-foreground">
                    <span>{layer.word_count.toLocaleString()} words</span>
                    <span className="w-px h-3 bg-foreground/10" />
                    <span>{layer.source_count} sources</span>
                    <span className="w-px h-3 bg-foreground/10" />
                    <span>{avgScore}/10</span>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Popups ───────────────────────────────────────── */}

      <ResultsPopup
        isOpen={openPopup === "overview"}
        onClose={() => setOpenPopup(null)}
        title="Overview"
        subtitle="Claim Transformation Pipeline"
        accentColor="rgba(124, 58, 237, 0.15)"
      >
        <ScrollPipeline report={report} />
      </ResultsPopup>

      {/* Comparator popup */}
      <ResultsPopup
        isOpen={openPopup === "comparator"}
        onClose={() => setOpenPopup(null)}
        title="Comparator"
        subtitle="Side-by-side layer comparison"
        accentColor="rgba(5, 150, 105, 0.15)"
      >
        <ComparatorContent report={report} />
      </ResultsPopup>

      {/* Layer popups */}
      {report.layers.map((layer) => {
        const evaluation = report.evaluations.find(
          (e) => e.layer === layer.layer
        );
        return (
          <ResultsPopup
            key={layer.layer}
            isOpen={openPopup === `layer-${layer.layer}`}
            onClose={() => setOpenPopup(null)}
            title={LAYER_NAMES[layer.layer] || `Layer ${layer.layer}`}
            subtitle={LAYER_DESCRIPTIONS[layer.layer]}
            accentColor={
              layer.layer === 1
                ? "rgba(124, 58, 237, 0.15)"
                : "rgba(0, 0, 0, 0.08)"
            }
          >
            <LayerPopupContent result={layer} evaluation={evaluation} />
          </ResultsPopup>
        );
      })}
    </ResearchLayout>
  );
}
