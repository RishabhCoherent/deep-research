"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import {
  Puzzle, Brain, Search, FileDown, FlipHorizontal,
  Scale, ShieldCheck, PenTool, ChevronDown, ChevronRight,
  Check, X, BadgeCheck,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import type {
  AnalystTrace, TraceStep, DecomposeContent, ThinkContent,
  SearchContent, AnalyzeContent,
  QualityContent, ComposeContent, VerifyContent,
} from "@/lib/types";

/* ── Phase styling ──────────────────────────────────────────── */

const PHASE = {
  decompose: { icon: Puzzle, label: "Understanding the Question", color: "text-indigo-400", bg: "bg-indigo-500/10", border: "border-indigo-500/20", accent: "indigo" },
  think:     { icon: Brain, label: "Forming Hypothesis", color: "text-purple-400", bg: "bg-purple-500/10", border: "border-purple-500/20", accent: "purple" },
  search:    { icon: Search, label: "Searching", color: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/20", accent: "blue" },
  scrape:    { icon: FileDown, label: "Reading Sources", color: "text-slate-400", bg: "bg-slate-500/10", border: "border-slate-500/20", accent: "slate" },
  reflect:   { icon: FlipHorizontal, label: "Evaluating Evidence", color: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/20", accent: "amber" },
  analyze:   { icon: Scale, label: "Making Sense of the Data", color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20", accent: "emerald" },
  quality:   { icon: ShieldCheck, label: "Quality Check", color: "text-green-400", bg: "bg-green-500/10", border: "border-green-500/20", accent: "green" },
  compose:   { icon: PenTool, label: "Writing the Report", color: "text-foreground/70", bg: "bg-foreground/5", border: "border-foreground/10", accent: "neutral" },
  verify:    { icon: BadgeCheck, label: "Grounding Check", color: "text-cyan-400", bg: "bg-cyan-500/10", border: "border-cyan-500/20", accent: "cyan" },
};

const PRIORITY_BADGE: Record<number, { label: string; cls: string }> = {
  1: { label: "P1 Critical", cls: "bg-red-500/15 text-red-400 border-red-500/20" },
  2: { label: "P2 Important", cls: "bg-amber-500/15 text-amber-400 border-amber-500/20" },
  3: { label: "P3 Enrichment", cls: "bg-foreground/5 text-muted-foreground border-foreground/10" },
};

/* ── Helpers ─────────────────────────────────────────────────── */

function groupStepsBySq(steps: TraceStep[]) {
  const groups: Record<string, { question: string; priority: number; steps: TraceStep[] }> = {};
  const thinkSteps = steps.filter(s => s.phase === "think");

  for (const step of steps) {
    if (!step.sq_id || ["decompose", "analyze", "quality", "compose"].includes(step.phase)) continue;
    if (!groups[step.sq_id]) {
      const think = thinkSteps.find(t => t.sq_id === step.sq_id);
      const content = think?.content as ThinkContent | undefined;
      groups[step.sq_id] = {
        question: content?.question || step.sq_id,
        priority: content?.priority || 2,
        steps: [],
      };
    }
    groups[step.sq_id].steps.push(step);
  }
  return groups;
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 70 ? "bg-green-500" : pct >= 40 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 rounded-full bg-foreground/10">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono text-muted-foreground">{pct}%</span>
    </div>
  );
}

function PhaseBadge({ phase, elapsed }: { phase: string; elapsed?: number }) {
  const p = PHASE[phase as keyof typeof PHASE];
  if (!p) return null;
  const Icon = p.icon;
  return (
    <div className="flex items-center gap-3">
      <div className={cn("flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-mono font-medium", p.bg, p.border, p.color)}>
        <Icon className="h-3.5 w-3.5" />
        {p.label}
      </div>
      {elapsed != null && elapsed > 0 && (
        <span className="text-[10px] font-mono text-muted-foreground">{elapsed.toFixed(1)}s</span>
      )}
    </div>
  );
}

/* ── Section 1: Decompose ────────────────────────────────────── */

function DecomposeSection({ step }: { step: TraceStep }) {
  const c = step.content as unknown as DecomposeContent;
  const sqs = c?.sub_questions || [];
  return (
    <section className="space-y-6">
      <PhaseBadge phase="decompose" elapsed={step.elapsed_s} />
      <p className="text-muted-foreground leading-relaxed">
        The agent read your topic and identified the core question:
      </p>
      {c?.core_question && (
        <blockquote className="border-l-2 border-indigo-500/40 pl-4 text-lg font-medium text-foreground/90 italic">
          "{c.core_question}"
        </blockquote>
      )}
      {sqs.length > 0 && (
        <>
          <p className="text-muted-foreground">
            It planned <strong className="text-foreground">{sqs.length} research questions</strong> to investigate:
          </p>
          <div className="grid gap-2">
            {sqs.map((sq: any, i: number) => {
              const pri = PRIORITY_BADGE[sq.priority] || PRIORITY_BADGE[2];
              return (
                <div key={sq.id || i} className="flex items-start gap-3 rounded-lg border border-foreground/5 bg-foreground/2 px-4 py-3">
                  <span className={cn("mt-0.5 shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-mono font-medium", pri.cls)}>
                    {pri.label}
                  </span>
                  <span className="text-sm text-foreground/80">{sq.question}</span>
                </div>
              );
            })}
          </div>
        </>
      )}
      {c?.assumptions?.length > 0 && (
        <details className="group">
          <summary className="text-xs font-mono text-muted-foreground cursor-pointer hover:text-foreground">
            Assumptions ({c.assumptions.length})
          </summary>
          <ul className="mt-2 space-y-1 pl-4 text-xs text-muted-foreground">
            {c.assumptions.map((a: string, i: number) => <li key={i}>• {a}</li>)}
          </ul>
        </details>
      )}
    </section>
  );
}

/* ── Section 2: Investigate ──────────────────────────────────── */

function InvestigateSection({ steps }: { steps: TraceStep[] }) {
  const groups = useMemo(() => groupStepsBySq(steps), [steps]);
  const sqIds = Object.keys(groups);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(sqIds.slice(0, 3)));

  const searches = steps.filter(s => s.phase === "search").length
    + steps.filter(s => s.phase === "part_research").length; // each part does a search
  const scrapes = steps.filter(s => s.phase === "scrape").length
    + steps.filter(s => s.phase === "part_research" && (s.content as any)?.scrape?.success).length;
  const reflects = steps.filter(s => s.phase === "reflect");
  const answered = reflects.filter(s => {
    const c = s.content as any;
    return c?.confidence && c.confidence >= 0.3;
  }).length;

  const toggle = (id: string) => setExpanded(prev => {
    const next = new Set(prev);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  return (
    <section className="space-y-6">
      <PhaseBadge phase="search" />
      <p className="text-muted-foreground leading-relaxed">
        The agent broke each question into smaller parts, researched each part, then combined the answers.
        It performed <strong className="text-foreground">{searches} searches</strong>, read{" "}
        <strong className="text-foreground">{scrapes} web pages</strong>, and answered{" "}
        <strong className="text-foreground">{answered} of {sqIds.length}</strong> questions.
      </p>

      <div className="space-y-3">
        {sqIds.map((sqId, idx) => {
          const g = groups[sqId];
          const isOpen = expanded.has(sqId);
          const thinkStep = g.steps.find(s => s.phase === "think");
          const reflectStep = g.steps.find(s => s.phase === "reflect");
          const searchSteps = g.steps.filter(s => s.phase === "search");
          const thinkC = thinkStep?.content as any;
          const reflectC = reflectStep?.content as any;
          const confidence = reflectC?.confidence || 0;
          const status = confidence >= 0.3 ? "answered" : "gap";

          // New decomposition format: think has "parts" array
          const hasParts = Array.isArray(thinkC?.parts) && thinkC.parts.length > 0;
          // Old format: think has "hypothesis"
          const hasHypothesis = !!thinkC?.hypothesis;

          return (
            <div key={sqId} className="rounded-xl border border-foreground/5 bg-foreground/2 overflow-hidden">
              {/* Header */}
              <button
                onClick={() => toggle(sqId)}
                className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-foreground/3 transition-colors"
              >
                {isOpen ? <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" /> : <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />}
                <span className="text-sm font-medium text-foreground/80 flex-1">
                  Q{idx + 1}: {g.question}
                </span>
                {hasParts && (
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full border bg-blue-500/10 text-blue-400 border-blue-500/20 mr-1">
                    {thinkC.parts.length} parts
                  </span>
                )}
                <span className={cn(
                  "text-[10px] font-mono px-2 py-0.5 rounded-full border",
                  status === "answered" ? "bg-green-500/10 text-green-400 border-green-500/20" : "bg-red-500/10 text-red-400 border-red-500/20"
                )}>
                  {status === "answered" ? `${Math.round(confidence * 100)}% confidence` : "gap"}
                </span>
              </button>

              {/* Detail */}
              {isOpen && (
                <div className="px-4 pb-4 space-y-4 border-t border-foreground/5 pt-3">
                  {/* Decomposition parts (new format) */}
                  {hasParts && (
                    <div>
                      <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-2">Decomposed into {thinkC.parts.length} parts</p>
                      <div className="space-y-1.5">
                        {thinkC.parts.map((part: string, i: number) => (
                          <div key={i} className="flex items-start gap-2 text-xs">
                            <span className="shrink-0 text-[10px] font-mono text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded">P{i + 1}</span>
                            <span className="text-foreground/80">{part}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Hypothesis (old format) */}
                  {!hasParts && hasHypothesis && (
                    <div>
                      <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-1">Hypothesis</p>
                      <p className="text-sm text-foreground/70 italic">"{thinkC.hypothesis}"</p>
                    </div>
                  )}

                  {/* Per-part research detail (new recursive format) */}
                  {g.steps.filter(s => s.phase === "part_research").length > 0 && (
                    <div className="space-y-3">
                      <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">Research per part</p>
                      {g.steps.filter(s => s.phase === "part_research").map((s, i) => {
                        const pc = s.content as any;
                        return (
                          <div key={i} className="rounded-lg border border-foreground/5 bg-foreground/2 p-3 space-y-2">
                            {/* Part header */}
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] font-mono font-bold text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded">P{i + 1}</span>
                              <span className="text-xs font-medium text-foreground/80">{pc?.part_question}</span>
                            </div>

                            {/* Search results */}
                            {pc?.search_results?.length > 0 && (
                              <div className="pl-6">
                                <p className="text-[10px] font-mono text-muted-foreground mb-1">
                                  <Search className="h-3 w-3 inline mr-1" />
                                  {pc.search_results.length} results found
                                </p>
                                <div className="space-y-1">
                                  {pc.search_results.slice(0, 3).map((r: any, j: number) => (
                                    <div key={j} className="text-[11px] text-muted-foreground">
                                      <span className="text-foreground/70">{r.title}</span>
                                      {r.snippet && <span className="ml-1">— {r.snippet}</span>}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Scrape info */}
                            {pc?.scrape?.success && (
                              <div className="pl-6">
                                <p className="text-[10px] font-mono text-muted-foreground">
                                  <FileDown className="h-3 w-3 inline mr-1" />
                                  Scraped {pc.scrape.content_length?.toLocaleString()} chars via {pc.scrape.method}
                                </p>
                              </div>
                            )}

                            {/* Evidence found */}
                            {pc?.evidence_found?.length > 0 && (
                              <div className="pl-6">
                                <p className="text-[10px] font-mono text-muted-foreground mb-1">{pc.evidence_found.length} evidence items</p>
                                {pc.evidence_found.slice(0, 3).map((e: any, j: number) => (
                                  <div key={j} className="flex items-start gap-1.5 text-[11px] mb-1">
                                    <Check className="h-3 w-3 mt-0.5 text-green-500 shrink-0" />
                                    <span className="text-foreground/70">{e.fact}</span>
                                  </div>
                                ))}
                              </div>
                            )}

                            {/* Part answer summary */}
                            {pc?.answer_summary && (
                              <div className="pl-6 pt-1 border-t border-foreground/5">
                                <p className="text-[11px] text-foreground/80">{pc.answer_summary}</p>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Searches (old format — no part_research steps) */}
                  {g.steps.filter(s => s.phase === "part_research").length === 0 && searchSteps.length > 0 && (
                    <div>
                      <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-1">Searches ({searchSteps.length})</p>
                      <div className="space-y-1">
                        {searchSteps.map((s, i) => {
                          const sc = s.content as unknown as SearchContent;
                          return (
                            <div key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
                              <Search className="h-3 w-3 shrink-0" />
                              <span className="truncate">"{sc?.query}"</span>
                              <span className="shrink-0 text-[10px]">→ {sc?.results?.length || 0} results</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Evidence findings (old format) */}
                  {g.steps.filter(s => s.phase === "part_research").length === 0 && reflectC?.findings?.length > 0 && (
                    <div>
                      <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-1">Evidence found ({reflectC.findings.length})</p>
                      <div className="space-y-1.5">
                        {reflectC.findings.slice(0, 5).map((f: any, i: number) => (
                          <div key={i} className="flex items-start gap-2 text-xs">
                            <Check className="h-3 w-3 mt-0.5 text-green-500 shrink-0" />
                            <div>
                              <span className="text-foreground/80">{f.data_point}</span>
                              {f.source_title && (
                                <span className="ml-1 text-muted-foreground">— {f.source_title}</span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Combined answer */}
                  {reflectC?.answer && (
                    <div>
                      <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-1">
                        {hasParts ? "Combined answer" : "Conclusion"}
                      </p>
                      <p className="text-sm text-foreground/80">{reflectC.answer}</p>
                      <ConfidenceBar value={confidence} />
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

/* ── Section 3: Analyze ──────────────────────────────────────── */

// Strip internal evidence IDs like (ev_abc123, ev_def456) from display text
function stripEvidenceIds(text: string): string {
  return text.replace(/\s*\(ev_[a-f0-9]+(,\s*ev_[a-f0-9]+)*\)/g, "").trim();
}

function AnalyzeSection({ step }: { step: TraceStep }) {
  const c = step.content as unknown as AnalyzeContent;
  const findings = (c?.key_findings || []).map(stripEvidenceIds);
  const judgments = c?.judgments || [];

  return (
    <section className="space-y-6">
      <PhaseBadge phase="analyze" elapsed={step.elapsed_s} />
      <p className="text-muted-foreground leading-relaxed">
        The agent cross-referenced all evidence and formed{" "}
        <strong className="text-foreground">{findings.length} key findings</strong> and{" "}
        <strong className="text-foreground">{judgments.length} analyst judgments</strong>.
      </p>

      {/* Narrative */}
      {c?.narrative_thread && (
        <blockquote className="border-l-2 border-emerald-500/40 pl-4 text-base text-foreground/90 leading-relaxed">
          {c.narrative_thread}
        </blockquote>
      )}

      {/* Key findings */}
      {findings.length > 0 && (
        <div>
          <p className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-2">Key Findings</p>
          <ol className="space-y-2 list-decimal list-inside">
            {findings.map((f: string, i: number) => (
              <li key={i} className="text-sm text-foreground/80 leading-relaxed">{f}</li>
            ))}
          </ol>
        </div>
      )}

      {/* Judgments */}
      {judgments.length > 0 && (
        <div>
          <p className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-2">Analyst Judgments</p>
          <div className="space-y-3">
            {judgments.map((j: any, i: number) => (
              <div key={i} className="rounded-lg border border-foreground/5 bg-foreground/2 p-4">
                <div className="flex items-start gap-2">
                  <span className={cn(
                    "shrink-0 mt-0.5 text-[10px] font-mono font-bold px-2 py-0.5 rounded-full border",
                    j.conviction === "high" ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/20" :
                    j.conviction === "medium" ? "bg-amber-500/15 text-amber-400 border-amber-500/20" :
                    "bg-foreground/5 text-muted-foreground border-foreground/10"
                  )}>
                    {j.conviction?.toUpperCase()}
                  </span>
                  <div>
                    <p className="text-sm font-medium text-foreground/90">{j.claim}</p>
                    {j.reasoning && (
                      <p className="mt-1 text-xs text-muted-foreground leading-relaxed">{j.reasoning}</p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {c?.overall_confidence != null && (
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-muted-foreground">Overall confidence:</span>
          <ConfidenceBar value={c.overall_confidence} />
        </div>
      )}
    </section>
  );
}

/* ── Section 4: Quality Gate ─────────────────────────────────── */

function QualitySection({ step }: { step: TraceStep }) {
  const c = step.content as unknown as QualityContent;
  const dims = [
    { key: "coverage", label: "Coverage" },
    { key: "evidence_strength", label: "Evidence Strength" },
    { key: "evidence_depth", label: "Evidence Depth" },
    { key: "contradiction_resolution", label: "Contradictions Resolved" },
    { key: "judgment_formation", label: "Judgments Formed" },
    { key: "gap_acknowledgment", label: "Gaps Acknowledged" },
  ];

  return (
    <section className="space-y-6">
      <PhaseBadge phase="quality" elapsed={step.elapsed_s} />
      <p className="text-muted-foreground leading-relaxed">
        The research was scored on 6 quality dimensions:
      </p>

      <div className="space-y-3 max-w-md">
        {dims.map(d => {
          const val = (c as any)?.[d.key] ?? 0;
          const pct = Math.round(val * 100);
          return (
            <div key={d.key} className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground w-40 shrink-0">{d.label}</span>
              <div className="flex-1 h-2 rounded-full bg-foreground/10">
                <div
                  className={cn("h-full rounded-full", pct >= 70 ? "bg-green-500" : pct >= 40 ? "bg-amber-500" : "bg-red-500")}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="text-xs font-mono text-muted-foreground w-10 text-right">{pct}%</span>
            </div>
          );
        })}
      </div>

      {c?.overall != null && (
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium">Overall:</span>
          <span className="text-lg font-mono font-bold">{Math.round(c.overall * 100)}%</span>
          <span className={cn(
            "px-2.5 py-0.5 rounded-full text-xs font-mono font-bold border",
            c.passes ? "bg-green-500/15 text-green-400 border-green-500/20" : "bg-red-500/15 text-red-400 border-red-500/20"
          )}>
            {c.passes ? "PASS" : "FAIL"}
          </span>
        </div>
      )}

      {c?.feedback && (
        <p className="text-xs text-muted-foreground italic">{c.feedback}</p>
      )}
    </section>
  );
}

/* ── Section 5: Compose ──────────────────────────────────────── */

function ComposeSection({ step }: { step: TraceStep }) {
  const c = step.content as unknown as ComposeContent;
  return (
    <section className="space-y-6">
      <PhaseBadge phase="compose" elapsed={step.elapsed_s} />
      <p className="text-muted-foreground leading-relaxed">
        The agent structured the report into{" "}
        <strong className="text-foreground">{c?.sections?.length || "several"} sections</strong> and wrote{" "}
        <strong className="text-foreground">{c?.word_count?.toLocaleString() || "the"} words</strong>.
      </p>
      {(c?.sections?.length ?? 0) > 0 && (
        <ol className="list-decimal list-inside space-y-1 text-sm text-foreground/70">
          {c.sections?.map((s: string, i: number) => <li key={i}>{s}</li>)}
        </ol>
      )}
    </section>
  );
}

/* ── Section 6: Verify ───────────────────────────────────────── */

function VerifySection({ step }: { step: TraceStep }) {
  const c = step.content as unknown as VerifyContent;
  const pct = Math.round((c?.grounding_score ?? 0) * 100);
  const color = pct >= 80 ? "bg-green-500" : pct >= 60 ? "bg-amber-500" : "bg-red-500";
  const textColor = pct >= 80 ? "text-green-400" : pct >= 60 ? "text-amber-400" : "text-red-400";

  return (
    <section className="space-y-6">
      <PhaseBadge phase="verify" elapsed={step.elapsed_s} />
      <p className="text-muted-foreground leading-relaxed">
        Checked <strong className="text-foreground">{c?.total_claims ?? 0} factual claims</strong> in the report against collected evidence.
      </p>

      <div className="space-y-3 max-w-md">
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground w-40 shrink-0">Grounding Score</span>
          <div className="flex-1 h-2 rounded-full bg-foreground/10">
            <div className={cn("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
          </div>
          <span className={cn("text-xs font-mono font-bold w-10 text-right", textColor)}>{pct}%</span>
        </div>
      </div>

      <div className="flex gap-6 text-sm">
        <div><span className="text-green-400 font-mono font-bold">{c?.verified_claims ?? 0}</span> <span className="text-muted-foreground">verified</span></div>
        <div><span className="text-amber-400 font-mono font-bold">{c?.uncertain?.length ?? 0}</span> <span className="text-muted-foreground">uncertain</span></div>
        <div><span className="text-red-400 font-mono font-bold">{c?.unverified?.length ?? 0}</span> <span className="text-muted-foreground">unverified</span></div>
      </div>

      {(c?.unverified?.length ?? 0) > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-red-400">Unverified claims:</p>
          <ul className="space-y-1">
            {c.unverified.slice(0, 8).map((claim, i) => (
              <li key={i} className="text-xs text-muted-foreground pl-3 border-l border-red-500/30">
                {claim}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

/* ── Full-screen overlay ─────────────────────────────────────── */

interface AnalystTraceOverlayProps {
  isOpen: boolean;
  onClose: () => void;
  trace: AnalystTrace;
}

export function AnalystTraceOverlay({ isOpen, onClose, trace }: AnalystTraceOverlayProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const onEsc = useCallback((e: KeyboardEvent) => {
    if (e.key === "Escape") onClose();
  }, [onClose]);

  useEffect(() => {
    if (isOpen) document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, [isOpen, onEsc]);

  const decomposeStep = trace.steps.find(s => s.phase === "decompose");
  const analyzeStep = trace.steps.find(s => s.phase === "analyze");
  const qualityStep = trace.steps.find(s => s.phase === "quality");
  const composeStep = trace.steps.find(s => s.phase === "compose");
  const verifyStep = trace.steps.find(s => s.phase === "verify");
  const investigateSteps = trace.steps.filter(s =>
    ["think", "search", "scrape", "reflect", "part_research"].includes(s.phase)
  );

  const totalSearches = trace.steps.filter(s => s.phase === "search").length
    + trace.steps.filter(s => s.phase === "part_research").length;
  const totalScrapes = trace.steps.filter(s => s.phase === "scrape").length
    + trace.steps.filter(s => s.phase === "part_research" && (s.content as any)?.scrape?.success).length;

  if (!mounted) return null;

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className="fixed inset-0 z-50 flex flex-col bg-background"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
        >
          {/* Header */}
          <header className="shrink-0 flex items-center justify-between border-b border-foreground/10 px-6 lg:px-12 py-4 bg-background/80 backdrop-blur-xl">
            <div>
              <h1 className="text-lg font-display tracking-tight">Research Trace</h1>
              <p className="text-xs text-muted-foreground font-mono">
                {trace.total_steps} steps · {totalSearches} searches · {totalScrapes} pages read
              </p>
            </div>
            <button onClick={onClose} className="rounded-full p-2 hover:bg-foreground/5 transition-colors">
              <X className="h-5 w-5" />
            </button>
          </header>

          {/* Scrollable content */}
          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-3xl px-6 lg:px-0 py-10 space-y-16">

              {/* 1. Decompose */}
              {decomposeStep && <DecomposeSection step={decomposeStep} />}

              <hr className="border-foreground/5" />

              {/* 2. Investigate */}
              {investigateSteps.length > 0 && <InvestigateSection steps={investigateSteps} />}

              <hr className="border-foreground/5" />

              {/* 3. Analyze */}
              {analyzeStep && <AnalyzeSection step={analyzeStep} />}

              <hr className="border-foreground/5" />

              {/* 4. Quality Gate */}
              {qualityStep && <QualitySection step={qualityStep} />}

              <hr className="border-foreground/5" />

              {/* 5. Compose */}
              {composeStep && <ComposeSection step={composeStep} />}

              {/* 6. Verify */}
              {verifyStep && (
                <>
                  <hr className="border-foreground/5" />
                  <VerifySection step={verifyStep} />
                </>
              )}

              {/* Footer */}
              <div className="text-center text-xs text-muted-foreground font-mono pt-8 pb-4">
                Research complete · {trace.total_steps} reasoning steps
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}

/* ── Legacy export for backward compat ───────────────────────── */
export function AnalystTraceTimeline({ trace: _trace }: { trace: AnalystTrace }) {
  return <div className="text-sm text-muted-foreground p-4">Use AnalystTraceOverlay instead.</div>;
}
