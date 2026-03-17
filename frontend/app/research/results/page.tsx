"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Layers,
  FileText,
  Globe,
  ArrowLeft,
  Download,
  Brain,
} from "lucide-react";
import { ResearchLayout } from "@/components/ResearchLayout";
import { ReportCard } from "@/components/ReportCard";
import { LayerCard } from "@/components/LayerCard";
import { ScoreChart } from "@/components/ScoreChart";
import { AgentActivityPanel, LayerComparison } from "@/components/AgentActivityPanel";
import { Button } from "@/components/ui/button";
import { useResearchStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { LAYER_NAMES } from "@/lib/types";

export default function ResearchResultsPage() {
  const router = useRouter();
  const { report, reset } = useResearchStore();
  const [activeTab, setActiveTab] = useState<string>("summary");

  // Redirect if no report
  useEffect(() => {
    if (!report) {
      router.push("/research");
    }
  }, [report, router]);

  if (!report) return null;

  const totalWords = report.layers.reduce((s, l) => s + l.word_count, 0);
  const totalSources = report.layers.reduce((s, l) => s + l.source_count, 0);

  function handleDownloadJson() {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `research_${report.topic.slice(0, 40).replace(/\s+/g, "_")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleNewResearch() {
    reset();
    router.push("/research");
  }

  const tabs = [
    { id: "summary", label: "Step Workflow Visual" },
    ...report.layers.map((l) => ({
      id: `layer-${l.layer}`,
      label: LAYER_NAMES[l.layer] || `Layer ${l.layer}`,
    })),
    { id: "comparison", label: "Layer Comparison" },
  ];

  return (
    <ResearchLayout currentStep={3}>
      <div className="mx-auto max-w-5xl animate-fade-in-up">
        {/* Header */}
        <div className="mb-8 flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple/20">
                <Brain className="h-5 w-5 text-orange" />
              </div>
              <h2 className="text-2xl font-bold text-foreground">
                Research Results
              </h2>
            </div>
            <p className="text-sm text-warm-gray">{report.topic}</p>
          </div>
          <div className="flex gap-2">
            <Button
              onClick={handleDownloadJson}
              variant="outline"
              size="sm"
              className="gap-1.5"
            >
              <Download className="h-3.5 w-3.5" />
              JSON
            </Button>
            <Button
              onClick={handleNewResearch}
              size="sm"
              className="gap-1.5 gradient-brand text-white hover:opacity-90"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              New Research
            </Button>
          </div>
        </div>

        {/* Metric Cards */}
        <div className="mb-8 grid grid-cols-3 gap-4">
          <ReportCard
            icon={<Layers className="h-5 w-5" />}
            label="Layers"
            value={report.layers.length}
          />
          <ReportCard
            icon={<FileText className="h-5 w-5" />}
            label="Total Words"
            value={totalWords}
          />
          <ReportCard
            icon={<Globe className="h-5 w-5" />}
            label="Total Sources"
            value={totalSources}
          />
        </div>

        {/* Score Chart */}
        {report.evaluations.length > 0 && (
          <div className="mb-8">
            <ScoreChart evaluations={report.evaluations} />
          </div>
        )}

        {/* Tabs */}
        <div className="mb-6 flex gap-1 rounded-xl bg-surface-2 p-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex-1 rounded-lg px-3 py-2 text-xs font-medium transition-all",
                activeTab === tab.id
                  ? "bg-purple text-white shadow-md"
                  : "text-warm-gray hover:text-foreground hover:bg-surface-3"
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="mb-8">
          {activeTab === "summary" ? (
            <AgentActivityPanel
              layers={report.layers}
              evaluations={report.evaluations}
              summary={report.summary}
            />
          ) : activeTab === "comparison" ? (
            <LayerComparison
              layers={report.layers}
              evaluations={report.evaluations}
              layerComparisons={report.layer_comparisons}
            />
          ) : (
            (() => {
              const layerNum = parseInt(activeTab.replace("layer-", ""));
              const result = report.layers.find((l) => l.layer === layerNum);
              const evaluation = report.evaluations.find(
                (e) => e.layer === layerNum
              );
              if (!result) return null;
              return <LayerCard result={result} evaluation={evaluation} />;
            })()
          )}
        </div>

      </div>
    </ResearchLayout>
  );
}
