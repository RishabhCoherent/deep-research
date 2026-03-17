"use client";

import { useRouter } from "next/navigation";
import {
  FileText,
  Layers,
  BarChart3,
  Download,
  ArrowLeft,
  ArrowRight,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import { useState } from "react";
import { WizardLayout } from "@/components/WizardLayout";
import { SectionPlanList } from "@/components/SectionPlanList";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useWizardStore } from "@/lib/store";
import { startGeneration } from "@/lib/api";

export default function ExtractPage() {
  const router = useRouter();
  const extractedData = useWizardStore((s) => s.extractedData);
  const summary = useWizardStore((s) => s.extractionSummary);
  const skipContent = useWizardStore((s) => s.skipContent);
  const topicOverride = useWizardStore((s) => s.topicOverride);
  const setGeneration = useWizardStore((s) => s.startGeneration);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Guard: redirect if no data
  if (!extractedData || !summary) {
    return (
      <WizardLayout currentStep={2}>
        <div className="flex flex-col items-center justify-center py-20">
          <p className="text-warm-gray">No extraction data found.</p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => router.push("/upload")}
          >
            <ArrowLeft className="mr-2 h-4 w-4" /> Back to Upload
          </Button>
        </div>
      </WizardLayout>
    );
  }

  async function handleGenerate() {
    if (!extractedData) return;
    setLoading(true);
    setError(null);
    try {
      const res = await startGeneration(extractedData, skipContent, topicOverride);
      setGeneration(res.job_id);
      router.push("/generate");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start generation");
    } finally {
      setLoading(false);
    }
  }

  function handleDownloadJson() {
    const json = JSON.stringify(extractedData, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(summary?.report_title ?? "data").replace(/\s+/g, "_").slice(0, 40)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const mode = skipContent
    ? "Charts + Tables only"
    : "Full report with LLM content";
  const topic = topicOverride || summary?.report_title || "";

  return (
    <WizardLayout currentStep={2}>
      <div className="mx-auto max-w-4xl animate-fade-in-up">
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-foreground">
            Extraction Complete
          </h2>
          <p className="mt-2 text-sm text-warm-gray">
            Review the extracted data before generating your report.
          </p>
        </div>

        {/* Metric cards */}
        <div className="mb-6 grid grid-cols-3 gap-4">
          <MetricCard
            icon={<FileText className="h-5 w-5" />}
            label="Report Title"
            value={summary.report_title}
            isText
          />
          <MetricCard
            icon={<Layers className="h-5 w-5" />}
            label="TOC Sections"
            value={summary.section_count}
          />
          <MetricCard
            icon={<BarChart3 className="h-5 w-5" />}
            label="ME Data Sheets"
            value={summary.sheet_count}
          />
        </div>

        {/* Section plans */}
        <div className="glass-card mb-6 p-5">
          <h3 className="mb-4 text-sm font-semibold text-foreground">
            Section Plan
          </h3>
          <SectionPlanList plans={summary.plans} />
        </div>

        {/* Data sheets */}
        {summary.sheets.length > 0 && (
          <div className="glass-card mb-6 p-5">
            <h3 className="mb-3 text-sm font-semibold text-foreground">
              ME Data Sheets
            </h3>
            <div className="flex flex-wrap gap-2">
              {summary.sheets.map((sheet, i) => (
                <span
                  key={i}
                  className="rounded-md bg-surface-3 px-3 py-1 text-xs text-warm-gray"
                >
                  {sheet}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Download JSON */}
        <div className="mb-6">
          <Button
            variant="outline"
            size="sm"
            onClick={handleDownloadJson}
            className="gap-2"
          >
            <Download className="h-3.5 w-3.5" />
            Download Extracted JSON
          </Button>
        </div>

        {/* Config summary */}
        <div className="glass-card mb-6 p-5">
          <div className="flex items-center gap-6 text-sm">
            <div>
              <span className="text-warm-gray">Mode:</span>{" "}
              <span className="font-medium text-foreground">{mode}</span>
            </div>
            <div>
              <span className="text-warm-gray">Topic:</span>{" "}
              <span className="font-medium text-foreground">{topic}</span>
            </div>
          </div>
          {!skipContent && (
            <div className="mt-3 flex items-center gap-2 rounded-lg border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-warning">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              Full report generation takes 15-30 minutes (LLM + web research).
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 rounded-lg border border-error/30 bg-error/10 px-4 py-3 text-sm text-error">
            {error}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-4">
          <Button
            variant="outline"
            onClick={() => router.push("/upload")}
            className="gap-2"
          >
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
          <Button
            onClick={handleGenerate}
            disabled={loading}
            className="flex-1 gradient-brand text-white hover:opacity-90 gap-2"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ArrowRight className="h-4 w-4" />
            )}
            Generate Report
          </Button>
        </div>
      </div>
    </WizardLayout>
  );
}

function MetricCard({
  icon,
  label,
  value,
  isText,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  isText?: boolean;
}) {
  return (
    <Card className="glass-card-hover border-surface-3">
      <CardContent className="flex items-start gap-3 p-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-purple/20 text-orange">
          {icon}
        </div>
        <div className="min-w-0">
          <p className="text-xs text-warm-gray">{label}</p>
          {isText ? (
            <p className="mt-0.5 text-sm font-semibold text-foreground truncate">
              {value}
            </p>
          ) : (
            <p className="mt-0.5 text-2xl font-bold text-gradient">{value}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
