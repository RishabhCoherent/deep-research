"use client";

import { use, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
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
  BrainCircuit,
} from "lucide-react";
import { ResearchLayout } from "@/components/ResearchLayout";
import { ScoreChart } from "@/components/ScoreChart";
import { ResultsPopup } from "@/components/ResultsPopup";
import { ScrollPipeline } from "@/components/ScrollPipeline";
import { LayerPopupContent } from "@/components/LayerPopupContent";
import { ComparatorContent } from "@/components/ComparatorContent";
import { AnalystTraceOverlay } from "@/components/AnalystTrace";
import { DecompositionTree } from "@/components/DecompositionTree";
import Backend2Results from "@/components/backend2/Backend2Results";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { LAYER_NAMES, LAYER_DESCRIPTIONS } from "@/lib/types";
import type { ResearchTreeData } from "@/lib/types";
import { getResearchHistoryDetail, AGENTIC_API_BASE } from "@/lib/api";
import { extractAnalystTrace } from "@/lib/extract-agent-steps";
import type { ComparisonReport } from "@/lib/types";
import type { Backend2Report } from "@/lib/types-backend2";

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
  const searchParams = useSearchParams();
  const source = searchParams.get("source") === "agentic" ? "agentic" : "legacy";

  const [report, setReport] = useState<ComparisonReport | null>(null);
  const [b2Report, setB2Report] = useState<Backend2Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [openPopup, setOpenPopup] = useState<string | null>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    setIsVisible(true);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        if (source === "agentic") {
          const res = await fetch(`${AGENTIC_API_BASE}/api/research/history/${id}`);
          if (!res.ok) throw new Error(`status ${res.status}`);
          const data: Backend2Report = await res.json();
          if (!cancelled) setB2Report(data);
        } else {
          const data = await getResearchHistoryDetail(id);
          if (!cancelled) setReport(data.report);
        }
      } catch {
        if (!cancelled) router.push("/research/history");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [id, source, router]);

  if (loading) {
    return (
      <ResearchLayout>
        <div className="flex items-center justify-center py-32">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </ResearchLayout>
    );
  }

  // ── Backend2 (agentic) detail path ──────────────────────────
  if (source === "agentic") {
    if (!b2Report) return null;

    function handleDownloadJsonB2() {
      if (!b2Report) return;
      const blob = new Blob([JSON.stringify(b2Report, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const name = (b2Report.chosen_query || b2Report.original_query || "research")
        .slice(0, 40)
        .replace(/\s+/g, "_");
      a.download = `backend2_${name}.json`;
      a.click();
      URL.revokeObjectURL(url);
    }

    return (
      <ResearchLayout>
        <div
          className={`mb-8 flex items-center justify-end gap-3 transition-all duration-700 ${
            isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
          }`}
        >
          <Button
            onClick={handleDownloadJsonB2}
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
        <Backend2Results report={b2Report} />
      </ResearchLayout>
    );
  }

  // ── Legacy detail path ──────────────────────────────────────
  if (!report) return null;

  const totalSources = report.layers.reduce((s, l) => s + l.source_count, 0);
  const analystTrace = extractAnalystTrace(report);
  const hasAnalystTrace = analystTrace !== null;

  const researchTree: ResearchTreeData | null = (() => {
    const l3 = report.layers.find((l) => l.layer === 2);
    const tree = (l3?.metadata as Record<string, unknown>)?.research_tree as ResearchTreeData | undefined;
    return tree && tree.total_nodes > 0 ? tree : null;
  })();

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
      <div className="mb-10 flex items-start justify-between">
        <div
          className={`transition-all duration-700 ${
            isVisible
              ? "opacity-100 translate-y-0"
              : "opacity-0 translate-y-8"
          }`}
        >
          <span className="inline-flex items-center gap-3 text-xl lg:text-2xl font-mono uppercase tracking-wider text-muted-foreground mb-2">
            <span className="w-6 h-px bg-foreground/30" />
            Query
          </span>
          <p className="text-2xl lg:text-3xl font-display text-foreground/80 max-w-2xl mb-4 leading-snug">
            {report.topic}
          </p>
          <h1 className="text-xl lg:text-2xl font-display leading-[1.1] tracking-tight text-muted-foreground">
            Research Results
          </h1>
        </div>
        <div
          className={`flex gap-3 shrink-0 transition-all duration-700 delay-100 ${
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
        {/* Overview + Research Trace + Comparator cards */}
        <div className={cn("grid grid-cols-1 gap-4 mb-4", hasAnalystTrace ? "md:grid-cols-3" : "md:grid-cols-2")}>
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

          {hasAnalystTrace && (
            <button
              onClick={() => setOpenPopup("trace")}
              className={cn(
                "w-full glass-card-hover p-6 lg:p-8 text-left group cursor-pointer",
                "relative overflow-hidden"
              )}
            >
              <div
                className="absolute -top-10 -right-10 w-40 h-40 rounded-full blur-3xl pointer-events-none opacity-40"
                style={{ background: "rgba(99, 102, 241, 0.15)" }}
              />
              <div className="relative z-10 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-indigo-500/10">
                    <BrainCircuit className="h-6 w-6 text-indigo-400" />
                  </div>
                  <div>
                    <p className="text-[10px] font-mono text-indigo-400 mb-0.5">L3 CMI Expert</p>
                    <h3 className="text-lg font-display">Research Journey</h3>
                    <p className="text-sm text-muted-foreground">
                      Full reasoning trail &middot; How the agent planned, searched, and formed judgments
                    </p>
                  </div>
                </div>
                <ArrowRight className="h-5 w-5 text-muted-foreground transition-transform group-hover:translate-x-1" />
              </div>
            </button>
          )}

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


      {/* ── Decomposition Tree ────────────────────────────── */}
      {researchTree && researchTree.total_nodes > 1 && (
        <div className="mb-12">
          <div className="mb-4">
            <span className="inline-flex items-center gap-3 text-xs font-mono uppercase tracking-wider text-muted-foreground">
              <span className="w-6 h-px bg-foreground/30" />
              Research Decomposition
            </span>
            <p className="text-sm text-muted-foreground mt-1">
              Each question was broken into smaller parts and researched individually. Click any node to inspect.
            </p>
          </div>
          <DecompositionTree treeData={researchTree} className="h-100" />
        </div>
      )}

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

      {/* Research Trace — full-screen narrative overlay */}
      {analystTrace && (
        <AnalystTraceOverlay
          isOpen={openPopup === "trace"}
          onClose={() => setOpenPopup(null)}
          trace={analystTrace}
        />
      )}

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
            <LayerPopupContent result={layer} evaluation={evaluation} report={report} />
          </ResultsPopup>
        );
      })}
    </ResearchLayout>
  );
}
