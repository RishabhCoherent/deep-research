"use client";

import { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import {
  Clock,
  CheckCircle2,
  Circle,
  Loader2,
  ChevronRight,
} from "lucide-react";
import { ResearchLayout } from "@/components/ResearchLayout";
import { useResearchStore } from "@/lib/store";
import { useResearch } from "@/hooks/useResearch";
import { cn } from "@/lib/utils";
import { LAYER_NAMES, LAYER_DESCRIPTIONS, type ResearchTreeData } from "@/lib/types";
import { DecompositionTree } from "@/components/DecompositionTree";
import Backend2NodeProgress from "@/components/backend2/Backend2NodeProgress";
import Backend2VariantPicker from "@/components/backend2/Backend2VariantPicker";

export default function ResearchProgressPage() {
  const router = useRouter();
  const {
    backend,
    jobId,
    topic,
    isResearching,
    currentLayer,
    completedLayers,
    progressEvents,
    report,
    error,
    maxLayer,
    graphNodes,
    backend2Report,
    backend2NodesStarted,
    backend2NodesDone,
    backend2Events,
    backend2VariantOptions,
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

  // Redirect to results when done — branched on active backend.
  useEffect(() => {
    if (backend === "agentic") {
      if (backend2Report && !isResearching) {
        router.push("/research/results");
      }
    } else {
      if (report && !isResearching) {
        router.push("/research/results");
      }
    }
  }, [backend, report, backend2Report, isResearching, router]);

  // Redirect if no job
  useEffect(() => {
    if (!jobId) {
      router.push("/research");
    }
  }, [jobId, router]);

  if (!jobId) return null;

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
            {backend === "agentic" ? "Agent Pipeline · backend2" : "Research Pipeline"}
          </span>
          <h1 className="text-3xl lg:text-4xl font-display leading-[1.1] tracking-tight">
            Research in progress
          </h1>
          <p className="mt-3 text-base text-muted-foreground">
            {isResearching
              ? backend === "agentic"
                ? "Running multi-agent crew (a0 → a8.5)..."
                : "Running all layers sequentially..."
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

      {backend === "agentic" ? (
        <>
          {backend2VariantOptions && backend2VariantOptions.length > 0 && jobId && (
            <Backend2VariantPicker
              jobId={jobId}
              originalQuery={topic}
              variants={backend2VariantOptions}
            />
          )}
          <Backend2ProgressBody
            isVisible={isVisible}
            isResearching={isResearching}
            nodesStarted={backend2NodesStarted}
            nodesDone={backend2NodesDone}
            topicDomain={backend2Report?.topic_profile?.topic_domain ?? null}
            events={backend2Events}
          />
        </>
      ) : (
        <LegacyProgressBody
          isVisible={isVisible}
          isResearching={isResearching}
          maxLayer={maxLayer}
          currentLayer={currentLayer}
          completedLayers={completedLayers}
          progressEvents={progressEvents}
          graphNodes={graphNodes}
        />
      )}
    </ResearchLayout>
  );
}

// ─────────────────────────────────────────────────────────────────
// Backend2 (agentic) progress body
// ─────────────────────────────────────────────────────────────────

function Backend2ProgressBody({
  isVisible,
  isResearching,
  nodesStarted,
  nodesDone,
  topicDomain,
  events,
}: {
  isVisible: boolean;
  isResearching: boolean;
  nodesStarted: Set<string>;
  nodesDone: Set<string>;
  topicDomain: string | null;
  events: ReturnType<typeof useResearchStore.getState>["backend2Events"];
}) {
  return (
    <div className="grid lg:grid-cols-[1fr_380px] gap-12">
      {/* Left: agent timeline */}
      <div
        className={`transition-all duration-700 delay-150 ${
          isVisible
            ? "opacity-100 translate-y-0"
            : "opacity-0 translate-y-8"
        }`}
      >
        <Backend2NodeProgress
          nodesStarted={nodesStarted}
          nodesDone={nodesDone}
          topicDomain={topicDomain}
          isResearching={isResearching}
        />
      </div>

      {/* Right: activity log (raw SSE events) */}
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
              Event Log
            </span>
          </div>
          <div className="max-h-125 overflow-y-auto p-4 font-mono text-xs leading-relaxed">
            {events.length === 0 && (
              <p className="text-muted-foreground">
                Waiting for crew to start...
              </p>
            )}
            {events.map((ev, i) => (
              <div
                key={i}
                className="flex items-start gap-2 py-0.5 animate-fade-in-up"
                style={{ animationDelay: `${i * 20}ms` }}
              >
                <span className="shrink-0 text-muted-foreground/60 select-none">
                  {new Date(ev.timestamp).toLocaleTimeString("en-US", {
                    hour12: false,
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </span>
                <span
                  className={cn(
                    ev.event === "node_started"
                      ? "text-purple font-semibold"
                      : ev.event === "node_done"
                      ? "text-foreground"
                      : ev.event === "done"
                      ? "text-emerald-600 font-semibold"
                      : "text-muted-foreground",
                  )}
                >
                  {ev.event}
                  {ev.node ? ` · ${ev.node}` : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Legacy 3-layer progress body
// ─────────────────────────────────────────────────────────────────

function LegacyProgressBody({
  isVisible,
  isResearching,
  maxLayer,
  currentLayer,
  completedLayers,
  progressEvents,
  graphNodes,
}: {
  isVisible: boolean;
  isResearching: boolean;
  maxLayer: number;
  currentLayer: number;
  completedLayers: number[];
  progressEvents: ReturnType<typeof useResearchStore.getState>["progressEvents"];
  graphNodes: ReturnType<typeof useResearchStore.getState>["graphNodes"];
}) {
  const layers = Array.from({ length: maxLayer + 1 }, (_, i) => i);

  // Derive live tree data from graphNodes
  const liveTreeData = useMemo((): ResearchTreeData | null => {
    const nodeCount = Object.keys(graphNodes).length;
    if (nodeCount === 0) return null;

    const topicNode = Object.values(graphNodes).find(
      (n) => n.depth === 0 || n.why_created === "topic_root",
    );
    const sq_to_root: Record<string, string> = {};
    for (const node of Object.values(graphNodes)) {
      if (node.depth === 1 && node.sq_id) {
        sq_to_root[node.sq_id] = node.id;
      }
    }
    const maxDepth = Math.max(0, ...Object.values(graphNodes).map((n) => n.depth));

    return {
      nodes: graphNodes,
      total_nodes: nodeCount,
      max_depth: maxDepth,
      topic_root_id: topicNode?.id,
      sq_to_root,
    };
  }, [graphNodes]);

  return (
    <>
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
                  <div
                    className={cn(
                      "glass-card rounded-2xl p-6 transition-all duration-500",
                      isRunning && "border-purple/30 glow-sm",
                    )}
                  >
                    <div className="flex items-start gap-4">
                      <div
                        className={cn(
                          "flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-all",
                          isCompleted && "bg-foreground text-background",
                          isRunning &&
                            "border-2 border-purple bg-purple/10 text-purple animate-pulse-glow",
                          isPending && "bg-foreground/5 text-muted-foreground",
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

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <h3
                            className={cn(
                              "font-display text-base",
                              isCompleted && "text-foreground",
                              isRunning && "text-purple",
                              isPending && "text-muted-foreground",
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

                  {i < layers.length - 1 && (
                    <div className="flex justify-center py-1">
                      <div
                        className={cn(
                          "w-0.5 h-6 rounded-full transition-colors duration-500",
                          isCompleted ? "bg-foreground" : "bg-foreground/10",
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
                        : "text-muted-foreground",
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

      {/* Live Research Tree */}
      {liveTreeData && liveTreeData.total_nodes > 0 && (
        <div className="mt-12">
          <div className="flex items-center justify-between mb-4">
            <div>
              <span className="text-xs font-mono uppercase tracking-wider text-muted-foreground">
                Research Tree
              </span>
              <p className="text-sm text-muted-foreground mt-0.5">
                {liveTreeData.total_nodes} node{liveTreeData.total_nodes !== 1 ? "s" : ""}
                {isResearching && (
                  <span className="ml-2 text-purple animate-pulse">· building...</span>
                )}
              </p>
            </div>
          </div>
          <DecompositionTree treeData={liveTreeData} className="h-130" />
        </div>
      )}
    </>
  );
}
