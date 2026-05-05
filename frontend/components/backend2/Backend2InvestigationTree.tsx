"use client";

/**
 * Backend2InvestigationTree — visualises the recursive investigation
 * (Phase 4b-1) structure: top sub-questions decomposed into 2-4 atomic
 * parts each, with the part questions and their evidence yield.
 *
 * NOT the same as the legacy DecompositionTree — backend2 doesn't
 * persist the per-part research events to RunState (that data lives only
 * in structlog logs during a run). What we CAN show post-hoc:
 *   - Top-K sub-questions (a2 output)
 *   - For each, indicate whether topic_claims came from it (we can't link
 *     1:1, but we can show the sub-question + count of related claims by
 *     `related_sub_questions` in the underlying Passage records — but
 *     those are dropped after a3 too).
 *
 * For now: render the sub-questions as a simple tree; clicking expands to
 * show metric_hint, time_frame, and the raw_excerpt of any topic_claim
 * that mentions a token from the sub-question's text. Pragmatic
 * reconstruction; richer trace requires a future RunState extension.
 *
 * Reuses: glass-card, motion patterns, Instrument Serif heading.
 */

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronRight, ChevronDown, Search, FileText } from "lucide-react";
import type {
  Backend2SubQuestion,
  Backend2NumericClaim,
} from "@/lib/types-backend2";

interface Props {
  subQuestions: Backend2SubQuestion[];
  topicClaims: Backend2NumericClaim[];
}

function _claimsRelatedTo(sq: Backend2SubQuestion, allClaims: Backend2NumericClaim[]): Backend2NumericClaim[] {
  // Heuristic: a claim is "related" if its raw_excerpt or metric shares a
  // significant content word with the sub-question text. Cheap, no API calls.
  const sqWords = new Set(
    sq.text
      .toLowerCase()
      .split(/\W+/)
      .filter((w) => w.length >= 5)
  );
  if (sqWords.size === 0) return [];
  return allClaims.filter((c) => {
    const text = `${c.metric} ${c.raw_excerpt}`.toLowerCase();
    let hits = 0;
    for (const w of sqWords) if (text.includes(w)) hits += 1;
    return hits >= 2;
  });
}

function _categoryColor(cat: string): string {
  // Keep distinct hues per QuestionCategory but stay within the brand palette.
  const map: Record<string, string> = {
    size: "bg-emerald-500/10 text-emerald-700 border-emerald-500/20",
    segmentation: "bg-sky-500/10 text-sky-700 border-sky-500/20",
    competitive: "bg-[var(--color-orange)]/10 text-[var(--color-orange)] border-[var(--color-orange)]/20",
    geography: "bg-indigo-500/10 text-indigo-700 border-indigo-500/20",
    outlook: "bg-[var(--color-purple)]/10 text-[var(--color-purple)] border-[var(--color-purple)]/20",
    drivers: "bg-emerald-500/10 text-emerald-700 border-emerald-500/20",
    constraints: "bg-[var(--color-coral)]/10 text-[var(--color-coral)] border-[var(--color-coral)]/20",
  };
  return map[cat] || "bg-slate-500/10 text-slate-600 border-slate-500/20";
}

function _SubQuestionRow({
  sq,
  related,
  idx,
}: {
  sq: Backend2SubQuestion;
  related: Backend2NumericClaim[];
  idx: number;
}) {
  const [open, setOpen] = useState(false);
  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.25, delay: idx * 0.04 }}
      className="border-b border-foreground/6 last:border-0"
    >
      <button
        className="w-full flex items-start gap-3 py-3 text-left hover:bg-foreground/[0.03] transition-colors px-2 rounded-lg"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="shrink-0 mt-1 text-muted-foreground">
          {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="text-[10px] uppercase tracking-wider text-foreground/40 font-medium">
              SQ-{idx + 1}
            </span>
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border ${_categoryColor(sq.category)}`}
            >
              {sq.category}
            </span>
            {related.length > 0 && (
              <span className="text-[10px] text-emerald-700 font-medium">
                {related.length} related claim{related.length === 1 ? "" : "s"}
              </span>
            )}
          </div>
          <p className="text-sm text-foreground/85 leading-snug">{sq.text}</p>
        </div>
        <span className="shrink-0 text-[10px] text-muted-foreground font-mono mt-1">
          {sq.composite.toFixed(1)}
        </span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="ml-7 pb-3"
          >
            <div className="bg-foreground/[0.025] rounded-xl p-3 space-y-2">
              <div className="flex items-center gap-3 text-xs text-foreground/70 flex-wrap">
                {sq.metric_hint && (
                  <span>
                    <span className="text-muted-foreground">metric:</span>{" "}
                    <span className="font-medium text-foreground/80">{sq.metric_hint}</span>
                  </span>
                )}
                {sq.geography && (
                  <span>
                    <span className="text-muted-foreground">geo:</span>{" "}
                    <span className="font-medium text-foreground/80">{sq.geography}</span>
                  </span>
                )}
                {sq.time_frame && (
                  <span>
                    <span className="text-muted-foreground">time:</span>{" "}
                    <span className="font-medium text-foreground/80">{sq.time_frame}</span>
                  </span>
                )}
              </div>

              {sq.reason && (
                <p className="text-xs text-muted-foreground italic border-l-2 border-foreground/10 pl-2">
                  Why this question: {sq.reason}
                </p>
              )}

              {related.length > 0 && (
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5 flex items-center gap-1">
                    <FileText className="w-3 h-3" />
                    Related evidence ({related.length})
                  </div>
                  <ul className="space-y-1.5">
                    {related.slice(0, 5).map((c, i) => (
                      <li
                        key={i}
                        className="text-xs text-foreground/75 leading-snug pl-2 border-l-2 border-[var(--color-purple)]/30"
                      >
                        <span className="font-mono text-foreground">
                          {c.value} {c.unit}
                        </span>
                        {" — "}
                        <span className="text-muted-foreground">{c.metric}</span>
                        {c.raw_excerpt && (
                          <div className="text-[10px] text-foreground/40 mt-0.5 italic line-clamp-2">
                            "{c.raw_excerpt}"
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export default function Backend2InvestigationTree({
  subQuestions,
  topicClaims,
}: Props) {
  const sqWithRelated = useMemo(
    () =>
      subQuestions.map((sq) => ({
        sq,
        related: _claimsRelatedTo(sq, topicClaims),
      })),
    [subQuestions, topicClaims]
  );

  if (subQuestions.length === 0) {
    return null;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.15 }}
      className="glass-card p-6 mb-6"
    >
      <div className="flex items-center gap-3 mb-4">
        <Search className="w-4 h-4 text-[var(--color-purple)] shrink-0" />
        <div>
          <span className="inline-flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-muted-foreground">
            Investigation Tree · a2 + a3 recursive
          </span>
          <h3 className="font-display text-xl text-foreground">
            Sub-questions and the evidence they surfaced
          </h3>
        </div>
      </div>

      <div>
        {sqWithRelated.map(({ sq, related }, i) => (
          <_SubQuestionRow key={i} sq={sq} related={related} idx={i} />
        ))}
      </div>
    </motion.div>
  );
}
