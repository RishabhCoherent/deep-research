"use client";

import { useState, useEffect } from "react";
import {
  Search,
  Globe,
  CheckCircle2,
  BarChart3,
  ChevronDown,
  ChevronUp,
  ArrowRight,
  ArrowDown,
  Activity,
  Clock,
  FileText,
  Target,
  RefreshCw,
  AlertTriangle,
  TrendingDown,
  Shuffle,
  ExternalLink,
  ClipboardList,
  Database,
  ShieldCheck,
  PenTool,
  Lightbulb,
  BookOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { LayerResult, LayerEvaluation, LayerComparisonData } from "@/lib/types";
import { LAYER_NAMES } from "@/lib/types";
import { EvidenceCards } from "@/components/EvidenceCards";

// ─── Config ──────────────────────────────────────────────────────────────────

const LAYER_CFG = {
  0: {
    color: "#6B7280",
    glow: "rgba(107,114,128,0.2)",
    bg: "rgba(107,114,128,0.06)",
    border: "rgba(107,114,128,0.2)",
    chipBg: "rgba(107,114,128,0.12)",
    Icon: FileText,
    role: "Baseline analyst",
    description: "Single LLM prompt — no tools, no web research. Model knowledge only.",
  },
  1: {
    color: "#7C3AED",
    glow: "rgba(124,58,237,0.25)",
    bg: "rgba(124,58,237,0.07)",
    border: "rgba(124,58,237,0.22)",
    chipBg: "rgba(124,58,237,0.12)",
    Icon: Search,
    role: "Enhanced researcher",
    description: "ReAct agent with web search — finds real data and writes a sourced report.",
  },
  2: {
    color: "#E11D48",
    glow: "rgba(225,29,72,0.25)",
    bg: "rgba(225,29,72,0.07)",
    border: "rgba(225,29,72,0.22)",
    chipBg: "rgba(225,29,72,0.12)",
    Icon: Target,
    role: "CMI Expert pipeline",
    description: "5-phase pipeline: Dissect → Plan → Investigate → Synthesize → Compose.",
  },
} as const;

type LayerKey = keyof typeof LAYER_CFG;

const DIMENSION_LABELS: Record<string, string> = {
  factual_density: "Factual Density",
  source_grounding: "Source Grounding",
  analytical_depth: "Analytical Depth",
  specificity: "Specificity",
  insight_quality: "Insight Quality",
  completeness: "Completeness",
};

// ─── Types ───────────────────────────────────────────────────────────────────

interface QueryHit {
  title: string;
  snippet: string;
  url: string;
}

interface QueryWithHits {
  tool?: string;
  query: string;
  hits: QueryHit[];
}

interface IterHistory {
  iteration: number;
  score: number;
  weaknesses?: string[];
  queries?: Array<string | QueryWithHits>;
  stop_reason?: string; // "threshold" | "plateau" | ""
}

interface PhaseDetail {
  phase: string; // "dissect" | "plan" | "investigate" | "synthesize" | "compose"
  // dissect
  claims_total?: number;
  claims_weak?: number;
  // plan
  sections?: number;
  questions?: number;
  report_type?: string;
  section_names?: string[];
  questions_by_section?: Record<string, Array<{
    question: string;
    priority: number;
    data_type: string;
    queries: string[];
  }>>;
  // investigate
  facts?: number;
  sources?: number;
  coverage?: number;
  searches?: number;
  scrapes?: number;
  facts_by_section?: Record<string, number>;
  questions_answered?: number;
  questions_gap?: number;
  // synthesize
  insights?: number;
  cross_links?: number;
  risks?: number;
  gaps?: number;
  insight_texts?: string[];
  risk_texts?: string[];
  section_impacts?: Array<{ section: string; impact: string; reason: string }>;
  verify_by_section?: Record<string, { total: number; high_confidence: number }>;
  // compose
  words?: number;
  review_score?: number;
  refinement_ran?: boolean;
  pre_refinement_score?: number;
  issues_fixed?: number;
  // legacy aliases (old 4-phase pipeline compat)
  verified?: number;
  corrected?: number;
  // all
  elapsed?: number;
}

function normalizeQuery(q: string | QueryWithHits): QueryWithHits {
  if (typeof q === "string") return { tool: "search_web", query: q, hits: [] };
  return { tool: q.tool ?? "search_web", ...q };
}

/* Tool display config for query chips */
const TOOL_DISPLAY: Record<string, { label: string; icon: string }> = {
  search_web: { label: "search", icon: "🔍" },
  scrape_page: { label: "scrape", icon: "📄" },
  verify_claim: { label: "verify", icon: "✓" },
  challenge_assumption: { label: "challenge", icon: "⚡" },
  find_bear_case: { label: "bear case", icon: "📉" },
  cross_industry_search: { label: "cross-industry", icon: "🔀" },
};

/* Per-layer loop descriptions */
const LOOP_CONFIG: Record<number, { title: string; subtitle: string }> = {
  1: { title: "Research Loop", subtitle: "Search · Scrape · Synthesize" },
  2: { title: "CMI Pipeline", subtitle: "Dissect · Plan · Investigate · Synthesize · Compose" },
};

function safeDomain(url: string): string {
  try { return new URL(url).hostname.replace("www.", ""); }
  catch { return url; }
}

function getPosthocAvg(evaluations: LayerEvaluation[], layerNum: number): number {
  const ev = evaluations.find((e) => e.layer === layerNum);
  if (!ev?.scores) return 0;
  const vals = Object.values(ev.scores)
    .map((s) => (typeof s === "object" && s !== null ? (s as { score: number }).score : 0))
    .filter((v) => v > 0);
  if (vals.length === 0) return 0;
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}

function parseMeta(layer: LayerResult) {
  const m = (layer.metadata ?? {}) as Record<string, unknown>;
  return {
    toolCalls: (m.tool_calls as number) ?? 0,
    iterations: (m.iterations as number) ?? 0,
    finalScore: (m.final_score as number) ?? 0,
    sourcesFound: (m.sources_found as number) ?? layer.source_count,
    sourcesScraped: (m.sources_scraped as number) ?? 0,
    verifications: (m.verifications as number) ?? 0,
    // L3 adversarial metadata
    assumptionsExtracted: (m.assumptions_extracted as string[]) ?? [],
    assumptionChallenges: (m.assumption_challenges as number) ?? 0,
    bearCasesSearched: (m.bear_cases_searched as number) ?? 0,
    crossIndustrySearches: (m.cross_industry_searches as number) ?? 0,
    iterHistory: (m.iteration_history as IterHistory[]) ?? [],
    method: (m.method as string) ?? "single_prompt",
    // CMI-specific
    phaseDetails: (m.phase_details as PhaseDetail[]) ?? [],
    planSections: (m.plan_sections as string[]) ?? [],
    planQuestions: (m.plan_questions as number) ?? 0,
    factsCollected: (m.facts_collected as number) ?? 0,
    factsVerified: (m.facts_verified as number) ?? 0,
    insightsGenerated: (m.insights_generated as number) ?? 0,
    contrarianRisks: (m.contrarian_risks as number) ?? 0,
    reviewScore: (m.review_score as number) ?? 0,
  };
}

// ─── Animated fill bar ────────────────────────────────────────────────────────

function FillBar({
  pct,
  color,
  delay = 0,
  height = "h-1.5",
}: {
  pct: number;
  color: string;
  delay?: number;
  height?: string;
}) {
  const [w, setW] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setW(pct), 120 + delay);
    return () => clearTimeout(t);
  }, [pct, delay]);
  return (
    <div className={cn("relative w-full rounded-full bg-foreground/10 overflow-hidden", height)}>
      <div
        className="absolute inset-y-0 left-0 rounded-full"
        style={{
          width: `${w}%`,
          background: color,
          transition: "width 0.85s cubic-bezier(0.4,0,0.2,1)",
        }}
      />
    </div>
  );
}

// ─── PipelineConnector ────────────────────────────────────────────────────────

function PipelineConnector({ fromColor, toColor }: { fromColor: string; toColor: string }) {
  return (
    <div className="flex flex-1 items-center gap-1 min-w-0 px-0.5 pt-0">
      <div className="relative flex-1 h-px overflow-hidden rounded-full">
        <div className="absolute inset-0 bg-foreground/10" />
        <div
          className="absolute inset-0"
          style={{
            background: `linear-gradient(90deg, ${fromColor}60, ${toColor}60)`,
            animation: "beam-flow 1.8s linear infinite",
          }}
        />
      </div>
      <ArrowRight className="h-3 w-3 shrink-0 text-muted-foreground/40" />
    </div>
  );
}

// ─── PipelineOverview ─────────────────────────────────────────────────────────

function PipelineOverview({
  layers,
  evaluations,
  totalToolCalls,
  totalSources,
  totalElapsed,
  totalQueries,
}: {
  layers: LayerResult[];
  evaluations: LayerEvaluation[];
  totalToolCalls: number;
  totalSources: number;
  totalElapsed: number;
  totalQueries: number;
}) {
  return (
    <div className="glass-card p-5">
      <div className="flex items-center gap-2 mb-5">
        <Activity className="h-4 w-4 text-purple" />
        <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          Agent Pipeline
        </span>
      </div>

      <div className="flex items-start mb-5">
        {layers.map((layer, i) => {
          const key = layer.layer as LayerKey;
          const cfg = LAYER_CFG[key] ?? LAYER_CFG[1];
          const Icon = cfg.Icon;
          const postscore = getPosthocAvg(evaluations, layer.layer);
          const nextCfg =
            i < layers.length - 1
              ? (LAYER_CFG[layers[i + 1].layer as LayerKey] ?? LAYER_CFG[1])
              : null;

          return (
            <div key={layer.layer} className="flex items-center flex-1 min-w-0">
              <div className="flex flex-col items-center shrink-0">
                <div
                  className="relative flex h-12 w-12 items-center justify-center rounded-2xl border-2 transition-transform hover:scale-105"
                  style={{
                    borderColor: cfg.color,
                    background: cfg.bg,
                    boxShadow: `0 0 18px ${cfg.glow}`,
                  }}
                >
                  <Icon className="h-5 w-5" style={{ color: cfg.color }} />
                  <div
                    className="absolute -bottom-2 left-1/2 -translate-x-1/2 rounded-full px-1.5 py-px text-[8px] font-bold text-white"
                    style={{ background: cfg.color }}
                  >
                    L{layer.layer}
                  </div>
                </div>
                <div className="mt-3 text-center">
                  <div className="text-[10px] font-semibold text-foreground leading-tight">
                    {LAYER_NAMES[layer.layer]}
                  </div>
                  {postscore > 0 ? (
                    <div className="text-[11px] font-bold mt-0.5" style={{ color: cfg.color }}>
                      {postscore.toFixed(1)}/10
                    </div>
                  ) : (
                    <div className="text-[10px] text-muted-foreground mt-0.5">—</div>
                  )}
                </div>
              </div>

              {nextCfg && (
                <div className="flex-1 px-1 pt-0">
                  <PipelineConnector fromColor={cfg.color} toColor={nextCfg.color} />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-4 gap-3 border-t border-foreground/10 pt-4">
        <StatBox icon={<Search className="h-3.5 w-3.5" />} label="Searches Run" value={totalQueries} color="#7C3AED" />
        <StatBox icon={<Activity className="h-3.5 w-3.5" />} label="Tool Calls" value={totalToolCalls} color="#EA580C" />
        <StatBox icon={<Globe className="h-3.5 w-3.5" />} label="Sources Found" value={totalSources} color="#E11D48" />
        <StatBox icon={<Clock className="h-3.5 w-3.5" />} label="Total Time" value={`${Math.round(totalElapsed)}s`} color="#059669" />
      </div>
    </div>
  );
}

function StatBox({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: number | string; color: string }) {
  return (
    <div className="rounded-xl bg-foreground/5 px-3 py-2.5 text-center">
      <div className="flex justify-center mb-1" style={{ color }}>{icon}</div>
      <div className="text-sm font-bold" style={{ color }}>{value}</div>
      <div className="text-[10px] text-muted-foreground leading-tight mt-0.5">{label}</div>
    </div>
  );
}

// ─── ReactLoopFlow ────────────────────────────────────────────────────────────
// Visualises the inner ReAct loop: Research → Evaluate → Feedback → Research…

function ReactLoopFlow({
  iterHistory,
  color,
  chipBg,
  layer,
}: {
  iterHistory: IterHistory[];
  color: string;
  chipBg: string;
  layer: number;
}) {
  const [expandedQueries, setExpandedQueries] = useState<number | null>(null);
  const [activeHits, setActiveHits] = useState<{ iter: number; queryText: string } | null>(null);

  if (iterHistory.length === 0) return null;

  const loopCfg = LOOP_CONFIG[layer] ?? LOOP_CONFIG[1];

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <RefreshCw className="h-3 w-3" style={{ color }} />
        <span className="text-[10px] font-semibold uppercase tracking-widest" style={{ color }}>
          {loopCfg.title} — {iterHistory.length} iteration{iterHistory.length !== 1 ? "s" : ""}
        </span>
        <div className="flex-1 h-px bg-foreground/10" />
        <span className="text-[9px] text-muted-foreground">{loopCfg.subtitle}</span>
      </div>

      <div className="space-y-2">
        {iterHistory.map((iter, i) => {
          const isLast = i === iterHistory.length - 1;
          const prev = i > 0 ? iterHistory[i - 1].score : null;
          const delta = prev !== null ? iter.score - prev : null;
          const queries = iter.queries ?? [];
          const weaknesses = iter.weaknesses ?? [];
          const queriesExpanded = expandedQueries === i;
          const visibleQueries = queriesExpanded ? queries : queries.slice(0, 3);

          return (
            <div key={i}>
              {/* ── Research block + Eval block row ──────────────────── */}
              <div className="grid grid-cols-[1fr_16px_1fr] items-stretch gap-1.5">

                {/* Research block */}
                <div
                  className="rounded-xl border p-3"
                  style={{ borderColor: `${color}30`, background: chipBg }}
                >
                  <div
                    className="text-[9px] font-bold uppercase tracking-widest mb-2 flex items-center gap-1"
                    style={{ color }}
                  >
                    <Search className="h-2.5 w-2.5" />
                    {layer === 2 ? `Phase ${i + 1}` : `Round ${i + 1}`}
                    {queries.length > 0 && (
                      <span className="ml-auto font-normal text-muted-foreground">
                        {queries.length}q
                      </span>
                    )}
                  </div>

                  {queries.length > 0 ? (
                    <>
                      <div className="flex flex-wrap gap-1">
                        {visibleQueries.map((q, j) => {
                          const nq = normalizeQuery(q);
                          const isActive = activeHits?.iter === i && activeHits?.queryText === nq.query;
                          const hasHits = nq.hits.length > 0;
                          return (
                            <button
                              key={j}
                              onClick={() => setActiveHits(isActive ? null : { iter: i, queryText: nq.query })}
                              className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] leading-tight transition-opacity hover:opacity-80"
                              style={{
                                background: isActive ? `${color}35` : `${color}15`,
                                color,
                                cursor: hasHits ? "pointer" : "default",
                              }}
                            >
                              {nq.tool && nq.tool !== "search_web" ? (
                                <span className="text-[8px] shrink-0 opacity-70">
                                  {TOOL_DISPLAY[nq.tool]?.icon ?? "🔍"}
                                </span>
                              ) : (
                                <Search className="h-2 w-2 shrink-0 opacity-60" />
                              )}
                              {nq.tool && nq.tool !== "search_web" && (
                                <span className="text-[8px] font-bold uppercase opacity-70 shrink-0">
                                  {TOOL_DISPLAY[nq.tool]?.label}
                                </span>
                              )}
                              {nq.query}
                              {hasHits && (
                                isActive
                                  ? <ChevronUp className="h-2 w-2 shrink-0 opacity-60" />
                                  : <ChevronDown className="h-2 w-2 shrink-0 opacity-60" />
                              )}
                            </button>
                          );
                        })}
                      </div>

                      {/* Hits panel — shown below chips when a query is active */}
                      {activeHits?.iter === i && (() => {
                        const activeQ = queries.map(normalizeQuery).find(q => q.query === activeHits.queryText);
                        if (!activeQ || activeQ.hits.length === 0) return null;
                        return (
                          <div
                            className="mt-2 rounded-lg border p-2 space-y-2"
                            style={{ borderColor: `${color}25`, background: `${color}06` }}
                          >
                            <div className="text-[8px] font-semibold uppercase tracking-wider mb-1" style={{ color }}>
                              Results for &ldquo;{activeQ.query}&rdquo;
                            </div>
                            {activeQ.hits.map((hit, k) => (
                              <a
                                key={k}
                                href={hit.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-start gap-1.5 group"
                              >
                                <ExternalLink className="h-3 w-3 shrink-0 mt-px text-muted-foreground/40 group-hover:text-foreground transition-colors" />
                                <div className="min-w-0">
                                  <div className="text-[10px] font-medium leading-tight group-hover:underline line-clamp-1 text-foreground">
                                    {hit.title || safeDomain(hit.url)}
                                  </div>
                                  <div className="text-[9px] text-muted-foreground leading-snug mt-0.5 line-clamp-2">
                                    {hit.snippet}
                                  </div>
                                  <div className="text-[8px] text-muted-foreground/50 mt-0.5">{safeDomain(hit.url)}</div>
                                </div>
                              </a>
                            ))}
                          </div>
                        );
                      })()}

                      {queries.length > 3 && (
                        <button
                          onClick={() => setExpandedQueries(queriesExpanded ? null : i)}
                          className="mt-1.5 text-[9px] text-muted-foreground hover:text-foreground transition-colors flex items-center gap-0.5"
                        >
                          {queriesExpanded ? (
                            <><ChevronUp className="h-2.5 w-2.5" /> less</>
                          ) : (
                            <><ChevronDown className="h-2.5 w-2.5" /> +{queries.length - 3} more</>
                          )}
                        </button>
                      )}
                    </>
                  ) : (
                    <p className="text-[10px] text-muted-foreground italic">
                      Web research + source synthesis
                    </p>
                  )}
                </div>

                {/* Arrow */}
                <div className="flex items-center justify-center">
                  <ArrowRight className="h-3 w-3 text-muted-foreground/40 shrink-0" />
                </div>

                {/* Evaluation block */}
                <div
                  className="rounded-xl border p-3"
                  style={{
                    borderColor: isLast ? `${color}50` : "rgba(245,158,11,0.35)",
                    background: isLast ? `${color}08` : "rgba(245,158,11,0.06)",
                  }}
                >
                  <div
                    className="text-[9px] font-bold uppercase tracking-widest mb-2 flex items-center gap-1"
                    style={{ color: isLast ? color : "#D97706" }}
                  >
                    <BarChart3 className="h-2.5 w-2.5" />
                    Evaluate
                    {isLast && iter.stop_reason !== "plateau" && <CheckCircle2 className="h-2.5 w-2.5 ml-auto" style={{ color }} />}
                  </div>

                  <div className="flex items-baseline gap-1.5 mb-1.5">
                    <span
                      className="text-xl font-extrabold leading-none"
                      style={{ color: isLast ? color : "#D97706" }}
                    >
                      {iter.score.toFixed(1)}
                    </span>
                    <span className="text-[9px] text-muted-foreground">/10</span>
                    {delta !== null && delta !== 0 && (
                      <span
                        className={cn(
                          "text-[10px] font-bold ml-auto",
                          delta > 0 ? "text-emerald-500" : "text-rose-500"
                        )}
                      >
                        {delta > 0 ? "+" : ""}
                        {delta.toFixed(1)}
                      </span>
                    )}
                  </div>

                  {isLast && iter.stop_reason === "threshold" ? (
                    <span className="text-[9px] font-semibold text-emerald-500 uppercase tracking-wide">
                      Passed ✓
                    </span>
                  ) : isLast && iter.stop_reason === "plateau" ? (
                    <span className="text-[9px] font-semibold text-amber-500 uppercase tracking-wide">
                      Plateau — stopped
                    </span>
                  ) : isLast && !iter.stop_reason ? (
                    <span className="text-[9px] font-semibold text-emerald-500 uppercase tracking-wide">
                      Complete ✓
                    </span>
                  ) : (
                    <div className="space-y-0.5">
                      {weaknesses.slice(0, 2).map((w, j) => (
                        <div key={j} className="flex items-start gap-1">
                          <AlertTriangle className="h-2.5 w-2.5 shrink-0 mt-0.5 text-amber-500" />
                          <span className="text-[9px] text-muted-foreground leading-snug line-clamp-2">
                            {w}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Feedback arrow between iterations */}
              {!isLast && (
                <div className="flex items-center justify-center py-1.5 gap-2">
                  <div className="h-px flex-1 border-t border-dashed border-amber-500/30" />
                  <div className="flex items-center gap-1 text-[8px] font-semibold text-amber-500/70 uppercase tracking-wider">
                    <ArrowDown className="h-2.5 w-2.5" />
                    evaluator feedback → refine
                    <ArrowDown className="h-2.5 w-2.5" />
                  </div>
                  <div className="h-px flex-1 border-t border-dashed border-amber-500/30" />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── CmiPipelineFlow ─────────────────────────────────────────────────────────
// Dedicated visualization for CMI Expert's 4-phase pipeline

const CMI_PHASES = [
  {
    key: "dissect",
    label: "Dissect",
    Icon: ClipboardList,
    color: "#F59E0B",
    description: "Extract & grade every claim from prior report",
  },
  {
    key: "plan",
    label: "Plan",
    Icon: Database,
    color: "#EA580C",
    description: "Generate targeted research queries per claim",
  },
  {
    key: "investigate",
    label: "Investigate",
    Icon: Search,
    color: "#7C3AED",
    description: "Execute research plan with evidence tracking",
  },
  {
    key: "synthesize",
    label: "Synthesize",
    Icon: ShieldCheck,
    color: "#059669",
    description: "Cross-reference findings & generate insights",
  },
  {
    key: "compose",
    label: "Compose",
    Icon: PenTool,
    color: "#E11D48",
    description: "Write definitive report with all evidence",
  },
];

function CmiPipelineFlow({
  phaseDetails,
  planSections,
  planQuestions,
  factsCollected,
  insightsGenerated,
  contrarianRisks,
  color,
}: {
  phaseDetails: PhaseDetail[];
  planSections: string[];
  planQuestions: number;
  factsCollected: number;
  insightsGenerated: number;
  contrarianRisks: number;
  color: string;
}) {
  const [expandedPhase, setExpandedPhase] = useState<string | null>(null);
  const [sectionsExpanded, setSectionsExpanded] = useState(false);

  const getPhase = (key: string) => phaseDetails.find((p) => p.phase === key);

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <Target className="h-3.5 w-3.5" style={{ color }} />
        <span className="text-[10px] font-semibold uppercase tracking-widest" style={{ color }}>
          CMI Expert Pipeline — 5 Phases
        </span>
        <div className="flex-1 h-px bg-foreground/10" />
      </div>

      {/* Phase timeline - horizontal steps */}
      <div className="flex items-center gap-0 mb-5">
        {CMI_PHASES.map((phase, i) => {
          const detail = getPhase(phase.key);
          const isLast = i === CMI_PHASES.length - 1;
          const PhaseIcon = phase.Icon;
          return (
            <div key={phase.key} className="flex items-center flex-1 min-w-0">
              <div className="flex flex-col items-center w-full">
                <div
                  className="flex h-9 w-9 items-center justify-center rounded-xl border-2 transition-transform hover:scale-110 cursor-pointer"
                  style={{
                    borderColor: phase.color,
                    background: `${phase.color}15`,
                    boxShadow: `0 0 12px ${phase.color}30`,
                  }}
                  onClick={() => setExpandedPhase(expandedPhase === phase.key ? null : phase.key)}
                >
                  <PhaseIcon className="h-4 w-4" style={{ color: phase.color }} />
                </div>
                <span className="text-[9px] font-bold mt-1.5" style={{ color: phase.color }}>
                  {phase.label}
                </span>
                {detail?.elapsed && (
                  <span className="text-[8px] text-muted-foreground">{detail.elapsed.toFixed(0)}s</span>
                )}
              </div>
              {!isLast && (
                <div className="flex items-center px-1 -mt-4">
                  <div className="w-6 h-px" style={{ background: `${phase.color}40` }} />
                  <ArrowRight className="h-2.5 w-2.5 text-muted-foreground/40 shrink-0" />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Phase detail cards — 5 phases */}
      <div className="space-y-2.5">
        {CMI_PHASES.map((phase, i) => {
          const p = getPhase(phase.key);
          const isOpen = expandedPhase === phase.key;
          const PhaseIcon = phase.Icon;

          // Build summary text per phase
          let summary = phase.description;
          if (p) {
            if (phase.key === "dissect") {
              summary = `${p.claims_total ?? 0} claims extracted, ${p.claims_weak ?? 0} need research`;
            } else if (phase.key === "plan") {
              summary = `${p.sections ?? 0} sections · ${p.questions ?? 0} targeted queries`;
            } else if (phase.key === "investigate") {
              summary = `${p.facts ?? 0} findings · ${p.sources ?? 0} sources · ${Math.round((p.coverage ?? 0) * 100)}% coverage`;
            } else if (phase.key === "synthesize") {
              summary = `${p.cross_links ?? 0} connections · ${p.insights ?? 0} insights · ${p.gaps ?? 0} gaps`;
            } else if (phase.key === "compose") {
              summary = `${p.words ?? 0} words`;
            }
          }

          return (
            <div
              key={phase.key}
              className="rounded-xl border overflow-hidden transition-all"
              style={{
                borderColor: `${phase.color}30`,
                background: `${phase.color}06`,
              }}
            >
              <button
                onClick={() => setExpandedPhase(isOpen ? null : phase.key)}
                className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left"
              >
                <PhaseIcon className="h-3.5 w-3.5 shrink-0" style={{ color: phase.color }} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: phase.color }}>
                      Phase {i + 1}: {phase.label}
                    </span>
                    <span className="text-[9px] text-muted-foreground">{summary}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {p?.elapsed != null && (
                    <span className="text-[9px] text-muted-foreground">{Number(p.elapsed).toFixed(1)}s</span>
                  )}
                  {p && <CheckCircle2 className="h-3 w-3 text-emerald-500" />}
                  {isOpen ? <ChevronUp className="h-3 w-3 text-muted-foreground" /> : <ChevronDown className="h-3 w-3 text-muted-foreground" />}
                </div>
              </button>

              {isOpen && p && (
                <div className="px-3.5 pb-3 animate-fade-in-up">
                  <div className="border-t pt-2.5" style={{ borderColor: `${phase.color}20` }}>

                    {/* ── Dissect detail ──────────────────── */}
                    {phase.key === "dissect" && (
                      <>
                        <p className="text-[10px] text-muted-foreground mb-2.5">
                          Audited the prior report section by section, extracting every factual claim and grading its evidence quality.
                        </p>
                        <div className="grid grid-cols-2 gap-3">
                          <div className="rounded-lg bg-foreground/5/50 px-3 py-2.5 text-center">
                            <div className="text-lg font-bold" style={{ color: phase.color }}>{p.claims_total ?? 0}</div>
                            <div className="text-[8px] text-muted-foreground mt-0.5">Claims Extracted</div>
                          </div>
                          <div className="rounded-lg bg-foreground/5/50 px-3 py-2.5 text-center">
                            <div className="text-lg font-bold text-amber-500">{p.claims_weak ?? 0}</div>
                            <div className="text-[8px] text-muted-foreground mt-0.5">Need Research</div>
                          </div>
                        </div>
                        {(p.claims_total ?? 0) > 0 && (
                          <div className="mt-3">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-[9px] font-semibold" style={{ color: phase.color }}>Claims Already Strong</span>
                              <span className="text-[10px] font-bold" style={{ color: phase.color }}>
                                {Math.round((1 - (p.claims_weak ?? 0) / (p.claims_total ?? 1)) * 100)}%
                              </span>
                            </div>
                            <FillBar pct={(1 - (p.claims_weak ?? 0) / (p.claims_total ?? 1)) * 100} color={phase.color} height="h-2" />
                          </div>
                        )}
                      </>
                    )}

                    {/* ── Plan detail ─────────────────────── */}
                    {phase.key === "plan" && (
                      <>
                        <p className="text-[10px] text-muted-foreground mb-2.5">
                          Generated targeted search queries for each weak or unsupported claim, with rationale for each search.
                        </p>
                        <div className="grid grid-cols-2 gap-3">
                          <div className="rounded-lg bg-foreground/5/50 px-3 py-2.5 text-center">
                            <div className="text-lg font-bold" style={{ color: phase.color }}>{p.sections ?? planSections.length}</div>
                            <div className="text-[8px] text-muted-foreground mt-0.5">Sections Covered</div>
                          </div>
                          <div className="rounded-lg bg-foreground/5/50 px-3 py-2.5 text-center">
                            <div className="text-lg font-bold" style={{ color: phase.color }}>{p.questions ?? planQuestions}</div>
                            <div className="text-[8px] text-muted-foreground mt-0.5">Search Queries</div>
                          </div>
                        </div>
                        {planSections.length > 0 && (
                          <div className="mt-3">
                            <button
                              onClick={() => setSectionsExpanded(!sectionsExpanded)}
                              className="flex items-center gap-1 text-[9px] font-semibold mb-1.5"
                              style={{ color: phase.color }}
                            >
                              <BookOpen className="h-2.5 w-2.5" />
                              Report Sections ({planSections.length})
                              {sectionsExpanded ? <ChevronUp className="h-2 w-2" /> : <ChevronDown className="h-2 w-2" />}
                            </button>
                            {sectionsExpanded && (
                              <div className="flex flex-wrap gap-1.5">
                                {planSections.map((section, si) => (
                                  <span
                                    key={si}
                                    className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[9px]"
                                    style={{ background: `${phase.color}15`, color: phase.color }}
                                  >
                                    <span className="text-[8px] opacity-60">{si + 1}</span>
                                    {section}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </>
                    )}

                    {/* ── Investigate detail ──────────────── */}
                    {phase.key === "investigate" && (
                      <>
                        <p className="text-[10px] text-muted-foreground mb-2.5">
                          Executed the research plan via agent with evidence tracking — each discovery mapped back to a specific claim.
                        </p>
                        {p.coverage !== undefined && (
                          <div className="mb-3">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-[9px] font-semibold" style={{ color: phase.color }}>Claim Coverage</span>
                              <span className="text-[10px] font-bold" style={{ color: phase.color }}>
                                {Math.round((p.coverage ?? 0) * 100)}%
                              </span>
                            </div>
                            <FillBar pct={(p.coverage ?? 0) * 100} color={phase.color} height="h-2" />
                          </div>
                        )}
                        <div className="grid grid-cols-4 gap-2">
                          <div className="rounded-lg bg-foreground/5/50 px-2 py-2 text-center">
                            <div className="text-sm font-bold" style={{ color: phase.color }}>{p.facts ?? factsCollected}</div>
                            <div className="text-[8px] text-muted-foreground mt-0.5">Findings</div>
                          </div>
                          <div className="rounded-lg bg-foreground/5/50 px-2 py-2 text-center">
                            <div className="text-sm font-bold" style={{ color: phase.color }}>{p.sources ?? 0}</div>
                            <div className="text-[8px] text-muted-foreground mt-0.5">Sources</div>
                          </div>
                          <div className="rounded-lg bg-foreground/5/50 px-2 py-2 text-center">
                            <div className="text-sm font-bold" style={{ color: phase.color }}>{p.searches ?? 0}</div>
                            <div className="text-[8px] text-muted-foreground mt-0.5">Searches</div>
                          </div>
                          <div className="rounded-lg bg-foreground/5/50 px-2 py-2 text-center">
                            <div className="text-sm font-bold" style={{ color: phase.color }}>{p.scrapes ?? 0}</div>
                            <div className="text-[8px] text-muted-foreground mt-0.5">Scraped</div>
                          </div>
                        </div>
                      </>
                    )}

                    {/* ── Synthesize detail ───────────────── */}
                    {phase.key === "synthesize" && (
                      <>
                        <p className="text-[10px] text-muted-foreground mb-2.5">
                          Cross-referenced findings across sections, identified causal chains, resolved contradictions, and generated insights.
                        </p>
                        <div className="grid grid-cols-4 gap-2">
                          <div className="rounded-lg bg-foreground/5/50 px-2 py-2 text-center">
                            <div className="text-sm font-bold" style={{ color: phase.color }}>{p.cross_links ?? 0}</div>
                            <div className="text-[8px] text-muted-foreground mt-0.5">Cross-Links</div>
                          </div>
                          <div className="rounded-lg bg-foreground/5/50 px-2 py-2 text-center">
                            <div className="text-sm font-bold" style={{ color: phase.color }}>{p.insights ?? insightsGenerated}</div>
                            <div className="text-[8px] text-muted-foreground mt-0.5">Insights</div>
                          </div>
                          <div className="rounded-lg bg-foreground/5/50 px-2 py-2 text-center">
                            <div className="text-sm font-bold text-rose-500">{p.risks ?? contrarianRisks}</div>
                            <div className="text-[8px] text-muted-foreground mt-0.5">Risks</div>
                          </div>
                          <div className="rounded-lg bg-foreground/5/50 px-2 py-2 text-center">
                            <div className="text-sm font-bold text-amber-500">{p.gaps ?? 0}</div>
                            <div className="text-[8px] text-muted-foreground mt-0.5">Gaps</div>
                          </div>
                        </div>
                      </>
                    )}

                    {/* ── Compose detail ──────────────────── */}
                    {phase.key === "compose" && (
                      <>
                        <p className="text-[10px] text-muted-foreground mb-2.5">
                          Wrote the definitive report with all structured evidence woven in, cross-section connections as transitions.
                        </p>
                        <div className="rounded-lg bg-foreground/5/50 px-3 py-2.5 text-center">
                          <div className="text-lg font-bold" style={{ color: phase.color }}>{p.words ?? 0}</div>
                          <div className="text-[8px] text-muted-foreground mt-0.5">Words Written</div>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── DimensionBreakdown ───────────────────────────────────────────────────────

function DimensionBreakdown({ evaluation, color }: { evaluation: LayerEvaluation; color: string }) {
  const entries = Object.entries(evaluation.scores ?? {}).filter(
    ([, v]) => typeof v === "object" && v !== null && "score" in v
  ) as [string, { score: number; justification: string }][];

  if (entries.length === 0) return null;

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <Target className="h-3 w-3" style={{ color }} />
        <span className="text-[10px] font-semibold uppercase tracking-widest" style={{ color }}>
          Quality Dimensions
        </span>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2.5">
        {entries.map(([key, val], i) => (
          <div key={key} title={val.justification}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] text-muted-foreground truncate pr-2">
                {DIMENSION_LABELS[key] ?? key}
              </span>
              <span className="text-[10px] font-bold shrink-0" style={{ color }}>
                {val.score.toFixed(1)}/10
              </span>
            </div>
            <FillBar pct={(val.score / 10) * 100} color={color} delay={i * 80} />
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── MissionCard ──────────────────────────────────────────────────────────────

function MissionCard({ layer, evaluation }: { layer: LayerResult; evaluation?: LayerEvaluation }) {
  const [dimOpen, setDimOpen] = useState(false);
  const key = layer.layer as LayerKey;
  const cfg = LAYER_CFG[key] ?? LAYER_CFG[1];
  const Icon = cfg.Icon;
  const meta = parseMeta(layer);

  const isBaseline = meta.method === "single_prompt" || (meta.toolCalls === 0 && !["enhanced_search", "cmi_expert"].includes(meta.method));
  const isCmi = meta.method === "cmi_expert";

  const postscore = evaluation
    ? Object.values(evaluation.scores ?? {})
        .map((s) => (typeof s === "object" && s !== null ? (s as { score: number }).score : 0))
        .filter((v) => v > 0)
        .reduce((a, b, _, arr) => a + b / arr.length, 0)
    : 0;

  return (
    <div
      className="relative rounded-2xl overflow-hidden border transition-shadow hover:shadow-xl"
      style={{
        borderColor: cfg.border,
        background: cfg.bg,
        boxShadow: `0 2px 16px ${cfg.glow}`,
      }}
    >
      <div
        className="absolute left-0 inset-y-0 w-0.75 rounded-l-full"
        style={{ background: cfg.color }}
      />

      <div className="pl-5 pr-4 pt-4 pb-4">
        {/* ── Header ─────────────────────────────────────────────── */}
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex items-start gap-3 min-w-0">
            <div
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border"
              style={{ background: cfg.bg, borderColor: cfg.border }}
            >
              <Icon className="h-4.5 w-4.5" style={{ color: cfg.color }} />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-bold text-foreground mb-0.5">
                {LAYER_NAMES[layer.layer] ?? `Layer ${layer.layer + 1}`}
              </div>
              <p className="text-[11px] text-muted-foreground leading-snug">{cfg.description}</p>
              <div className="flex flex-wrap items-center gap-3 mt-2 text-[10px] text-muted-foreground">
                <span className="flex items-center gap-1">
                  <FileText className="h-2.5 w-2.5" />
                  {layer.word_count.toLocaleString()} words
                </span>
                <span className="flex items-center gap-1">
                  <Globe className="h-2.5 w-2.5" />
                  {layer.source_count} sources
                </span>
                <span className="flex items-center gap-1">
                  <Clock className="h-2.5 w-2.5" />
                  {layer.elapsed_seconds.toFixed(1)}s
                </span>
                {meta.toolCalls > 0 && (
                  <span className="flex items-center gap-1">
                    <Activity className="h-2.5 w-2.5" />
                    {meta.toolCalls} tool calls
                  </span>
                )}
                {meta.verifications > 0 && (
                  <span className="flex items-center gap-1">
                    <CheckCircle2 className="h-2.5 w-2.5" />
                    {meta.verifications} verified
                  </span>
                )}
                {meta.assumptionChallenges > 0 && (
                  <span className="flex items-center gap-1 font-semibold" style={{ color: "#E11D48" }}>
                    <AlertTriangle className="h-2.5 w-2.5" />
                    {meta.assumptionChallenges} challenged
                  </span>
                )}
                {meta.bearCasesSearched > 0 && (
                  <span className="flex items-center gap-1" style={{ color: "#E11D48" }}>
                    <TrendingDown className="h-2.5 w-2.5" />
                    {meta.bearCasesSearched} bear cases
                  </span>
                )}
                {meta.crossIndustrySearches > 0 && (
                  <span className="flex items-center gap-1" style={{ color: "#E11D48" }}>
                    <Shuffle className="h-2.5 w-2.5" />
                    {meta.crossIndustrySearches} cross-industry
                  </span>
                )}
              </div>
            </div>
          </div>

          {postscore > 0 && (
            <div className="shrink-0 text-right">
              <div className="text-3xl font-extrabold leading-none" style={{ color: cfg.color }}>
                {postscore.toFixed(1)}
              </div>
              <div className="text-[10px] text-muted-foreground">/10</div>
            </div>
          )}
        </div>

        {/* ── Baseline note ───────────────────────────────────────── */}
        {isBaseline && !isCmi && (
          <div className="mb-3 rounded-xl bg-foreground/5/60 border border-foreground/10 px-3 py-2.5 text-[11px] text-muted-foreground">
            No tools used — raw LLM answer with zero external research.
            Establishes a quality floor that all subsequent agents must beat.
          </div>
        )}

        {/* ── CMI Pipeline Flow (dedicated 5-phase visualization) ─── */}
        {isCmi && meta.phaseDetails.length > 0 && (
          <div className="mb-4 rounded-xl bg-white/3 border border-foreground/10 p-3">
            <CmiPipelineFlow
              phaseDetails={meta.phaseDetails}
              planSections={meta.planSections}
              planQuestions={meta.planQuestions}
              factsCollected={meta.factsCollected}
              insightsGenerated={meta.insightsGenerated}
              contrarianRisks={meta.contrarianRisks}
              color={cfg.color}
            />
          </div>
        )}

        {/* ── ReAct Loop Flow (for Enhanced layer) ─────────────────── */}
        {!isBaseline && !isCmi && meta.iterHistory.length > 0 && (
          <div className="mb-4 rounded-xl bg-white/3 border border-foreground/10 p-3">
            <ReactLoopFlow
              iterHistory={meta.iterHistory}
              color={cfg.color}
              chipBg={cfg.chipBg}
              layer={layer.layer}
            />
          </div>
        )}

        {/* ── Quality Dimensions toggle ────────────────────────────── */}
        {evaluation && (
          <div>
            <button
              onClick={() => setDimOpen(!dimOpen)}
              className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
            >
              <Target className="h-2.5 w-2.5" />
              Quality Dimensions
              {dimOpen ? <ChevronUp className="h-2.5 w-2.5 ml-0.5" /> : <ChevronDown className="h-2.5 w-2.5 ml-0.5" />}
            </button>

            {dimOpen && (
              <div className="mt-3 animate-fade-in-up rounded-xl bg-white/3 border border-foreground/10 p-3">
                <DimensionBreakdown evaluation={evaluation} color={cfg.color} />
              </div>
            )}
          </div>
        )}

        {/* Baseline: show dimensions inline */}
        {isBaseline && evaluation && (
          <DimensionBreakdown evaluation={evaluation} color={cfg.color} />
        )}
      </div>
    </div>
  );
}

// ─── ImprovementCard ─────────────────────────────────────────────────────────

function ImprovementCard({ comparison }: { comparison: LayerComparisonData }) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const fromKey = comparison.from_layer as LayerKey;
  const toKey = comparison.to_layer as LayerKey;
  const fromCfg = LAYER_CFG[fromKey] ?? LAYER_CFG[0];
  const toCfg = LAYER_CFG[toKey] ?? LAYER_CFG[1];
  const fromName = LAYER_NAMES[comparison.from_layer] ?? `Layer ${comparison.from_layer}`;
  const toName = LAYER_NAMES[comparison.to_layer] ?? `Layer ${comparison.to_layer}`;
  const deltaPositive = comparison.score_delta > 0;

  return (
    <div
      className="relative rounded-2xl overflow-hidden border transition-shadow hover:shadow-xl"
      style={{
        borderColor: toCfg.border,
        background: toCfg.bg,
        boxShadow: `0 2px 16px ${toCfg.glow}`,
      }}
    >
      <div
        className="absolute left-0 inset-y-0 w-0.75 rounded-l-full"
        style={{ background: `linear-gradient(to bottom, ${fromCfg.color}, ${toCfg.color})` }}
      />

      {/* Header */}
      <div className="px-5 pt-4 pb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-bold"
            style={{ background: fromCfg.chipBg, color: fromCfg.color }}
          >
            L{comparison.from_layer}
          </span>
          <ArrowRight size={14} className="text-muted-foreground" />
          <span
            className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-bold"
            style={{ background: toCfg.chipBg, color: toCfg.color }}
          >
            L{comparison.to_layer}
          </span>
          <span className="text-sm font-semibold text-foreground ml-1">
            {fromName} → {toName}
          </span>
        </div>
        {comparison.score_delta !== 0 && (
          <span
            className={cn(
              "text-xs font-bold px-2 py-0.5 rounded-full",
              deltaPositive
                ? "bg-emerald-500/10 text-emerald-400"
                : "bg-red-500/10 text-red-400"
            )}
          >
            {deltaPositive ? "+" : ""}{comparison.score_delta.toFixed(1)} avg
          </span>
        )}
      </div>

      {/* Verdict */}
      {comparison.overall_verdict && (
        <div className="px-5 pb-3">
          <p className="text-xs text-muted-foreground italic">{comparison.overall_verdict}</p>
        </div>
      )}

      {/* Improvements */}
      <div className="px-5 pb-3">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-2">
          Key Improvements
        </p>
        <div className="space-y-2">
          {comparison.improvements.map((imp, i) => (
            <div key={i} className="flex gap-2.5 items-start">
              <span
                className="mt-0.5 shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold"
                style={{ background: toCfg.chipBg, color: toCfg.color }}
              >
                {i + 1}
              </span>
              <p className="text-xs text-foreground leading-relaxed">{imp}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Key Evidence (collapsible) */}
      {comparison.key_evidence && (
        <div className="px-5 pb-4">
          <button
            onClick={() => setEvidenceOpen(!evidenceOpen)}
            className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground hover:text-primary transition-colors"
          >
            <Lightbulb size={12} />
            Most Striking Evidence
            {evidenceOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
          {evidenceOpen && (
            <div
              className="mt-2 rounded-lg p-3 text-xs text-muted-foreground leading-relaxed border"
              style={{
                background: `${toCfg.color}08`,
                borderColor: `${toCfg.color}20`,
              }}
            >
              {comparison.key_evidence}
            </div>
          )}
        </div>
      )}
    </div>
  );
}


// ─── Main Export ──────────────────────────────────────────────────────────────

interface AgentActivityPanelProps {
  layers: LayerResult[];
  evaluations: LayerEvaluation[];
  summary?: string;
}

export function AgentActivityPanel({ layers, evaluations }: AgentActivityPanelProps) {
  const metas = layers.map(parseMeta);
  const totalToolCalls = metas.reduce((s, m) => s + m.toolCalls, 0);
  const totalSources = layers.reduce((s, l) => s + l.source_count, 0);
  const totalElapsed = layers.reduce((s, l) => s + l.elapsed_seconds, 0);
  const totalQueries = metas.reduce(
    (s, m) => s + m.iterHistory.flatMap((h) => h.queries ?? []).length,
    0
  );

  return (
    <div className="space-y-4">
      <PipelineOverview
        layers={layers}
        evaluations={evaluations}
        totalToolCalls={totalToolCalls}
        totalSources={totalSources}
        totalElapsed={totalElapsed}
        totalQueries={totalQueries}
      />

      <Divider label="Agent Missions" />

      <div className="space-y-3">
        {layers.map((layer) => (
          <MissionCard
            key={layer.layer}
            layer={layer}
            evaluation={evaluations.find((e) => e.layer === layer.layer)}
          />
        ))}
      </div>

    </div>
  );
}

// ─── LayerComparison ─────────────────────────────────────────────────────────
// Content-level comparison: extract matching sections from each layer's report
// and show the actual text side-by-side so you can see how quality improves.

interface ParsedSection {
  heading: string;
  body: string;
  wordCount: number;
}

/** Parse markdown into sections split on ## headings */
function parseSections(markdown: string): ParsedSection[] {
  const sections: ParsedSection[] = [];
  const lines = markdown.split("\n");
  let currentHeading = "";
  let currentBody: string[] = [];

  for (const line of lines) {
    const h2Match = line.match(/^##\s+(.+)/);
    if (h2Match) {
      if (currentHeading) {
        const body = currentBody.join("\n").trim();
        sections.push({ heading: currentHeading, body, wordCount: body.split(/\s+/).filter(Boolean).length });
      }
      currentHeading = h2Match[1].trim();
      currentBody = [];
    } else if (currentHeading) {
      currentBody.push(line);
    }
  }
  if (currentHeading) {
    const body = currentBody.join("\n").trim();
    sections.push({ heading: currentHeading, body, wordCount: body.split(/\s+/).filter(Boolean).length });
  }
  return sections;
}

/** Fuzzy match section headings across layers */
function normalizeHeading(h: string): string {
  return h.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function findMatchingSections(allLayerSections: ParsedSection[][]) {
  // Use the layer with most sections as the reference (usually CMI expert)
  const refIdx = allLayerSections.reduce((best, cur, i) =>
    cur.length > allLayerSections[best].length ? i : best, 0);
  const refSections = allLayerSections[refIdx];

  const matched: { heading: string; perLayer: (ParsedSection | null)[] }[] = [];

  for (const refSec of refSections) {
    const norm = normalizeHeading(refSec.heading);
    const perLayer = allLayerSections.map((layerSections) => {
      // Exact normalized match first
      const exact = layerSections.find((s) => normalizeHeading(s.heading) === norm);
      if (exact) return exact;
      // Substring match: either heading contains the other
      const partial = layerSections.find((s) => {
        const sNorm = normalizeHeading(s.heading);
        return sNorm.includes(norm) || norm.includes(sNorm);
      });
      return partial ?? null;
    });
    // Only include if at least 2 layers have this section
    const matchCount = perLayer.filter(Boolean).length;
    if (matchCount >= 2) {
      matched.push({ heading: refSec.heading, perLayer });
    }
  }

  return matched;
}

/** Count specific data points in text: numbers, percentages, dollar values */
function countDataPoints(text: string): number {
  const patterns = [
    /\$[\d,.]+[BMK]?/g,           // Dollar amounts
    /\d+(\.\d+)?%/g,              // Percentages
    /\d{4,}/g,                     // Years or large numbers
    /\d+(\.\d+)?\s*(billion|million|thousand|CAGR|USD|EUR)/gi, // Financial figures
  ];
  const found = new Set<string>();
  for (const pat of patterns) {
    const matches = text.match(pat);
    if (matches) matches.forEach((m) => found.add(m));
  }
  return found.size;
}

export function LayerComparison({
  layers,
  layerComparisons,
}: {
  layers: LayerResult[];
  evaluations: LayerEvaluation[];
  layerComparisons?: LayerComparisonData[];
}) {
  const sortedLayers = [...layers].sort((a, b) => a.layer - b.layer);
  const [leftIdx, setLeftIdx] = useState(0);
  const [rightIdx, setRightIdx] = useState(Math.min(sortedLayers.length - 1, 2));
  const [selectedSection, setSelectedSection] = useState(0);

  if (layers.length < 2) return null;

  const leftLayer = sortedLayers[leftIdx];
  const rightLayer = sortedLayers[rightIdx];

  const allSections = sortedLayers.map((l) => parseSections(l.content));
  const matched = findMatchingSections(allSections);

  if (matched.length === 0) return null;

  const currentMatch = matched[selectedSection];
  const leftSection = currentMatch.perLayer[leftIdx];
  const rightSection = currentMatch.perLayer[rightIdx];

  const leftWords = leftSection?.wordCount ?? 0;
  const rightWords = rightSection?.wordCount ?? 0;
  const leftData = leftSection ? countDataPoints(leftSection.body) : 0;
  const rightData = rightSection ? countDataPoints(rightSection.body) : 0;
  const wordDelta = rightWords - leftWords;
  const dataDelta = rightData - leftData;

  function renderColumn(layer: LayerResult, section: ParsedSection | null) {
    const cfg = LAYER_CFG[layer.layer as LayerKey] ?? LAYER_CFG[0];
    const words = section?.wordCount ?? 0;
    const data = section ? countDataPoints(section.body) : 0;

    return (
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Column header */}
        <div
          className="rounded-t-xl border-b px-3.5 py-3 flex items-center gap-2.5"
          style={{ borderColor: `${cfg.color}25`, background: `${cfg.color}08` }}
        >
          <div
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border"
            style={{ borderColor: cfg.color, background: `${cfg.color}18` }}
          >
            <cfg.Icon className="h-3 w-3" style={{ color: cfg.color }} />
          </div>
          <div className="min-w-0">
            <div className="text-[11px] font-bold" style={{ color: cfg.color }}>
              {LAYER_NAMES[layer.layer]}
            </div>
            {section && (
              <div className="flex items-center gap-2 text-[9px] text-muted-foreground">
                <span>{words} words</span>
                <span className="text-muted-foreground/30">|</span>
                <span>{data} data pts</span>
              </div>
            )}
          </div>
        </div>

        {/* Content */}
        <div
          className="flex-1 rounded-b-xl border border-t-0 overflow-hidden"
          style={{ borderColor: `${cfg.color}15`, background: `${cfg.color}04` }}
        >
          {section ? (
            <div
              className="p-3.5 text-[11px] text-foreground/70 leading-relaxed whitespace-pre-line overflow-y-auto
                [&_h3]:text-[11px] [&_h3]:font-bold [&_h3]:text-foreground/80 [&_h3]:mt-3 [&_h3]:mb-1
                [&_strong]:text-foreground/80 [&_strong]:font-semibold"
              style={{
                maxHeight: 600,
                scrollbarWidth: "thin",
                scrollbarColor: `${cfg.color}40 transparent`,
              }}
            >
              {section.body}
            </div>
          ) : (
            <div className="p-4 flex items-center justify-center h-32">
              <span className="text-[10px] text-muted-foreground/30 italic">
                Section not covered by this layer
              </span>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* ── Layer Improvement Analysis ───────────────────────────── */}
      {layerComparisons && layerComparisons.length > 0 && (
        <>
          <Divider label="Layer Improvement Analysis" />
          <div className="space-y-3">
            {layerComparisons.map((lc) => (
              <ImprovementCard key={`${lc.from_layer}-${lc.to_layer}`} comparison={lc} />
            ))}
          </div>
        </>
      )}

      {/* ── Claim Transformations (Evidence Cards) ────────────── */}
      {layerComparisons && layerComparisons.some((lc) => lc.claim_pairs && lc.claim_pairs.length > 0) && (
        <>
          <Divider label="Claim Transformations" />
          {layerComparisons
            .filter((lc) => lc.claim_pairs && lc.claim_pairs.length > 0)
            .map((lc) => (
              <div key={`evidence-${lc.from_layer}-${lc.to_layer}`} className="glass-card p-5">
                <EvidenceCards
                  pairs={lc.claim_pairs!}
                  fromLayer={lc.from_layer}
                  toLayer={lc.to_layer}
                />
              </div>
            ))}
        </>
      )}

      {/* ── Layer Selector ──────────────────────────────────────── */}
      <div className="glass-card p-4">
        <div className="flex items-center gap-2 mb-3">
          <BarChart3 className="h-4 w-4 text-cyan-400" />
          <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Compare Two Layers Side by Side
          </span>
        </div>

        <div className="flex items-center gap-3">
          {/* Left picker */}
          <div className="flex-1">
            <div className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">Left</div>
            <div className="flex gap-1.5">
              {sortedLayers.map((l, i) => {
                const cfg = LAYER_CFG[l.layer as LayerKey] ?? LAYER_CFG[0];
                const isActive = i === leftIdx;
                return (
                  <button
                    key={l.layer}
                    onClick={() => { if (i !== rightIdx) setLeftIdx(i); }}
                    disabled={i === rightIdx}
                    className={cn(
                      "flex-1 rounded-lg px-2 py-2 text-[10px] font-semibold transition-all border text-center",
                      isActive
                        ? "text-white shadow-md"
                        : i === rightIdx
                          ? "border-foreground/10 bg-foreground/5/30 text-muted-foreground/30 cursor-not-allowed"
                          : "border-foreground/10 bg-foreground/5/50 text-muted-foreground hover:text-foreground"
                    )}
                    style={isActive ? { background: cfg.color, borderColor: cfg.color } : undefined}
                  >
                    {LAYER_NAMES[l.layer]}
                  </button>
                );
              })}
            </div>
          </div>

          {/* VS badge */}
          <div className="flex flex-col items-center pt-4">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-foreground/10 text-[10px] font-bold text-muted-foreground">
              VS
            </div>
          </div>

          {/* Right picker */}
          <div className="flex-1">
            <div className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">Right</div>
            <div className="flex gap-1.5">
              {sortedLayers.map((l, i) => {
                const cfg = LAYER_CFG[l.layer as LayerKey] ?? LAYER_CFG[0];
                const isActive = i === rightIdx;
                return (
                  <button
                    key={l.layer}
                    onClick={() => { if (i !== leftIdx) setRightIdx(i); }}
                    disabled={i === leftIdx}
                    className={cn(
                      "flex-1 rounded-lg px-2 py-2 text-[10px] font-semibold transition-all border text-center",
                      isActive
                        ? "text-white shadow-md"
                        : i === leftIdx
                          ? "border-foreground/10 bg-foreground/5/30 text-muted-foreground/30 cursor-not-allowed"
                          : "border-foreground/10 bg-foreground/5/50 text-muted-foreground hover:text-foreground"
                    )}
                    style={isActive ? { background: cfg.color, borderColor: cfg.color } : undefined}
                  >
                    {LAYER_NAMES[l.layer]}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* ── Section Picker ─────────────────────────────────────── */}
      <div className="glass-card p-4">
        <div className="flex items-center gap-2 mb-2.5">
          <BookOpen className="h-3.5 w-3.5 text-cyan-400" />
          <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
            Section
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {matched.map((m, i) => {
            const isActive = i === selectedSection;
            const hasLeft = m.perLayer[leftIdx] !== null;
            const hasRight = m.perLayer[rightIdx] !== null;
            return (
              <button
                key={i}
                onClick={() => setSelectedSection(i)}
                className={cn(
                  "rounded-lg px-2.5 py-1.5 text-[10px] font-medium transition-all border",
                  isActive
                    ? "border-cyan-500/40 bg-cyan-500/10 text-cyan-300"
                    : "border-foreground/10 bg-foreground/5/50 text-muted-foreground hover:text-foreground hover:border-foreground/10"
                )}
              >
                {m.heading}
                {(!hasLeft || !hasRight) && (
                  <span className="ml-1 text-[8px] opacity-40">partial</span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Delta Bar ──────────────────────────────────────────── */}
      {leftSection && rightSection && (
        <div className="glass-card px-4 py-2.5 flex items-center justify-center gap-6">
          <span className="text-[9px] text-muted-foreground uppercase tracking-wider font-semibold">
            Difference
          </span>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              <FileText className="h-3 w-3 text-muted-foreground/50" />
              <span
                className="text-[10px] font-bold"
                style={{ color: wordDelta > 0 ? "#059669" : wordDelta < 0 ? "#EF4444" : "#6B7280" }}
              >
                {wordDelta > 0 ? "+" : ""}{wordDelta} words
              </span>
            </div>
            <div className="w-px h-3 bg-foreground/10" />
            <div className="flex items-center gap-1.5">
              <Target className="h-3 w-3 text-muted-foreground/50" />
              <span
                className="text-[10px] font-bold"
                style={{ color: dataDelta > 0 ? "#059669" : dataDelta < 0 ? "#EF4444" : "#6B7280" }}
              >
                {dataDelta > 0 ? "+" : ""}{dataDelta} data points
              </span>
            </div>
          </div>
        </div>
      )}

      {/* ── Side by Side Columns ───────────────────────────────── */}
      <div className="flex gap-3">
        {renderColumn(leftLayer, leftSection)}
        {renderColumn(rightLayer, rightSection)}
      </div>
    </div>
  );
}

function Divider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 px-1">
      <div className="h-px flex-1 bg-foreground/10" />
      <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground shrink-0">
        {label}
      </span>
      <div className="h-px flex-1 bg-foreground/10" />
    </div>
  );
}
