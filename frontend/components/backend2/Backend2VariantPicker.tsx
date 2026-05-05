"use client";

/**
 * Backend2VariantPicker — mandatory query-variant selection between a1 and a2.
 *
 * After a1 finishes the backend2 graph pauses (interrupt_before=["a2_questions"])
 * and emits an `awaiting_variant_choice` SSE event with 4 ranked variants.
 * The progress page mounts this component while the run is paused; clicking
 * a card POSTs /select_variant which resumes the graph.
 */

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Check, Loader2, Sparkles } from "lucide-react";
import { selectBackend2Variant } from "@/lib/api";
import type { Backend2QueryVariantOption } from "@/lib/types-backend2";
import { cn } from "@/lib/utils";

interface Props {
  jobId: string;
  originalQuery: string;
  variants: Backend2QueryVariantOption[];
}

export default function Backend2VariantPicker({ jobId, originalQuery, variants }: Props) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConfirm() {
    if (selectedIndex == null || submitting) return;
    setError(null);
    setSubmitting(true);
    try {
      await selectBackend2Variant(jobId, selectedIndex);
      // Server fires `variant_chosen` SSE which clears the picker via the
      // store; we keep the loading indicator until that arrives.
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit pick");
      setSubmitting(false);
    }
  }

  // Sort by composite score (highest first) — server already does this but
  // re-sort defensively in case of network reordering.
  const ordered = [...variants].sort((a, b) => b.composite - a.composite);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="glass-card rounded-2xl p-6 lg:p-8 mb-8 relative overflow-hidden"
    >
      {/* Decorative orb */}
      <div
        className="pointer-events-none absolute -top-12 -right-12 w-60 h-60 rounded-full opacity-20"
        style={{
          background: "radial-gradient(circle, var(--color-purple) 0%, transparent 70%)",
          filter: "blur(60px)",
        }}
      />

      <div className="relative z-10">
        <div className="flex items-center gap-2 mb-2">
          <Sparkles className="w-4 h-4 text-purple" />
          <span className="text-[10px] uppercase tracking-wider text-purple font-medium">
            Pick a refined query &middot; pipeline paused after a1_refiner
          </span>
        </div>
        <h2 className="font-display text-2xl lg:text-3xl text-foreground leading-tight mb-1">
          Which version should we research?
        </h2>
        <p className="text-sm text-muted-foreground mb-6">
          a1 took{" "}
          <span className="italic text-foreground/70">&ldquo;{originalQuery}&rdquo;</span>{" "}
          and produced four analyst-grade variants. Pick one to continue — a2/a3/a4
          will run only after you choose.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-5">
          {ordered.map((v) => {
            const isSelected = selectedIndex === v.index;
            return (
              <button
                key={v.index}
                type="button"
                onClick={() => !submitting && setSelectedIndex(v.index)}
                disabled={submitting}
                className={cn(
                  "text-left rounded-xl p-4 border transition-all relative",
                  "hover:border-purple/40",
                  isSelected
                    ? "border-purple bg-purple/5 ring-2 ring-purple/20"
                    : "border-foreground/10 bg-foreground/[0.02]",
                  submitting && "opacity-60 cursor-not-allowed",
                )}
              >
                <div className="flex items-start justify-between mb-2 gap-3">
                  <div className="flex items-center gap-2">
                    <span
                      className={cn(
                        "w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-mono font-semibold",
                        isSelected
                          ? "bg-purple text-white"
                          : "bg-foreground/10 text-muted-foreground",
                      )}
                    >
                      {isSelected ? <Check className="w-3.5 h-3.5" /> : v.index}
                    </span>
                    <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                      score {v.composite.toFixed(1)}
                    </span>
                  </div>
                </div>
                <p className="text-sm text-foreground leading-snug mb-2">
                  {v.text}
                </p>
                {v.reason && (
                  <p className="text-xs text-muted-foreground italic leading-snug">
                    {v.reason}
                  </p>
                )}
              </button>
            );
          })}
        </div>

        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
            >
              {error}
            </motion.div>
          )}
        </AnimatePresence>

        <div className="flex items-center justify-end gap-3">
          <span className="text-xs text-muted-foreground font-mono">
            {selectedIndex == null
              ? "no variant selected"
              : `variant #${selectedIndex} selected`}
          </span>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={selectedIndex == null || submitting}
            className={cn(
              "inline-flex items-center gap-2 rounded-full px-5 h-10 text-sm font-medium",
              "transition-colors group",
              selectedIndex == null || submitting
                ? "bg-foreground/10 text-muted-foreground cursor-not-allowed"
                : "bg-foreground text-background hover:bg-foreground/90",
            )}
          >
            {submitting ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Resuming pipeline&hellip;
              </>
            ) : (
              <>
                Continue
                <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-1" />
              </>
            )}
          </button>
        </div>
      </div>
    </motion.div>
  );
}
