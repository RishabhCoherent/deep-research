"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Clock, ArrowLeft } from "lucide-react";
import { WizardLayout } from "@/components/WizardLayout";
import { ProgressStream } from "@/components/ProgressStream";
import { Button } from "@/components/ui/button";
import { useWizardStore } from "@/lib/store";
import { useGeneration } from "@/hooks/useGeneration";

export default function GeneratePage() {
  const router = useRouter();
  const jobId = useWizardStore((s) => s.jobId);
  const messages = useWizardStore((s) => s.progressMessages);
  const isGenerating = useWizardStore((s) => s.isGenerating);
  const downloadReady = useWizardStore((s) => s.downloadReady);
  const sectionPlans = useWizardStore((s) => s.sectionPlans);

  useGeneration(jobId);

  // Elapsed time
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!isGenerating) return;
    const start = Date.now();
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(id);
  }, [isGenerating]);

  // Navigate to download when ready
  useEffect(() => {
    if (downloadReady) {
      router.push("/download");
    }
  }, [downloadReady, router]);

  // Guard
  if (!jobId) {
    return (
      <WizardLayout currentStep={3}>
        <div className="flex flex-col items-center justify-center py-20">
          <p className="text-warm-gray">No generation job found.</p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => router.push("/extract")}
          >
            <ArrowLeft className="mr-2 h-4 w-4" /> Back to Extract
          </Button>
        </div>
      </WizardLayout>
    );
  }

  // Compute progress percentage (mirrors app.py logic)
  const sectionCount = sectionPlans.length || 1;
  const progressMsgs = messages.filter((m) => m.type === "progress");
  const contentDone = progressMsgs.filter((m) =>
    m.message.includes("Generating content:")
  ).length;
  const buildDone = progressMsgs.filter((m) =>
    m.message.includes("Building section")
  ).length;
  const pct = Math.min(
    Math.round(((contentDone * 0.7 + buildDone * 0.3) / sectionCount) * 100),
    99
  );

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  return (
    <WizardLayout currentStep={3}>
      <div className="mx-auto max-w-3xl animate-fade-in-up">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-foreground">
              Generating Report
            </h2>
            <p className="mt-2 text-sm text-warm-gray">
              Your report is being generated. This may take several minutes.
            </p>
          </div>
          <div className="flex items-center gap-2 rounded-lg bg-surface-2 px-3 py-2">
            <Clock className="h-4 w-4 text-orange" />
            <span className="font-mono text-sm text-foreground">
              {formatTime(elapsed)}
            </span>
          </div>
        </div>

        <ProgressStream messages={messages} progress={pct} />

        {/* Check for failed generation */}
        {!isGenerating && !downloadReady && messages.length > 0 && (
          <div className="mt-6">
            <div className="rounded-lg border border-error/30 bg-error/10 px-4 py-3 text-sm text-error">
              Generation failed. Check the log above for details.
            </div>
            <Button
              variant="outline"
              className="mt-4 gap-2"
              onClick={() => router.push("/extract")}
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Configuration
            </Button>
          </div>
        )}
      </div>
    </WizardLayout>
  );
}
