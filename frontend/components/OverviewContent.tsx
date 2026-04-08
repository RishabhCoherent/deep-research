"use client";

import { cn } from "@/lib/utils";
import type { ComparisonReport } from "@/lib/types";

/* ── Types matching backend metadata shape ── */

interface Judgment {
  claim: string;
  conviction: string;
  reasoning: string;
}

interface SubQuestion {
  id: string;
  question: string;
  status: string;
  priority: number;
  answer_type: string;
  confidence: number;
  answer: string;
  evidence_count: number;
}

interface QualityScores {
  coverage: number;
  evidence_strength: number;
  evidence_depth: number;
  contradiction_resolution: number;
  judgment_formation: number;
  gap_acknowledgment: number;
  overall: number;
}

/* ── Helpers ── */

function pct(val: number) {
  return Math.round((val ?? 0) * 100);
}

function ConvictionBadge({ conviction }: { conviction: string }) {
  const norm = (conviction ?? "").toLowerCase();
  const cls =
    norm === "high"
      ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/25"
      : norm === "medium"
      ? "bg-amber-500/15 text-amber-400 border-amber-500/25"
      : "bg-foreground/8 text-muted-foreground border-foreground/10";
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono font-bold border uppercase tracking-wide",
        cls
      )}
    >
      {norm}
    </span>
  );
}

function QualityBar({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  const p = pct(value);
  const color =
    p >= 75 ? "bg-emerald-500" : p >= 50 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-muted-foreground w-44 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-foreground/8">
        <div
          className={cn("h-full rounded-full transition-all duration-700", color)}
          style={{ width: `${p}%` }}
        />
      </div>
      <span className="text-xs font-mono text-muted-foreground w-9 text-right">
        {p}%
      </span>
    </div>
  );
}

/* ── Main component ── */

export function OverviewContent({ report }: { report: ComparisonReport }) {
  const l2 = report.layers.find((l) => l.layer === 2);
  const meta = (l2?.metadata ?? {}) as Record<string, unknown>;

  const analysis = (meta.analysis ?? {}) as {
    narrative?: string;
    key_findings?: string[];
    judgments?: Judgment[];
    confidence?: number;
  };

  const quality = (meta.quality ?? {}) as QualityScores;
  const board = (meta.board ?? {}) as {
    sub_questions?: SubQuestion[];
    evidence_count?: number;
  };

  const keyFindings: string[] = Array.isArray(analysis.key_findings)
    ? analysis.key_findings
    : [];
  const judgments: Judgment[] = Array.isArray(analysis.judgments)
    ? analysis.judgments
    : [];
  const subQuestions: SubQuestion[] = Array.isArray(board.sub_questions)
    ? board.sub_questions
    : [];
  const answeredCount = subQuestions.filter((q) => q.status === "answered").length;
  const evidenceCount = (meta.evidence_count as number) ?? board.evidence_count ?? 0;
  const searches = (meta.searches_count as number) ?? 0;
  const coveragePct = pct((meta.coverage as number) ?? 0);
  const confidence = pct(analysis.confidence ?? 0);
  const groundingScore = meta.grounding_score as number | null | undefined;

  const qualityDims = [
    { label: "Coverage", key: "coverage" },
    { label: "Evidence Strength", key: "evidence_strength" },
    { label: "Evidence Depth", key: "evidence_depth" },
    { label: "Contradictions Resolved", key: "contradiction_resolution" },
    { label: "Judgments Formed", key: "judgment_formation" },
    { label: "Gaps Acknowledged", key: "gap_acknowledgment" },
  ];

  return (
    <div className="space-y-12 max-w-3xl mx-auto">

      {/* ── Stats row ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-foreground/8 rounded-2xl overflow-hidden">
        {[
          { label: "Questions answered", value: `${answeredCount}/${subQuestions.length}` },
          { label: "Evidence collected", value: evidenceCount.toLocaleString() },
          { label: "Web searches", value: searches.toLocaleString() },
          { label: "Coverage", value: `${coveragePct}%` },
        ].map((s) => (
          <div key={s.label} className="bg-background px-6 py-5 text-center">
            <div className="text-2xl font-display tracking-tight">{s.value}</div>
            <div className="text-xs text-muted-foreground mt-1">{s.label}</div>
          </div>
        ))}
      </div>

      {/* ── Narrative thread ── */}
      {analysis.narrative && (
        <section className="space-y-3">
          <h2 className="text-xs font-mono uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <span className="w-4 h-px bg-foreground/30" /> Analyst Narrative
          </h2>
          <p className="text-[15px] leading-relaxed text-foreground/85">
            {analysis.narrative}
          </p>
          {confidence > 0 && (
            <p className="text-xs text-muted-foreground font-mono">
              Overall confidence: {confidence}%
              {groundingScore != null && ` · Grounding: ${pct(groundingScore)}%`}
            </p>
          )}
        </section>
      )}

      {/* ── Key findings ── */}
      {keyFindings.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-xs font-mono uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <span className="w-4 h-px bg-foreground/30" /> Key Findings
          </h2>
          <ol className="space-y-3">
            {keyFindings.map((f, i) => (
              <li key={i} className="flex gap-3">
                <span className="text-xs font-mono text-muted-foreground/60 pt-0.5 shrink-0 w-5">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <p className="text-sm text-foreground/80 leading-relaxed">{f}</p>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* ── Analyst judgments ── */}
      {judgments.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-xs font-mono uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <span className="w-4 h-px bg-foreground/30" /> Analyst Judgments
          </h2>
          <div className="space-y-3">
            {judgments.map((j, i) => (
              <div
                key={i}
                className="rounded-xl border border-foreground/8 bg-foreground/[0.02] p-4 space-y-2"
              >
                <div className="flex items-start gap-2">
                  <ConvictionBadge conviction={j.conviction} />
                  <p className="text-sm font-medium text-foreground/90 leading-snug">
                    {j.claim}
                  </p>
                </div>
                {j.reasoning && (
                  <p className="text-xs text-muted-foreground leading-relaxed pl-0.5">
                    {j.reasoning}
                  </p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Sub-questions answered ── */}
      {subQuestions.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-xs font-mono uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <span className="w-4 h-px bg-foreground/30" /> Research Questions
          </h2>
          <div className="space-y-2">
            {subQuestions.map((sq) => {
              const isAnswered = sq.status === "answered";
              const isGap = sq.status === "gap";
              return (
                <div
                  key={sq.id}
                  className="rounded-xl border border-foreground/8 p-4 space-y-1"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={cn(
                        "inline-block w-1.5 h-1.5 rounded-full shrink-0",
                        isAnswered
                          ? "bg-emerald-400"
                          : isGap
                          ? "bg-amber-400"
                          : "bg-foreground/20"
                      )}
                    />
                    <p className="text-sm text-foreground/80 leading-snug">
                      {sq.question}
                    </p>
                    {sq.priority === 1 && (
                      <span className="ml-auto shrink-0 text-[10px] font-mono text-red-400 border border-red-500/20 bg-red-500/10 px-1.5 py-0.5 rounded-full">
                        P1
                      </span>
                    )}
                  </div>
                  {isAnswered && sq.answer && (
                    <p className="text-xs text-muted-foreground leading-relaxed pl-4 line-clamp-2">
                      {sq.answer}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* ── Quality dimensions ── */}
      {quality.overall != null && (
        <section className="space-y-4">
          <h2 className="text-xs font-mono uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <span className="w-4 h-px bg-foreground/30" /> Research Quality
          </h2>
          <div className="space-y-2.5 max-w-md">
            {qualityDims.map((d) => (
              <QualityBar
                key={d.key}
                label={d.label}
                value={(quality as unknown as Record<string, number>)[d.key] ?? 0}
              />
            ))}
          </div>
          <div className="flex items-center gap-3 pt-1">
            <span className="text-sm font-medium">Overall</span>
            <span className="text-2xl font-display font-bold tracking-tight">
              {pct(quality.overall)}%
            </span>
          </div>
        </section>
      )}
    </div>
  );
}
