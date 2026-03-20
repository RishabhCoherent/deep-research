"use client";

import { useState } from "react";
import { Check } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { MarkdownReport } from "@/components/MarkdownReport";
import type { ComparisonReport } from "@/lib/types";
import { LAYER_NAMES } from "@/lib/types";

/* ── Constants ──────────────────────────────────────────────── */

const easeOutExpo: [number, number, number, number] = [0.22, 1, 0.36, 1];

const LAYER_COLORS: Record<number, { bg: string; border: string; text: string; dot: string }> = {
  0: {
    bg: "bg-foreground/5",
    border: "border-foreground/15",
    text: "text-foreground/70",
    dot: "bg-foreground/40",
  },
  1: {
    bg: "bg-purple-500/8",
    border: "border-purple-500/20",
    text: "text-purple-600",
    dot: "bg-purple-500",
  },
  2: {
    bg: "bg-foreground/8",
    border: "border-foreground/20",
    text: "text-foreground",
    dot: "bg-foreground/70",
  },
};

const SHORT_NAMES: Record<number, string> = {
  0: "Baseline",
  1: "Enhanced",
  2: "Expert",
};

/* ── Animations ─────────────────────────────────────────────── */

const fadeUp = {
  initial: { opacity: 0, y: 16 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: easeOutExpo },
  },
};

/* ── Main Component ─────────────────────────────────────────── */

interface ComparatorContentProps {
  report: ComparisonReport;
}

export function ComparatorContent({ report }: ComparatorContentProps) {
  // Default: compare layer 0 vs layer 2 (or last two available)
  const availableLayers = report.layers.map((l) => l.layer).sort();
  const [leftLayer, setLeftLayer] = useState(availableLayers[0] ?? 0);
  const [rightLayer, setRightLayer] = useState(availableLayers[availableLayers.length - 1] ?? 2);

  const leftResult = report.layers.find((l) => l.layer === leftLayer);
  const rightResult = report.layers.find((l) => l.layer === rightLayer);

  const selectLayer = (side: "left" | "right", layer: number) => {
    if (side === "left") {
      if (layer === rightLayer) {
        // Swap
        setRightLayer(leftLayer);
      }
      setLeftLayer(layer);
    } else {
      if (layer === leftLayer) {
        // Swap
        setLeftLayer(rightLayer);
      }
      setRightLayer(layer);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      {/* ── Layer Selectors ─────────────────────────────────── */}
      <motion.div
        variants={fadeUp}
        initial="initial"
        animate="animate"
        className="grid grid-cols-2 gap-4 shrink-0"
      >
        {/* Left selector */}
        <div>
          <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-2 block">
            Left Panel
          </span>
          <div className="flex gap-1.5">
            {availableLayers.map((layer) => {
              const active = layer === leftLayer;
              const colors = LAYER_COLORS[layer] || LAYER_COLORS[0];
              return (
                <motion.button
                  key={layer}
                  onClick={() => selectLayer("left", layer)}
                  whileHover={{ scale: 1.04 }}
                  whileTap={{ scale: 0.97 }}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-2 rounded-lg border text-xs font-medium transition-colors",
                    active
                      ? `${colors.bg} ${colors.border} ${colors.text}`
                      : "bg-transparent border-foreground/10 text-muted-foreground hover:border-foreground/20"
                  )}
                >
                  <AnimatePresence>
                    {active && (
                      <motion.span
                        initial={{ scale: 0, width: 0 }}
                        animate={{ scale: 1, width: "auto" }}
                        exit={{ scale: 0, width: 0 }}
                        transition={{ type: "spring", stiffness: 500, damping: 25 }}
                      >
                        <Check className="h-3 w-3" />
                      </motion.span>
                    )}
                  </AnimatePresence>
                  {SHORT_NAMES[layer]}
                </motion.button>
              );
            })}
          </div>
        </div>

        {/* Right selector */}
        <div>
          <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-2 block">
            Right Panel
          </span>
          <div className="flex gap-1.5">
            {availableLayers.map((layer) => {
              const active = layer === rightLayer;
              const colors = LAYER_COLORS[layer] || LAYER_COLORS[0];
              return (
                <motion.button
                  key={layer}
                  onClick={() => selectLayer("right", layer)}
                  whileHover={{ scale: 1.04 }}
                  whileTap={{ scale: 0.97 }}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-2 rounded-lg border text-xs font-medium transition-colors",
                    active
                      ? `${colors.bg} ${colors.border} ${colors.text}`
                      : "bg-transparent border-foreground/10 text-muted-foreground hover:border-foreground/20"
                  )}
                >
                  <AnimatePresence>
                    {active && (
                      <motion.span
                        initial={{ scale: 0, width: 0 }}
                        animate={{ scale: 1, width: "auto" }}
                        exit={{ scale: 0, width: 0 }}
                        transition={{ type: "spring", stiffness: 500, damping: 25 }}
                      >
                        <Check className="h-3 w-3" />
                      </motion.span>
                    )}
                  </AnimatePresence>
                  {SHORT_NAMES[layer]}
                </motion.button>
              );
            })}
          </div>
        </div>
      </motion.div>

      {/* ── Side-by-Side Reports ────────────────────────────── */}
      <motion.div
        variants={fadeUp}
        initial="initial"
        animate="animate"
        className="grid grid-cols-2 gap-4"
      >
        {/* Left panel */}
        <AnimatePresence mode="wait">
          <motion.div
            key={`left-${leftLayer}`}
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0, transition: { duration: 0.3, ease: easeOutExpo } }}
            exit={{ opacity: 0, x: -12, transition: { duration: 0.15 } }}
            className="flex flex-col"
          >
            <ReportPanel layer={leftResult} />
          </motion.div>
        </AnimatePresence>

        {/* Right panel */}
        <AnimatePresence mode="wait">
          <motion.div
            key={`right-${rightLayer}`}
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0, transition: { duration: 0.3, ease: easeOutExpo } }}
            exit={{ opacity: 0, x: 12, transition: { duration: 0.15 } }}
            className="flex flex-col"
          >
            <ReportPanel layer={rightResult} />
          </motion.div>
        </AnimatePresence>
      </motion.div>
    </div>
  );
}

/* ── Report Panel ───────────────────────────────────────────── */

function ReportPanel({ layer }: { layer?: { layer: number; content: string; word_count: number; source_count: number } }) {
  if (!layer) {
    return (
      <div className="flex-1 flex items-center justify-center rounded-xl border border-dashed border-foreground/10 text-sm text-muted-foreground">
        Layer not available
      </div>
    );
  }

  const colors = LAYER_COLORS[layer.layer] || LAYER_COLORS[0];

  return (
    <>
      {/* Header */}
      <div className={cn("rounded-t-xl border border-b-0 px-4 py-3 flex items-center justify-between", colors.bg, colors.border)}>
        <div className="flex items-center gap-2">
          <div className={cn("w-2 h-2 rounded-full", colors.dot)} />
          <span className={cn("text-sm font-semibold", colors.text)}>
            {LAYER_NAMES[layer.layer] || `Layer ${layer.layer}`}
          </span>
        </div>
        <div className="flex items-center gap-3 text-[10px] font-mono text-muted-foreground">
          <span>{layer.word_count.toLocaleString()} words</span>
          <span className="w-px h-3 bg-foreground/10" />
          <span>{layer.source_count} sources</span>
        </div>
      </div>

      {/* Scrollable content — each panel scrolls independently */}
      <div className="border border-foreground/10 rounded-b-xl p-5 overflow-y-auto bg-background h-[65vh]">
        {layer.content ? (
          <MarkdownReport content={layer.content} />
        ) : (
          <p className="text-sm text-muted-foreground italic">No content available</p>
        )}
      </div>
    </>
  );
}
