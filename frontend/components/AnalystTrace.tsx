"use client";

import { useState, useMemo } from "react";
import {
  Puzzle,
  Brain,
  Search,
  FileDown,
  FlipHorizontal,
  Scale,
  ShieldCheck,
  PenTool,
  ChevronDown,
  ChevronRight,
  Check,
  X,
  AlertTriangle,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  AnalystTrace,
  TraceStep,
  DecomposeContent,
  ThinkContent,
  SearchContent,
  ScrapeContent,
  ReflectContent,
  AnalyzeContent,
  QualityContent,
  ComposeContent,
} from "@/lib/types";

/* ── Phase config ──────────────────────────────────────────── */

const PHASE_CONFIG: Record<
  string,
  { icon: typeof Brain; label: string; color: string; bg: string; border: string }
> = {
  decompose: { icon: Puzzle, label: "Problem Decomposition", color: "text-indigo-400", bg: "bg-indigo-500/10", border: "border-indigo-500/20" },
  think:     { icon: Brain, label: "Hypothesis Formation", color: "text-purple-400", bg: "bg-purple-500/10", border: "border-purple-500/20" },
  search:    { icon: Search, label: "Web Search", color: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/20" },
  scrape:    { icon: FileDown, label: "Source Extraction", color: "text-slate-400", bg: "bg-slate-500/10", border: "border-slate-500/20" },
  reflect:   { icon: FlipHorizontal, label: "Evidence Evaluation", color: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/20" },
  analyze:   { icon: Scale, label: "Cross-Reference Analysis", color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20" },
  quality:   { icon: ShieldCheck, label: "Quality Gate", color: "text-green-400", bg: "bg-green-500/10", border: "border-green-500/20" },
  compose:   { icon: PenTool, label: "Report Composition", color: "text-foreground/70", bg: "bg-foreground/5", border: "border-foreground/10" },
};

const TIER_STYLES: Record<number, { label: string; cls: string }> = {
  1: { label: "T1", cls: "bg-amber-500/20 text-amber-300 border-amber-500/30" },
  2: { label: "T2", cls: "bg-blue-500/20 text-blue-300 border-blue-500/30" },
  3: { label: "T3", cls: "bg-foreground/10 text-muted-foreground border-foreground/10" },
};

const PRIORITY_STYLES: Record<number, { label: string; cls: string }> = {
  1: { label: "P1 Blocking", cls: "bg-red-500/15 text-red-400 border-red-500/25" },
  2: { label: "P2 Important", cls: "bg-amber-500/15 text-amber-400 border-amber-500/25" },
  3: { label: "P3 Enrichment", cls: "bg-foreground/8 text-muted-foreground border-foreground/10" },
};

/* ── Helpers ───────────────────────────────────────────────── */

function TierBadge({ tier }: { tier: number }) {
  const style = TIER_STYLES[tier] ?? TIER_STYLES[3];
  return (
    <span className={cn("inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono rounded border", style.cls)}>
      {style.label}
    </span>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 70 ? "bg-emerald-500" : pct >= 40 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-foreground/10 overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono text-muted-foreground">{pct}%</span>
    </div>
  );
}

function PhaseIcon({ phase, size = "sm" }: { phase: string; size?: "sm" | "md" }) {
  const config = PHASE_CONFIG[phase] ?? PHASE_CONFIG.compose;
  const Icon = config.icon;
  const s = size === "md" ? "w-8 h-8" : "w-6 h-6";
  const iconS = size === "md" ? "h-4 w-4" : "h-3.5 w-3.5";
  return (
    <div className={cn("rounded-lg flex items-center justify-center shrink-0", s, config.bg)}>
      <Icon className={cn(iconS, config.color)} />
    </div>
  );
}

/* ── Sub-components ────────────────────────────────────────── */

function DecomposeCard({ content }: { content: DecomposeContent }) {
  return (
    <div className="space-y-4">
      <div className="p-4 rounded-xl bg-indigo-500/5 border border-indigo-500/10">
        <div className="text-xs uppercase tracking-wider text-indigo-400/70 mb-1.5 font-mono">Core Question</div>
        <p className="text-sm text-foreground/90">{content.core_question}</p>
      </div>

      {content.assumptions?.length > 0 && (
        <div>
          <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2 font-mono">Assumptions</div>
          <ul className="space-y-1">
            {content.assumptions.map((a, i) => (
              <li key={i} className="text-xs text-muted-foreground flex gap-2">
                <span className="text-indigo-400/50 shrink-0">-</span> {a}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <div className="text-xs uppercase tracking-wider text-muted-foreground mb-3 font-mono">
          Research Questions ({content.sub_questions?.length ?? 0})
        </div>
        <div className="grid grid-cols-1 gap-2">
          {content.sub_questions?.map((sq) => {
            const pStyle = PRIORITY_STYLES[sq.priority] ?? PRIORITY_STYLES[2];
            return (
              <div key={sq.id} className="p-3 rounded-lg bg-foreground/2 border border-foreground/5 space-y-1.5">
                <div className="flex items-start gap-2">
                  <span className={cn("inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono rounded border shrink-0 mt-0.5", pStyle.cls)}>
                    {pStyle.label}
                  </span>
                  <span className="text-sm text-foreground/80">{sq.question}</span>
                </div>
                <div className="flex flex-wrap gap-1.5 pl-0.5">
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-foreground/5 text-muted-foreground font-mono">{sq.answer_type}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-foreground/5 text-muted-foreground font-mono">{sq.research_strategy}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function ThinkCard({ content }: { content: ThinkContent }) {
  return (
    <div className="space-y-3">
      <blockquote className="p-3 rounded-lg bg-purple-500/5 border-l-2 border-purple-500/40">
        <div className="text-[10px] uppercase tracking-wider text-purple-400/60 mb-1 font-mono">Hypothesis</div>
        <p className="text-sm italic text-foreground/80">&ldquo;{content.hypothesis}&rdquo;</p>
      </blockquote>

      {content.would_change_mind && (
        <div className="p-3 rounded-lg bg-amber-500/5 border-l-2 border-amber-500/30">
          <div className="text-[10px] uppercase tracking-wider text-amber-400/60 mb-1 font-mono">Would Change Mind If</div>
          <p className="text-xs text-muted-foreground italic">&ldquo;{content.would_change_mind}&rdquo;</p>
        </div>
      )}

      {content.search_queries?.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1.5 font-mono">Planned Searches</div>
          <div className="flex flex-wrap gap-1.5">
            {content.search_queries.map((q, i) => (
              <code key={i} className="text-[11px] px-2 py-0.5 rounded bg-foreground/5 text-muted-foreground">{q}</code>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SearchCard({ content }: { content: SearchContent }) {
  return (
    <div className="space-y-2">
      <code className="text-xs text-blue-400/80 bg-blue-500/5 px-2 py-1 rounded block">{content.query}</code>
      {content.results?.length > 0 && (
        <div className="space-y-1.5">
          {content.results.map((r, i) => (
            <div key={i} className="flex items-start gap-2 text-xs">
              <TierBadge tier={r.tier} />
              <div className="min-w-0">
                <div className="text-foreground/70 truncate">{r.title}</div>
                {r.snippet && <div className="text-muted-foreground/60 line-clamp-1 mt-0.5">{r.snippet}</div>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ScrapeCard({ content }: { content: ScrapeContent }) {
  return (
    <div className="flex items-start gap-2">
      {content.success ? (
        <Check className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" />
      ) : (
        <X className="h-3.5 w-3.5 text-red-400 shrink-0 mt-0.5" />
      )}
      <div className="min-w-0 space-y-1">
        <div className="text-xs text-foreground/70 flex items-center gap-2">
          <span className="truncate">{content.url}</span>
          <a href={content.url} target="_blank" rel="noopener noreferrer" className="shrink-0 text-muted-foreground hover:text-foreground transition-colors">
            <ExternalLink className="h-3 w-3" />
          </a>
        </div>
        {content.success && (
          <div className="text-[10px] text-muted-foreground font-mono">
            {content.content_length?.toLocaleString()} chars via {content.method}
          </div>
        )}
        {content.content_preview && (
          <div className="text-[11px] text-muted-foreground/60 line-clamp-2 italic">
            {content.content_preview}
          </div>
        )}
      </div>
    </div>
  );
}

function ReflectCard({ content }: { content: ReflectContent }) {
  return (
    <div className="space-y-3">
      {content.findings?.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2 font-mono">Findings</div>
          <div className="space-y-2">
            {content.findings.map((f, i) => (
              <div key={i} className="flex items-start gap-2 text-xs">
                {f.confirms_hypothesis ? (
                  <Check className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" />
                ) : (
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0 mt-0.5" />
                )}
                <div className="min-w-0">
                  <div className="text-foreground/80">{f.data_point}</div>
                  <div className="flex items-center gap-2 mt-0.5 text-muted-foreground/60">
                    <TierBadge tier={f.source_tier} />
                    <span>{f.source_title}</span>
                    <span className="font-mono">{Math.round(f.confidence * 100)}%</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {content.contradictions?.length > 0 && (
        <div className="p-2.5 rounded-lg bg-red-500/5 border border-red-500/10">
          <div className="text-[10px] uppercase tracking-wider text-red-400/60 mb-1 font-mono">Contradictions</div>
          {content.contradictions.map((c, i) => (
            <div key={i} className="text-xs text-red-300/70">{c}</div>
          ))}
        </div>
      )}

      {content.answer && (
        <div className="p-3 rounded-lg bg-foreground/2 border border-foreground/5">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1 font-mono">Answer</div>
          <p className="text-sm text-foreground/80 mb-2">{content.answer}</p>
          <ConfidenceBar value={content.confidence} />
          {content.hypothesis_revised && content.revised_hypothesis && (
            <div className="mt-2 p-2 rounded bg-amber-500/5 border border-amber-500/10">
              <span className="text-[10px] text-amber-400 font-mono">HYPOTHESIS REVISED: </span>
              <span className="text-xs text-muted-foreground italic">{content.revised_hypothesis}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function AnalyzeCard({ content }: { content: AnalyzeContent }) {
  return (
    <div className="space-y-4">
      {content.key_findings?.length > 0 && (
        <div>
          <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2 font-mono">Key Findings</div>
          <ol className="space-y-1.5 list-decimal list-inside">
            {content.key_findings.map((f, i) => (
              <li key={i} className="text-sm text-foreground/80">{f}</li>
            ))}
          </ol>
        </div>
      )}

      {content.judgments?.length > 0 && (
        <div>
          <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2 font-mono">Analyst Judgments</div>
          <div className="space-y-2">
            {content.judgments.map((j, i) => {
              const convColor = j.conviction === "high" ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/20"
                : j.conviction === "medium" ? "text-amber-400 bg-amber-500/10 border-amber-500/20"
                : "text-red-400 bg-red-500/10 border-red-500/20";
              return (
                <div key={i} className="p-3 rounded-lg bg-foreground/2 border border-foreground/5">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={cn("text-[10px] font-mono px-1.5 py-0.5 rounded border uppercase", convColor)}>
                      {j.conviction}
                    </span>
                  </div>
                  <p className="text-sm text-foreground/80 mb-1">{j.claim}</p>
                  <p className="text-xs text-muted-foreground italic line-clamp-2">{j.reasoning}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {content.causal_chains?.length > 0 && (
        <div>
          <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2 font-mono">Causal Chains</div>
          {content.causal_chains.map((c, i) => (
            <div key={i} className="text-xs text-foreground/70 mb-1 pl-2 border-l border-emerald-500/20">{c}</div>
          ))}
        </div>
      )}

      {content.narrative_thread && (
        <div className="p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/10">
          <div className="text-[10px] uppercase tracking-wider text-emerald-400/60 mb-1 font-mono">Narrative Thread</div>
          <p className="text-sm text-foreground/80">{content.narrative_thread}</p>
        </div>
      )}
    </div>
  );
}

function QualityGateCard({ content }: { content: QualityContent }) {
  const dimensions = [
    { key: "coverage", label: "Coverage", value: content.coverage },
    { key: "evidence_strength", label: "Evidence Strength", value: content.evidence_strength },
    { key: "evidence_depth", label: "Evidence Depth", value: content.evidence_depth ?? 0 },
    { key: "contradiction_resolution", label: "Contradiction Resolution", value: content.contradiction_resolution },
    { key: "judgment_formation", label: "Judgment Formation", value: content.judgment_formation },
    { key: "gap_acknowledgment", label: "Gap Acknowledgment", value: content.gap_acknowledgment },
  ];

  return (
    <div className="space-y-4">
      <div className={cn(
        "inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-mono",
        content.passes
          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
          : "bg-red-500/10 text-red-400 border border-red-500/20"
      )}>
        {content.passes ? <Check className="h-4 w-4" /> : <X className="h-4 w-4" />}
        {Math.round(content.overall * 100)}% — {content.passes ? "PASS" : "FAIL"}
      </div>

      <div className="space-y-2">
        {dimensions.map((d) => (
          <div key={d.key} className="space-y-0.5">
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">{d.label}</span>
              <span className="font-mono text-foreground/70">{Math.round(d.value * 100)}%</span>
            </div>
            <ConfidenceBar value={d.value} />
          </div>
        ))}
      </div>

      {content.feedback && (
        <p className="text-xs text-muted-foreground italic">{content.feedback}</p>
      )}
    </div>
  );
}

function ComposeCard({ content }: { content: ComposeContent }) {
  return (
    <div className="space-y-2">
      <div className="text-2xl font-display tracking-tight text-foreground/80">
        {content.word_count?.toLocaleString()} <span className="text-sm text-muted-foreground">words</span>
      </div>
      {(content.sections?.length ?? 0) > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {content.sections!.map((s, i) => (
            <span key={i} className="text-[10px] px-2 py-0.5 rounded bg-foreground/5 text-muted-foreground">{s}</span>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Sub-question group ────────────────────────────────────── */

function SubQuestionGroup({
  sqId,
  question,
  priority,
  steps,
  defaultOpen,
}: {
  sqId: string;
  question: string;
  priority: number;
  steps: TraceStep[];
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const pStyle = PRIORITY_STYLES[priority] ?? PRIORITY_STYLES[2];

  return (
    <div className="border border-foreground/5 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full p-4 flex items-center gap-3 text-left hover:bg-foreground/2 transition-colors"
      >
        {open ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
        )}
        <span className={cn("inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono rounded border shrink-0", pStyle.cls)}>
          {pStyle.label}
        </span>
        <span className="text-sm text-foreground/80 truncate">{question}</span>
        <span className="text-[10px] font-mono text-muted-foreground shrink-0 ml-auto">
          {steps.length} steps
        </span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3">
          {steps.map((step, i) => (
            <StepCard key={i} step={step} compact />
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Step card (renders any phase) ─────────────────────────── */

function StepCard({ step, compact = false }: { step: TraceStep; compact?: boolean }) {
  const config = PHASE_CONFIG[step.phase] ?? PHASE_CONFIG.compose;
  const c = step.content as Record<string, unknown>;

  return (
    <div className={cn(
      "rounded-xl border transition-colors",
      config.border,
      compact ? "p-3" : "p-4"
    )}>
      <div className="flex items-center gap-2 mb-2">
        <PhaseIcon phase={step.phase} size={compact ? "sm" : "md"} />
        <div className="min-w-0 flex-1">
          <div className={cn("font-medium truncate", compact ? "text-xs" : "text-sm", config.color)}>
            {config.label}
          </div>
          {step.elapsed_s > 0 && (
            <div className="text-[10px] text-muted-foreground font-mono">{step.elapsed_s.toFixed(1)}s</div>
          )}
        </div>
      </div>

      {step.phase === "decompose" && <DecomposeCard content={c as unknown as DecomposeContent} />}
      {step.phase === "think" && <ThinkCard content={c as unknown as ThinkContent} />}
      {step.phase === "search" && <SearchCard content={c as unknown as SearchContent} />}
      {step.phase === "scrape" && <ScrapeCard content={c as unknown as ScrapeContent} />}
      {step.phase === "reflect" && <ReflectCard content={c as unknown as ReflectContent} />}
      {step.phase === "analyze" && <AnalyzeCard content={c as unknown as AnalyzeContent} />}
      {step.phase === "quality" && <QualityGateCard content={c as unknown as QualityContent} />}
      {step.phase === "compose" && <ComposeCard content={c as unknown as ComposeContent} />}
    </div>
  );
}

/* ── Main component ────────────────────────────────────────── */

export function AnalystTraceTimeline({ trace }: { trace: AnalystTrace }) {
  // Group steps: decompose and global phases are top-level, per-SQ steps are grouped
  const { decomposeStep, sqGroups, globalSteps } = useMemo(() => {
    let decomposeStep: TraceStep | null = null;
    const sqMap = new Map<string, { question: string; priority: number; steps: TraceStep[] }>();
    const globalSteps: TraceStep[] = [];

    for (const step of trace.steps) {
      if (step.phase === "decompose") {
        decomposeStep = step;
        continue;
      }

      if (step.sq_id && ["think", "search", "scrape", "reflect"].includes(step.phase)) {
        if (!sqMap.has(step.sq_id)) {
          const question = (step.content as Record<string, unknown>)?.question as string ?? step.sq_id;
          const priority = (step.content as Record<string, unknown>)?.priority as number ?? 2;
          sqMap.set(step.sq_id, { question, priority, steps: [] });
        }
        sqMap.get(step.sq_id)!.steps.push(step);
      } else {
        globalSteps.push(step);
      }
    }

    return {
      decomposeStep,
      sqGroups: Array.from(sqMap.entries()),
      globalSteps,
    };
  }, [trace.steps]);

  // Stats
  const searchCount = trace.steps.filter((s) => s.phase === "search").length;
  const scrapeCount = trace.steps.filter((s) => s.phase === "scrape").length;
  const reflectCount = trace.steps.filter((s) => s.phase === "reflect").length;
  const qualityStep = trace.steps.find((s) => s.phase === "quality");
  const qualityScore = qualityStep ? Math.round(((qualityStep.content as unknown as QualityContent).overall ?? 0) * 100) : null;

  return (
    <div className="space-y-6">
      {/* Header stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Questions", value: sqGroups.length },
          { label: "Searches", value: searchCount },
          { label: "Scrapes", value: scrapeCount },
          { label: "Quality", value: qualityScore != null ? `${qualityScore}%` : "—" },
        ].map((stat) => (
          <div key={stat.label} className="p-3 rounded-xl bg-foreground/2 border border-foreground/5 text-center">
            <div className="text-xl font-display tracking-tight">{stat.value}</div>
            <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-mono">{stat.label}</div>
          </div>
        ))}
      </div>

      {/* Decompose */}
      {decomposeStep && <StepCard step={decomposeStep} />}

      {/* Sub-question groups */}
      {sqGroups.length > 0 && (
        <div>
          <div className="text-xs uppercase tracking-wider text-muted-foreground mb-3 font-mono flex items-center gap-2">
            <span className="w-4 h-px bg-foreground/20" />
            Investigation — {sqGroups.length} Sub-Questions
          </div>
          <div className="space-y-2">
            {sqGroups.map(([sqId, group], i) => (
              <SubQuestionGroup
                key={sqId}
                sqId={sqId}
                question={group.question}
                priority={group.priority}
                steps={group.steps}
                defaultOpen={i === 0}
              />
            ))}
          </div>
        </div>
      )}

      {/* Global steps (analyze, quality, compose) */}
      {globalSteps.length > 0 && (
        <div>
          <div className="text-xs uppercase tracking-wider text-muted-foreground mb-3 font-mono flex items-center gap-2">
            <span className="w-4 h-px bg-foreground/20" />
            Synthesis & Composition
          </div>
          <div className="space-y-3">
            {globalSteps.map((step, i) => (
              <StepCard key={i} step={step} />
            ))}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="text-center text-[10px] text-muted-foreground font-mono pt-4 border-t border-foreground/5">
        {trace.total_steps} total steps &middot; {searchCount} searches &middot; {scrapeCount} scrapes &middot; {reflectCount} reflections
      </div>
    </div>
  );
}
