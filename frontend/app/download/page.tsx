"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  FileText,
  HardDrive,
  Layers,
  BookOpen,
  Download,
  RotateCcw,
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  Info,
  AlertTriangle,
  Activity,
} from "lucide-react";
import confetti from "canvas-confetti";
import { WizardLayout } from "@/components/WizardLayout";
import { ReportCard } from "@/components/ReportCard";
import { Button } from "@/components/ui/button";
import { useWizardStore } from "@/lib/store";
import { getDownloadUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function DownloadPage() {
  const router = useRouter();
  const reportTitle = useWizardStore((s) => s.reportTitle);
  const outputSize = useWizardStore((s) => s.outputSize);
  const sectionPlans = useWizardStore((s) => s.sectionPlans);
  const citationCount = useWizardStore((s) => s.citationCount);
  const progressMessages = useWizardStore((s) => s.progressMessages);
  const jobId = useWizardStore((s) => s.jobId);
  const downloadReady = useWizardStore((s) => s.downloadReady);
  const reset = useWizardStore((s) => s.reset);

  const [logOpen, setLogOpen] = useState(false);
  const confettiLaunched = useRef(false);

  // Launch confetti on mount
  useEffect(() => {
    if (!confettiLaunched.current && downloadReady) {
      confettiLaunched.current = true;
      confetti({
        particleCount: 120,
        spread: 80,
        origin: { y: 0.6 },
        colors: ["#7C3AED", "#F97316", "#E11D48", "#34D399"],
      });
    }
  }, [downloadReady]);

  // Guard
  if (!downloadReady || !jobId) {
    return (
      <WizardLayout currentStep={4}>
        <div className="flex flex-col items-center justify-center py-20">
          <p className="text-warm-gray">No report available.</p>
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

  const sizeMB = (outputSize / (1024 * 1024)).toFixed(1);

  function handleDownload() {
    const url = getDownloadUrl(jobId!);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${reportTitle.replace(/\s+/g, "_").slice(0, 60)}.docx`;
    a.click();
  }

  function handleReset() {
    reset();
    router.push("/upload");
  }

  return (
    <WizardLayout currentStep={4}>
      <div className="mx-auto max-w-4xl animate-fade-in-up">
        <div className="mb-8 text-center">
          <div className="mb-4 inline-flex h-16 w-16 items-center justify-center rounded-2xl gradient-brand glow-lg">
            <FileText className="h-8 w-8 text-white" />
          </div>
          <h2 className="text-2xl font-bold text-foreground">Report Ready!</h2>
          <p className="mt-2 text-sm text-warm-gray">
            Your market research report has been generated successfully.
          </p>
        </div>

        {/* Metric cards */}
        <div className="mb-8 grid grid-cols-4 gap-4">
          <ReportCard
            icon={<FileText className="h-5 w-5" />}
            label="Report"
            value={reportTitle}
            isText
          />
          <ReportCard
            icon={<HardDrive className="h-5 w-5" />}
            label="File Size"
            value={parseFloat(sizeMB)}
            suffix="MB"
          />
          <ReportCard
            icon={<Layers className="h-5 w-5" />}
            label="Sections"
            value={sectionPlans.length}
          />
          <ReportCard
            icon={<BookOpen className="h-5 w-5" />}
            label="Citations"
            value={citationCount}
          />
        </div>

        {/* Download button */}
        <Button
          onClick={handleDownload}
          className="w-full gradient-brand text-white text-base py-6 hover:opacity-90 glow-md gap-3"
        >
          <Download className="h-5 w-5" />
          Download Report (.docx)
        </Button>

        {/* Generation log (collapsible) */}
        {progressMessages.length > 0 && (
          <div className="mt-8 glass-card overflow-hidden">
            <button
              onClick={() => setLogOpen(!logOpen)}
              className="flex w-full items-center justify-between px-5 py-3 text-sm font-medium text-warm-gray hover:text-foreground transition-colors"
            >
              <span>Generation Log ({progressMessages.length} entries)</span>
              {logOpen ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </button>
            {logOpen && (
              <div className="max-h-60 overflow-y-auto border-t border-surface-3 px-5 py-3 font-mono text-xs leading-relaxed">
                {progressMessages.map((msg, i) => {
                  if (msg.type === "done") return null;
                  const iconMap = {
                    status: <Activity className="h-3 w-3 text-orange" />,
                    info: <Info className="h-3 w-3 text-orange-light" />,
                    progress: (
                      <ChevronRight className="h-3 w-3 text-warm-gray" />
                    ),
                    warning: (
                      <AlertTriangle className="h-3 w-3 text-warning" />
                    ),
                    done: <Activity className="h-3 w-3 text-success" />,
                  };
                  const colors = {
                    status: "text-foreground font-semibold",
                    info: "text-orange-light",
                    progress: "text-warm-gray-light",
                    warning: "text-warning",
                    done: "text-success",
                  };
                  return (
                    <div key={i} className="flex items-start gap-2 py-0.5">
                      <span className="shrink-0 mt-0.5">
                        {iconMap[msg.type]}
                      </span>
                      <span className={cn(colors[msg.type])}>
                        {msg.message}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* New report */}
        <div className="mt-6 text-center">
          <Button variant="outline" onClick={handleReset} className="gap-2">
            <RotateCcw className="h-4 w-4" />
            Generate Another Report
          </Button>
        </div>
      </div>
    </WizardLayout>
  );
}
