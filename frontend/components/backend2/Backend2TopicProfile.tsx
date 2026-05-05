"use client";

/**
 * Backend2TopicProfile — renders the a0 TopicProfile card.
 *
 * Shown at the top of the backend2 results page so the reader knows what
 * domain the run thought it was operating in (clinical / market / policy /
 * social-science / etc.) and what metric vocabulary the rest of the
 * pipeline was anchored to.
 *
 * Reuses: glass-card, evidence-highlight-* (for chip styling),
 * Instrument Serif heading font, brand purple/orange tokens.
 */

import { motion } from "framer-motion";
import { useState } from "react";
import type { Backend2TopicProfile as Profile } from "@/lib/types-backend2";
import { ChevronDown, ChevronUp } from "lucide-react";

interface Props {
  profile: Profile | null;
}

const _DOMAIN_PALETTE: Record<string, string> = {
  market_research:    "bg-[var(--color-orange)]/10  text-[var(--color-orange)]  border-[var(--color-orange)]/30",
  clinical_research:  "bg-emerald-500/10            text-emerald-700           border-emerald-500/30",
  policy_analysis:    "bg-sky-500/10                text-sky-700               border-sky-500/30",
  social_science:     "bg-[var(--color-purple)]/10  text-[var(--color-purple)] border-[var(--color-purple)]/30",
};

function _domainClass(domain: string): string {
  const key = (domain || "").toLowerCase();
  return (
    _DOMAIN_PALETTE[key] ||
    "bg-foreground/5 text-foreground/70 border-foreground/20"
  );
}

function _Pill({ text, intent = "neutral" }: { text: string; intent?: "positive" | "negative" | "neutral" }) {
  const cls =
    intent === "positive"
      ? "bg-emerald-500/10 text-emerald-700 border-emerald-500/20"
      : intent === "negative"
      ? "bg-[var(--color-coral)]/10 text-[var(--color-coral)] border-[var(--color-coral)]/20"
      : "bg-foreground/5 text-foreground/60 border-foreground/15";
  return (
    <span
      className={`inline-block px-2.5 py-1 rounded-md text-xs font-medium border ${cls}`}
    >
      {text}
    </span>
  );
}

export default function Backend2TopicProfile({ profile }: Props) {
  const [showSignals, setShowSignals] = useState(false);

  if (!profile) {
    return (
      <div className="glass-card p-6 mb-6">
        <p className="text-sm text-muted-foreground italic">
          No topic profile generated for this run.
        </p>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className="glass-card p-6 mb-6"
    >
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="flex-1 min-w-0">
          <span className="inline-flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-muted-foreground mb-2">
            <span className="w-5 h-px bg-foreground/30" />
            Topic Profile · a0
          </span>
          <h2 className="font-display text-2xl leading-tight text-foreground">
            {profile.topic_subject}
          </h2>
        </div>
        <span
          className={`shrink-0 px-3 py-1 rounded-full text-xs font-semibold border ${_domainClass(profile.topic_domain)}`}
        >
          {profile.topic_domain}
        </span>
      </div>

      {profile.expected_metric_kinds.length > 0 && (
        <div className="mb-3">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5">
            Expected metric kinds
          </div>
          <div className="flex flex-wrap gap-1.5">
            {profile.expected_metric_kinds.map((m) => (
              <_Pill key={m} text={m} />
            ))}
          </div>
        </div>
      )}

      {profile.key_dimensions.length > 0 && (
        <div className="mb-3">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5">
            Key dimensions
          </div>
          <div className="flex flex-wrap gap-1.5">
            {profile.key_dimensions.map((d) => (
              <_Pill key={d} text={d} />
            ))}
          </div>
        </div>
      )}

      {(profile.positive_signals.length > 0 || profile.negative_signals.length > 0) && (
        <button
          onClick={() => setShowSignals((v) => !v)}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors mt-2"
        >
          {showSignals ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          {showSignals ? "Hide" : "Show"} relevance signals
        </button>
      )}

      {showSignals && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3"
        >
          {profile.positive_signals.length > 0 && (
            <div>
              <div className="text-[11px] uppercase tracking-wider text-emerald-700 font-medium mb-1.5">
                On-topic signals
              </div>
              <div className="flex flex-wrap gap-1">
                {profile.positive_signals.slice(0, 8).map((s) => (
                  <_Pill key={s} text={s} intent="positive" />
                ))}
              </div>
            </div>
          )}
          {profile.negative_signals.length > 0 && (
            <div>
              <div className="text-[11px] uppercase tracking-wider text-[var(--color-coral)] font-medium mb-1.5">
                Off-topic signals
              </div>
              <div className="flex flex-wrap gap-1">
                {profile.negative_signals.slice(0, 8).map((s) => (
                  <_Pill key={s} text={s} intent="negative" />
                ))}
              </div>
            </div>
          )}
        </motion.div>
      )}

      {profile.profile_reasoning && (
        <p className="mt-4 text-xs text-muted-foreground italic border-t border-foreground/8 pt-3">
          {profile.profile_reasoning}
        </p>
      )}
    </motion.div>
  );
}
