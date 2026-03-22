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

  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    setIsVisible(true);
  }, []);

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
            Research Pipeline
          </span>
          <h1 className="text-3xl lg:text-4xl font-display leading-[1.1] tracking-tight">
            Research in progress
          </h1>
          <p className="mt-3 text-base text-muted-foreground">
            {isResearching
              ? "Running all layers sequentially..."
              : error
              ? "Research encountered an error"
              : "Research complete!"}
          </p>
        </div>
        <div
          className={`transition-all duration-700 delay-100 ${
            isVisible
              ? "opacity-100 translate-y-0"
              : "opacity-0 translate-y-4"
          }`}
        >
          <div className="glass-card flex items-center gap-2.5 rounded-full px-5 py-2.5">
            <span className="h-2 w-2 rounded-full bg-purple animate-pulse" />
            <Clock className="h-4 w-4 text-muted-foreground" />
            <span className="font-mono text-sm font-semibold text-foreground">
              {formatTime(elapsed)}
            </span>
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* ── Two-column layout ────────────────────────────── */}
      <div className="grid lg:grid-cols-[1fr_380px] gap-12">
        {/* Left: Layer Progress Cards */}
        <div
          className={`transition-all duration-700 delay-150 ${
            isVisible
              ? "opacity-100 translate-y-0"
              : "opacity-0 translate-y-8"
          }`}
        >
          <div className="space-y-3">
            {layers.map((layer, i) => {
              const isCompleted = completedLayers.includes(layer);
              const isRunning = currentLayer === layer && !isCompleted;
              const isPending = !isCompleted && !isRunning;

              return (
                <div key={layer}>
                  {/* Card */}
                  <div
                    className={cn(
                      "glass-card rounded-2xl p-6 transition-all duration-500",
                      isRunning && "border-purple/30 glow-sm"
                    )}
                  >
                    <div className="flex items-start gap-4">
                      {/* Status circle */}
                      <div
                        className={cn(
                          "flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-all",
                          isCompleted &&
                            "bg-foreground text-background",
                          isRunning &&
                            "border-2 border-purple bg-purple/10 text-purple animate-pulse-glow",
                          isPending &&
                            "bg-foreground/5 text-muted-foreground"
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

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <h3
                            className={cn(
                              "font-display text-base",
                              isCompleted && "text-foreground",
                              isRunning && "text-purple",
                              isPending && "text-muted-foreground"
                            )}
                          >
                            {LAYER_NAMES[layer]}
                          </h3>
                          {isRunning && (
                            <span className="rounded-full bg-purple/10 px-2.5 py-0.5 text-[10px] font-mono font-medium text-purple">
                              RUNNING
                            </span>
                          )}
                          {isCompleted && (
                            <span className="rounded-full bg-foreground/10 px-2.5 py-0.5 text-[10px] font-mono font-medium text-foreground">
                              COMPLETE
                            </span>
                          )}
                        </div>
                        <p className="mt-1 text-sm text-muted-foreground">
                          {LAYER_DESCRIPTIONS[layer]}
                        </p>

                        {/* Layer events */}
                        {progressEvents
                          .filter((e) => e.layer === layer)
                          .map((event, j) => (
                            <div
                              key={j}
                              className="mt-1.5 flex items-start gap-1.5 text-xs animate-fade-in-up"
                              style={{ animationDelay: `${j * 30}ms` }}
                            >
                              <ChevronRight className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
                              <span className="text-muted-foreground">
                                {event.message}
                              </span>
                            </div>
                          ))}
                      </div>
                    </div>
                  </div>

                  {/* Connecting line between cards */}
                  {i < layers.length - 1 && (
                    <div className="flex justify-center py-1">
                      <div
                        className={cn(
                          "w-0.5 h-6 rounded-full transition-colors duration-500",
                          isCompleted ? "bg-foreground" : "bg-foreground/10"
                        )}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Right: Activity Feed */}
        <div
          className={`transition-all duration-700 delay-300 ${
            isVisible
              ? "opacity-100 translate-y-0"
              : "opacity-0 translate-y-8"
          }`}
        >
          <div className="glass-card rounded-2xl overflow-hidden lg:sticky lg:top-24">
            <div className="flex items-center gap-2 border-b border-foreground/10 px-5 py-3.5">
              <span className="h-2 w-2 rounded-full bg-purple animate-pulse" />
              <span className="text-xs font-mono uppercase tracking-wider text-muted-foreground">
                Activity Log
              </span>
            </div>
            <div className="max-h-125 overflow-y-auto p-4 font-mono text-xs leading-relaxed">
              {progressEvents.length === 0 && (
                <p className="text-muted-foreground">
                  Waiting for research to start...
                </p>
              )}
              {progressEvents.map((event, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 py-0.5 animate-fade-in-up"
                  style={{ animationDelay: `${i * 20}ms` }}
                >
                  <span className="shrink-0 text-muted-foreground/60 select-none">
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
                        ? "text-purple font-semibold"
                        : event.status === "done"
                        ? "text-foreground"
                        : "text-muted-foreground"
                    )}
                  >
                    [L{event.layer}] {event.message}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </ResearchLayout>
  );
}
