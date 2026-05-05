"use client";

/**
 * Backend2NodeProgress — vertical timeline of a0 → a8.5 nodes.
 *
 * Replaces the layer-cards UI on the progress page when the active backend
 * is "agentic". Each node card surfaces:
 *   - Node id + human-friendly title
 *   - Status (pending / running / done / skipped) — driven by the SSE
 *     events `node_started` / `node_done`
 *   - Status indicator (pulse-glow when running, check when done)
 *
 * Reuses: glass-card, pulse-glow, brand purple/orange tokens, Framer
 * Motion patterns. Same aesthetic as the legacy progress page so the
 * visual identity is preserved.
 */

import { useMemo } from "react";
import { motion } from "framer-motion";
import { CheckCircle2, Loader2, Clock, MinusCircle } from "lucide-react";

interface Props {
  nodesStarted: Set<string>;
  nodesDone: Set<string>;
  topicDomain: string | null;
  isResearching: boolean;
}

interface NodeDef {
  id: string;
  title: string;
  blurb: string;
}

const NODES: NodeDef[] = [
  { id: "a0_topic_profile", title: "Topic Profile", blurb: "Generate domain + expected metric vocabulary" },
  { id: "a1_refiner",        title: "Query Refiner", blurb: "Sharpen the query into analyst-grade variants" },
  { id: "a2_questions",      title: "Question Generator", blurb: "Decompose into 8-15 atomic sub-questions" },
  { id: "a3_topic",          title: "Topic Researcher", blurb: "Recursive: decompose → search → scrape → extract" },
  { id: "a4_market",         title: "Market Context", blurb: "Parent market + value chain (skipped for non-market)" },
  { id: "a5_news",           title: "News & Events", blurb: "Recent events / regulatory / disruptions" },
  { id: "a6_5_clusterer",    title: "Dimensional Clustering", blurb: "Group claims by qualifier hash, find consensus" },
  { id: "a6_consolidator",   title: "Consolidator", blurb: "Two-pass compose: outline → prose with frameworks" },
  { id: "a7_validator",      title: "Validator", blurb: "Authority ranking + cross-check + conflict resolution" },
  { id: "a8_causation",      title: "Causation", blurb: "Detect deltas, correlate with events" },
  { id: "a8_5_verifier",     title: "Verifier", blurb: "Fact-check brief; compute grounding score" },
];

type Status = "pending" | "running" | "done" | "skipped";

function _statusOf(
  node: NodeDef,
  started: Set<string>,
  done: Set<string>,
  isMarketResearch: boolean | null,
): Status {
  // a4 is conditional — for non-market topics it never starts and we should
  // render it as "skipped" rather than "pending forever".
  if (node.id === "a4_market" && isMarketResearch === false) {
    return "skipped";
  }
  if (done.has(node.id)) return "done";
  if (started.has(node.id)) return "running";
  return "pending";
}

function _StatusIcon({ status }: { status: Status }) {
  if (status === "done") {
    return <CheckCircle2 className="w-5 h-5 text-emerald-600" />;
  }
  if (status === "running") {
    return (
      <Loader2 className="w-5 h-5 text-[var(--color-purple)] animate-spin" />
    );
  }
  if (status === "skipped") {
    return <MinusCircle className="w-5 h-5 text-slate-300" />;
  }
  return <Clock className="w-5 h-5 text-slate-300" />;
}

export default function Backend2NodeProgress({
  nodesStarted,
  nodesDone,
  topicDomain,
  isResearching,
}: Props) {
  const isMarketResearch = useMemo(() => {
    if (!topicDomain) return null;
    const d = topicDomain.toLowerCase();
    return d.includes("market") || d.includes("industry");
  }, [topicDomain]);

  const totalDone = nodesDone.size;
  const totalApplicable = NODES.filter(
    (n) => !(n.id === "a4_market" && isMarketResearch === false)
  ).length;
  const pct = Math.round((totalDone / totalApplicable) * 100);

  return (
    <div className="space-y-4">
      {/* Top progress bar */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card p-4"
      >
        <div className="flex items-center justify-between mb-2">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">
              Agent Pipeline
            </div>
            <h3 className="font-[Instrument_Serif,Georgia,serif] text-lg text-slate-900">
              {isResearching ? "Running…" : totalDone === totalApplicable ? "Complete" : "Idle"}
            </h3>
          </div>
          <span className="font-mono text-2xl text-[var(--color-purple)]">
            {pct}%
          </span>
        </div>
        <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
          <motion.div
            className="h-full bg-gradient-to-r from-[var(--color-purple)] to-[var(--color-orange)]"
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.4, ease: "easeOut" }}
          />
        </div>
      </motion.div>

      {/* Vertical timeline of nodes */}
      <div className="relative">
        {/* Spine line */}
        <div className="absolute left-[27px] top-2 bottom-2 w-px bg-slate-200" />

        <div className="space-y-2">
          {NODES.map((node, idx) => {
            const status = _statusOf(node, nodesStarted, nodesDone, isMarketResearch);
            const isRunning = status === "running";
            const isDone = status === "done";
            const isSkipped = status === "skipped";

            return (
              <motion.div
                key={node.id}
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.25, delay: idx * 0.03 }}
                className={`flex items-start gap-4 p-3 rounded-md transition-colors ${
                  isRunning
                    ? "glass-card pulse-glow"
                    : isDone
                    ? "bg-emerald-50/30"
                    : isSkipped
                    ? "opacity-50"
                    : "opacity-70"
                }`}
              >
                <div className="shrink-0 z-10 mt-0.5 bg-white rounded-full p-1 border border-slate-200">
                  <_StatusIcon status={status} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                    <span className="text-[10px] uppercase tracking-wider text-slate-400 font-mono">
                      {node.id}
                    </span>
                    {status !== "pending" && (
                      <span
                        className={`text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                          isDone
                            ? "bg-emerald-500/10 text-emerald-700"
                            : isRunning
                            ? "bg-[var(--color-purple)]/10 text-[var(--color-purple)]"
                            : "bg-slate-200 text-slate-500"
                        }`}
                      >
                        {status}
                      </span>
                    )}
                  </div>
                  <div className="font-medium text-slate-900 text-sm">
                    {node.title}
                  </div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {isSkipped
                      ? `Skipped — domain is ${topicDomain || "non-market"}`
                      : node.blurb}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
