"use client";

/**
 * Backend2PipelineTrace — shows every stage of the agentic pipeline at a
 * glance: what ran, what it produced, and key aggregate KPIs.
 *
 * Stages visualised: a0 → a1 → a2 → a3 → a4 → a5 → a6 → a6.5 → a7 → a8 → a8.5
 * Each stage dot is filled/dark when the stage produced output; hollow/dim
 * when the stage was skipped or produced nothing.
 */

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  BrainCircuit,
  Sparkles,
  ListTree,
  Globe,
  BarChart3,
  Newspaper,
  PenTool,
  Layers,
  GitMerge,
  TrendingUp,
  ShieldCheck,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  MessageSquare,
  FileSearch,
  Sigma,
} from "lucide-react";
import type { Backend2Report } from "@/lib/types-backend2";

interface Props {
  report: Backend2Report;
}

interface Stage {
  id: string;
  name: string;
  description: string;
  icon: React.ElementType;
  active: boolean;
  summary: string[];
  tag?: string;
}

function uniqueSources(claims: { citation?: { url?: string | null } | null }[]): number {
  const seen = new Set<string>();
  for (const c of claims) if (c.citation?.url) seen.add(c.citation.url);
  return seen.size;
}

export default function Backend2PipelineTrace({ report }: Props) {
  const [expanded, setExpanded] = useState(false);

  // ── Derived aggregates ────────────────────────────────────────────────────

  const allClaims = [
    ...report.topic_claims,
    ...report.market_claims,
    ...report.news_claims,
  ];
  const totalClaims = allClaims.length;
  const totalSources = uniqueSources(allClaims);
  const grounding = report.verification
    ? Math.round(report.verification.grounding_score * 100)
    : null;
  const wordCount = report.consolidated?.narrative
    ? report.consolidated.narrative.split(/\s+/).length
    : 0;
  const highConsensus = report.dimensional_clusters.filter(
    (c) => c.consensus_level === "high"
  ).length;

  // ── Stage definitions ─────────────────────────────────────────────────────

  const stages: Stage[] = [
    {
      id: "a0",
      name: "Topic Profiler",
      description: "Classifies the domain and extracts expected metric kinds & dimensions.",
      icon: BrainCircuit,
      active: !!report.topic_profile,
      tag: report.topic_profile?.topic_domain ?? undefined,
      summary: report.topic_profile
        ? [
            `domain: ${report.topic_profile.topic_domain}`,
            `${report.topic_profile.key_dimensions.length} key dimensions`,
            `${report.topic_profile.expected_metric_kinds.length} metric kinds`,
          ]
        : ["no profile generated"],
    },
    {
      id: "a1",
      name: "Query Refiner",
      description: "Rewrites the original query into a more precise research question.",
      icon: Sparkles,
      active: !!report.chosen_query,
      summary: report.chosen_query
        ? [
            `"${
              report.chosen_query.length > 80
                ? report.chosen_query.slice(0, 80) + "…"
                : report.chosen_query
            }"`,
          ]
        : ["no variant selected"],
    },
    {
      id: "a2",
      name: "Sub-question Generator",
      description: "Decomposes the query into atomic investigable sub-questions.",
      icon: ListTree,
      active: report.sub_questions.length > 0,
      summary: [
        `${report.sub_questions.length} sub-questions`,
        ...(report.sub_questions.length > 0
          ? [
              `categories: ${[
                ...new Set(report.sub_questions.map((sq) => sq.category)),
              ].join(", ")}`,
            ]
          : []),
      ],
    },
    {
      id: "a3",
      name: "Topic Researcher",
      description: "Searches for quantitative topic claims from authoritative sources.",
      icon: Globe,
      active: report.topic_claims.length > 0,
      summary: [
        `${report.topic_claims.length} claims`,
        `${uniqueSources(report.topic_claims)} sources`,
      ],
    },
    {
      id: "a4",
      name: "Market Researcher",
      description: "Finds market-size, growth-rate and competitive data.",
      icon: BarChart3,
      active: report.market_claims.length > 0 || !!report.market_narrative,
      summary: report.market_claims.length > 0
        ? [
            `${report.market_claims.length} claims`,
            `${uniqueSources(report.market_claims)} sources`,
          ]
        : report.market_narrative
        ? ["ran — no numeric claims extracted"]
        : ["no market data found"],
    },
    {
      id: "a5",
      name: "News Researcher",
      description: "Pulls recent headlines and signals from news sources.",
      icon: Newspaper,
      active: report.news_claims.length > 0,
      summary: [
        `${report.news_claims.length} claims`,
        `${uniqueSources(report.news_claims)} sources`,
      ],
    },
    {
      id: "a6",
      name: "Briefing Composer",
      description: "Two-pass structured composition: outline → prose narrative.",
      icon: PenTool,
      active: !!report.consolidated?.narrative,
      summary: report.consolidated
        ? [
            ...(report.consolidated.outline
              ? [`${report.consolidated.outline.sections.length} sections`]
              : []),
            wordCount > 0 ? `~${wordCount} words` : "",
            report.consolidated.footnotes.length > 0
              ? `${report.consolidated.footnotes.length} footnotes`
              : "",
          ].filter(Boolean)
        : ["no brief composed"],
    },
    {
      id: "a6.5",
      name: "Cluster Analyser",
      description: "Clusters numeric claims into consensus groups with statistical analysis.",
      icon: Layers,
      active: report.dimensional_clusters.length > 0,
      summary: [
        `${report.dimensional_clusters.length} clusters`,
        ...(report.dimensional_clusters.length > 0
          ? [
              `${highConsensus} high-consensus`,
              `${report.dimensional_clusters.filter((c) => c.n_unique_sources >= 2).length} multi-source`,
            ]
          : []),
      ],
    },
    {
      id: "a7",
      name: "Conflict Resolver",
      description: "Validates claims and arbitrates contradictory numeric evidence.",
      icon: GitMerge,
      active: report.validated_claims.length > 0,
      summary: [
        `${report.validated_claims.length} validated claims`,
        report.conflicts.length > 0
          ? `${report.conflicts.length} conflict${report.conflicts.length !== 1 ? "s" : ""} resolved`
          : "no conflicts",
      ],
    },
    {
      id: "a8",
      name: "Causation Analyser",
      description: "Identifies causal drivers and deltas between evidence data points.",
      icon: TrendingUp,
      // Active if pipeline reached a8 (validated_claims proves a7 completed)
      active: report.causations.length > 0 || report.validated_claims.length > 0,
      summary:
        report.causations.length > 0
          ? [
              `${report.causations.length} causation chain${
                report.causations.length !== 1 ? "s" : ""
              }`,
            ]
          : report.validated_claims.length > 0
          ? ["ran — no causal patterns found"]
          : ["not run"],
    },
    {
      id: "a8.5",
      name: "Grounding Verifier",
      description: "Cross-checks every prose claim against the source evidence set.",
      icon: ShieldCheck,
      active: !!report.verification,
      summary: report.verification
        ? [
            `${grounding}% grounded`,
            `${report.verification.verified_claims} / ${report.verification.total_claims} verified`,
            ...(report.verification.fabricated.length > 0
              ? [`${report.verification.fabricated.length} likely fabricated`]
              : []),
          ]
        : ["not verified"],
    },
  ];

  const activeCount = stages.filter((s) => s.active).length;

  // ── KPI tiles ─────────────────────────────────────────────────────────────

  const kpis = [
    {
      icon: FileSearch,
      label: "Total claims",
      value: totalClaims.toString(),
      sub: `${totalSources} unique sources`,
    },
    {
      icon: Sigma,
      label: "Clusters",
      value: report.dimensional_clusters.length.toString(),
      sub: `${highConsensus} high-consensus`,
    },
    {
      icon: ShieldCheck,
      label: "Grounding",
      value: grounding !== null ? `${grounding}%` : "—",
      sub:
        grounding !== null
          ? `${report.verification!.verified_claims} verified`
          : "verifier skipped",
    },
    {
      icon: MessageSquare,
      label: "Sub-questions",
      value: report.sub_questions.length > 0 ? report.sub_questions.length.toString() : "—",
      sub:
        report.sub_questions.length > 0
          ? `${[...new Set(report.sub_questions.map((sq) => sq.category))].length} categories · ${activeCount}/${stages.length} stages`
          : `${activeCount}/${stages.length} stages ran`,
    },
  ];

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className="glass-card p-6 mb-6"
    >
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between mb-5 gap-3">
        <div>
          <span className="inline-flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-muted-foreground mb-1">
            <span className="w-5 h-px bg-foreground/30" />
            Pipeline Trace · agentic backend
          </span>
          <h2 className="font-display text-xl text-foreground">
            How the agent built this brief
          </h2>
        </div>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="shrink-0 flex items-center gap-1.5 text-xs font-mono text-muted-foreground hover:text-foreground transition-colors border border-foreground/10 rounded-full px-3 py-1.5 hover:bg-foreground/5"
        >
          {expanded ? (
            <>
              Collapse <ChevronUp className="w-3 h-3" />
            </>
          ) : (
            <>
              Expand <ChevronDown className="w-3 h-3" />
            </>
          )}
        </button>
      </div>

      {/* ── KPI tiles ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-foreground/8 rounded-xl overflow-hidden mb-5">
        {kpis.map((kpi) => {
          const Icon = kpi.icon;
          return (
            <div key={kpi.label} className="bg-background/70 px-4 py-3">
              <div className="flex items-center gap-1.5 mb-1">
                <Icon className="w-3.5 h-3.5 text-muted-foreground" />
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
                  {kpi.label}
                </span>
              </div>
              <div className="text-2xl font-display tracking-tight text-foreground">
                {kpi.value}
              </div>
              <div className="text-[11px] text-foreground/45 mt-0.5 font-mono">
                {kpi.sub}
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Compact pipeline strip (always visible) ────────────────────── */}
      <div className="flex items-center gap-1 flex-wrap mb-2">
        {stages.map((stage, idx) => {
          const Icon = stage.icon;
          const isLast = idx === stages.length - 1;
          return (
            <div key={stage.id} className="flex items-center gap-1">
              <div
                title={`${stage.id}: ${stage.name}`}
                className={`flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-mono border transition-all ${
                  stage.active
                    ? "bg-foreground/8 border-foreground/20 text-foreground/80"
                    : "bg-transparent border-foreground/6 text-foreground/25"
                }`}
              >
                <Icon className="w-3 h-3" />
                <span>{stage.id}</span>
                {stage.active && (
                  <CheckCircle2 className="w-2.5 h-2.5 text-emerald-600" />
                )}
              </div>
              {!isLast && (
                <span className="text-foreground/15 text-[10px]">›</span>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Expanded timeline ───────────────────────────────────────────── */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="mt-5 pt-5 border-t border-foreground/8 relative">
              {/* Vertical connecting rail */}
              <div className="absolute left-[15px] top-5 bottom-0 w-px bg-foreground/8" />

              <div className="space-y-0">
                {stages.map((stage, idx) => {
                  const Icon = stage.icon;
                  const isLast = idx === stages.length - 1;
                  return (
                    <motion.div
                      key={stage.id}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.2, delay: idx * 0.035 }}
                      className={`relative flex gap-4 ${isLast ? "pb-0" : "pb-4"}`}
                    >
                      {/* Stage dot */}
                      <div
                        className={`relative z-10 flex-shrink-0 w-[30px] h-[30px] rounded-full flex items-center justify-center border-2 transition-all ${
                          stage.active
                            ? "bg-foreground border-foreground text-background"
                            : "bg-background border-foreground/12 text-foreground/20"
                        }`}
                      >
                        <Icon className="w-3.5 h-3.5" />
                      </div>

                      {/* Stage content */}
                      <div
                        className={`flex-1 min-w-0 pt-0.5 ${
                          !isLast ? "pb-1 border-b border-foreground/5" : ""
                        }`}
                      >
                        <div className="flex items-center gap-2 flex-wrap mb-0.5">
                          <span
                            className={`text-[9px] font-mono font-bold uppercase tracking-widest px-1.5 py-0.5 rounded border ${
                              stage.active
                                ? "text-foreground/60 border-foreground/18 bg-foreground/5"
                                : "text-foreground/20 border-foreground/8"
                            }`}
                          >
                            {stage.id}
                          </span>
                          <span
                            className={`text-sm font-medium ${
                              stage.active ? "text-foreground" : "text-foreground/25"
                            }`}
                          >
                            {stage.name}
                          </span>
                          {stage.tag && (
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-foreground/6 text-foreground/50 border border-foreground/10">
                              {stage.tag}
                            </span>
                          )}
                          {stage.active && (
                            <CheckCircle2 className="w-3 h-3 text-emerald-600 shrink-0" />
                          )}
                        </div>

                        <p
                          className={`text-[11px] mb-1 ${
                            stage.active
                              ? "text-muted-foreground"
                              : "text-foreground/20"
                          }`}
                        >
                          {stage.description}
                        </p>

                        <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                          {stage.summary.map((s, i) => (
                            <span
                              key={i}
                              className={`text-[11px] font-mono ${
                                stage.active
                                  ? "text-foreground/60"
                                  : "text-foreground/18"
                              }`}
                            >
                              {s}
                            </span>
                          ))}
                        </div>
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
