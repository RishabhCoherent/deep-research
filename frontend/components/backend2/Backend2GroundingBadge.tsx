"use client";

/**
 * Backend2GroundingBadge — surfaces the a8.5 verifier's grounding score
 * as a top-of-results KPI tile. Click to expand the fabricated/uncertain
 * claim lists.
 *
 * Reuses: glass-card, claim-strong/weak/unsupported palette tokens, motion.
 */

import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import { ChevronDown, ChevronUp, ShieldCheck, ShieldAlert, ShieldX } from "lucide-react";
import type { Backend2Verification } from "@/lib/types-backend2";

interface Props {
  verification: Backend2Verification | null;
}

function _bandClass(score: number): {
  pillBg: string;
  pillText: string;
  bigText: string;
  Icon: typeof ShieldCheck;
  band: "high" | "moderate" | "low";
} {
  if (score >= 0.85) {
    return {
      pillBg: "bg-emerald-500/10 border-emerald-500/30",
      pillText: "text-emerald-700",
      bigText: "text-emerald-700",
      Icon: ShieldCheck,
      band: "high",
    };
  }
  if (score >= 0.7) {
    return {
      pillBg: "bg-[var(--color-orange)]/10 border-[var(--color-orange)]/30",
      pillText: "text-[var(--color-orange)]",
      bigText: "text-[var(--color-orange)]",
      Icon: ShieldAlert,
      band: "moderate",
    };
  }
  return {
    pillBg: "bg-[var(--color-coral)]/10 border-[var(--color-coral)]/30",
    pillText: "text-[var(--color-coral)]",
    bigText: "text-[var(--color-coral)]",
    Icon: ShieldX,
    band: "low",
  };
}

export default function Backend2GroundingBadge({ verification }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (!verification || verification.total_claims === 0) {
    return null;
  }

  const score = verification.grounding_score;
  const pct = Math.round(score * 100);
  const v = _bandClass(score);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="glass-card p-5 mb-6"
    >
      <div
        className="flex items-center gap-4 cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
        role="button"
        aria-expanded={expanded}
      >
        <div
          className={`shrink-0 w-14 h-14 rounded-full border-2 flex items-center justify-center ${v.pillBg}`}
        >
          <v.Icon className={`w-7 h-7 ${v.pillText}`} />
        </div>
        <div className="flex-1 min-w-0">
          <span className="inline-flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-muted-foreground mb-0.5">
            <span className="w-5 h-px bg-foreground/30" />
            Brief Grounding · a8.5 verifier
          </span>
          <div className="flex items-baseline gap-2">
            <span className={`font-display text-3xl ${v.bigText}`}>
              {pct}%
            </span>
            <span className="text-sm text-foreground/60">
              ({verification.verified_claims} of {verification.total_claims} factual claims directly grounded)
            </span>
          </div>
          {v.band === "low" && (
            <p className="text-xs text-[var(--color-coral)] mt-1">
              Below 0.7 grounding — prose may include LLM-generated specifics
              not in the source set. Treat unverified items with caution.
            </p>
          )}
        </div>
        <button
          className="shrink-0 text-slate-400 hover:text-slate-600 transition-colors"
          aria-label="Toggle details"
        >
          {expanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
        </button>
      </div>

      <AnimatePresence>
        {expanded && (verification.fabricated.length > 0 || verification.uncertain.length > 0) && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25 }}
            className="mt-4 pt-4 border-t border-foreground/8 grid grid-cols-1 md:grid-cols-2 gap-4"
          >
            {verification.fabricated.length > 0 && (
              <div>
                <div className="text-[11px] uppercase tracking-wider text-[var(--color-coral)] font-medium mb-2 flex items-center gap-1">
                  <ShieldX className="w-3 h-3" />
                  Likely fabricated ({verification.fabricated.length})
                </div>
                <ul className="space-y-1.5">
                  {verification.fabricated.slice(0, 8).map((c, i) => (
                    <li
                      key={i}
                      className="text-xs text-foreground/80 leading-snug pl-2 border-l-2 border-[var(--color-coral)]/40"
                    >
                      {c}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {verification.uncertain.length > 0 && (
              <div>
                <div className="text-[11px] uppercase tracking-wider text-[var(--color-orange)] font-medium mb-2 flex items-center gap-1">
                  <ShieldAlert className="w-3 h-3" />
                  Uncertain — plausible but not directly stated ({verification.uncertain.length})
                </div>
                <ul className="space-y-1.5">
                  {verification.uncertain.slice(0, 8).map((c, i) => (
                    <li
                      key={i}
                      className="text-xs text-foreground/80 leading-snug pl-2 border-l-2 border-[var(--color-orange)]/40"
                    >
                      {c}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
