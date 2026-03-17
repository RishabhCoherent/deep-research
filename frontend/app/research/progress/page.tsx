"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Clock,
  CheckCircle2,
  Circle,
  Loader2,
  Activity,
  ChevronRight,
} from "lucide-react";
import { ResearchLayout } from "@/components/ResearchLayout";
import { useResearchStore } from "@/lib/store";
import { useResearch } from "@/hooks/useResearch";
import { cn } from "@/lib/utils";
import { LAYER_NAMES, LAYER_DESCRIPTIONS } from "@/lib/types";

export default function ResearchProgressPage() {
  const router = useRouter();
  const {
    jobId,
    isResearching,
    currentLayer,
    completedLayers,
    progressEvents,
    report,
    error,
    maxLayer,
  } = useResearchStore();

  useResearch(jobId);

  // Elapsed timer
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!isResearching) return;
    const start = Date.now();
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [isResearching]);

  // Redirect to results when done
  useEffect(() => {
    if (report && !isResearching) {
      router.push("/research/results");
    }
  }, [report, isResearching, router]);

  // Redirect if no job
  useEffect(() => {
    if (!jobId) {
      router.push("/research");
    }
  }, [jobId, router]);

  if (!jobId) return null;

  const layers = Array.from({ length: maxLayer + 1 }, (_, i) => i);

  function formatTime(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  }

  return (
    <ResearchLayout currentStep={2}>
      <div className="mx-auto max-w-3xl animate-fade-in-up">
        {/* Header with timer */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-foreground">
              Research in Progress
            </h2>
            <p className="mt-1 text-sm text-warm-gray">
              {isResearching
                ? "Running all layers in parallel..."
                : error
                ? "Research encountered an error"
                : "Research complete!"}
            </p>
          </div>
          <div className="flex items-center gap-2 rounded-xl bg-surface-2 px-4 py-2">
            <Clock className="h-4 w-4 text-orange" />
            <span className="font-mono text-sm font-semibold text-foreground">
              {formatTime(elapsed)}
            </span>
          </div>
        </div>

        {error && (
          <div className="mb-6 rounded-lg border border-error/30 bg-error/10 px-4 py-3 text-sm text-error">
            {error}
          </div>
        )}

        {/* Timeline */}
        <div className="glass-card p-6 mb-6">
          <div className="relative">
            {layers.map((layer, i) => {
              const isCompleted = completedLayers.includes(layer);
              const isRunning = currentLayer === layer && !isCompleted;
              const isPending = !isCompleted && !isRunning;

              return (
                <div key={layer} className="flex gap-4">
                  {/* Connector line + node */}
                  <div className="flex flex-col items-center">
                    <div
                      className={cn(
                        "flex h-10 w-10 items-center justify-center rounded-full border-2 transition-all",
                        isCompleted &&
                          "border-purple bg-purple/20 text-purple-light",
                        isRunning &&
                          "border-orange bg-orange/20 text-orange animate-pulse-glow",
                        isPending && "border-surface-3 bg-surface-2 text-warm-gray"
                      )}
                    >
                      {isCompleted ? (
                        <CheckCircle2 className="h-5 w-5" />
                      ) : isRunning ? (
                        <Loader2 className="h-5 w-5 animate-spin" />
                      ) : (
                        <Circle className="h-5 w-5" />
                      )}
                    </div>
                    {i < layers.length - 1 && (
                      <div
                        className={cn(
                          "w-0.5 flex-1 min-h-8",
                          isCompleted ? "bg-purple" : "bg-surface-3"
                        )}
                      />
                    )}
                  </div>

                  {/* Content */}
                  <div className="flex-1 pb-8">
                    <div className="flex items-center gap-2">
                      <h3
                        className={cn(
                          "text-sm font-semibold",
                          isCompleted && "text-purple-light",
                          isRunning && "text-orange",
                          isPending && "text-warm-gray"
                        )}
                      >
                        Layer {layer}: {LAYER_NAMES[layer]}
                      </h3>
                      {isRunning && (
                        <span className="rounded-full bg-orange/20 px-2 py-0.5 text-[10px] font-medium text-orange">
                          Running
                        </span>
                      )}
                      {isCompleted && (
                        <span className="rounded-full bg-purple/20 px-2 py-0.5 text-[10px] font-medium text-purple-light">
                          Complete
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 text-xs text-warm-gray">
                      {LAYER_DESCRIPTIONS[layer]}
                    </p>

                    {/* Layer-specific events */}
                    {progressEvents
                      .filter((e) => e.layer === layer)
                      .map((event, j) => (
                        <div
                          key={j}
                          className="mt-1.5 flex items-start gap-1.5 text-xs"
                        >
                          <ChevronRight className="mt-0.5 h-3 w-3 shrink-0 text-warm-gray" />
                          <span className="text-warm-gray-light">
                            {event.message}
                          </span>
                        </div>
                      ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Activity log */}
        <div className="glass-card overflow-hidden">
          <div className="flex items-center gap-2 border-b border-surface-3 px-4 py-2.5">
            <Activity className="h-3.5 w-3.5 text-orange" />
            <span className="text-[11px] text-warm-gray font-mono">
              Activity Log
            </span>
          </div>
          <div className="max-h-48 overflow-y-auto p-4 font-mono text-xs leading-relaxed">
            {progressEvents.length === 0 && (
              <p className="text-warm-gray">
                Waiting for research to start...
              </p>
            )}
            {progressEvents.map((event, i) => (
              <div
                key={i}
                className="flex items-start gap-2 py-0.5 animate-fade-in-up"
                style={{ animationDelay: `${i * 20}ms` }}
              >
                <span className="shrink-0 text-warm-gray select-none">
                  {new Date(event.timestamp).toLocaleTimeString("en-US", {
                    hour12: false,
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </span>
                <span
                  className={cn(
                    event.status === "start"
                      ? "text-orange font-semibold"
                      : event.status === "done"
                      ? "text-purple-light"
                      : "text-warm-gray-light"
                  )}
                >
                  [L{event.layer}] {event.message}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </ResearchLayout>
  );
}
