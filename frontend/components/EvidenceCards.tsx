"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";
import {
  ArrowRight,
  ChevronDown,
  AlertTriangle,
  CheckCircle2,
  Columns2,
  Rows3,
  SlidersHorizontal,
  GripVertical,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { highlightDataPoints } from "@/lib/highlight";
import type { ClaimPair } from "@/lib/types";
import { LAYER_NAMES } from "@/lib/types";

// ─── Tag Colors ──────────────────────────────────────────────────────────────

const TAG_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  "+Data Point":       { bg: "bg-cyan-500/15",    text: "text-cyan-700",    border: "border-cyan-500/30" },
  "+Named Source":     { bg: "bg-emerald-500/15",  text: "text-emerald-700",  border: "border-emerald-500/30" },
  "+Specific Company": { bg: "bg-violet-500/15",   text: "text-violet-700",   border: "border-violet-500/30" },
  "+Quantified":       { bg: "bg-amber-500/15",    text: "text-amber-700",    border: "border-amber-500/30" },
  "+Causal Mechanism": { bg: "bg-rose-500/15",     text: "text-rose-700",     border: "border-rose-500/30" },
  "+Time-Bound":       { bg: "bg-blue-500/15",     text: "text-blue-700",     border: "border-blue-500/30" },
};

export function TagBadge({ tag }: { tag: string }) {
  const colors = TAG_COLORS[tag] || { bg: "bg-foreground/5", text: "text-muted-foreground", border: "border-border" };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium",
        colors.bg, colors.text, colors.border
      )}
    >
      {tag}
    </span>
  );
}

// ─── Shared Props ────────────────────────────────────────────────────────────

interface EvidenceCardsProps {
  pairs: ClaimPair[];
  fromLayer: number;
  toLayer: number;
}

// ─── Style A: Transformation Cards (Side-by-Side) ────────────────────────────

function TransformationCards({ pairs, fromLayer, toLayer }: EvidenceCardsProps) {
  return (
    <div className="space-y-4">
      {pairs.map((pair, i) => (
        <div
          key={i}
          className="rounded-xl border border-border bg-background overflow-hidden shadow-sm"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-foreground/5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
              {pair.category}
            </span>
            <div className="flex items-center gap-1.5 flex-wrap justify-end">
              {pair.tags.map((tag, j) => (
                <TagBadge key={j} tag={tag} />
              ))}
            </div>
          </div>

          {/* Side-by-side content */}
          <div className="grid grid-cols-2 divide-x divide-border">
            {/* Baseline (muted) */}
            <div className="p-4 bg-foreground/3">
              <div className="flex items-center gap-1.5 mb-2.5">
                <div className="flex h-5 w-5 items-center justify-center rounded-md bg-foreground/10">
                  <AlertTriangle className="h-3 w-3 text-muted-foreground" />
                </div>
                <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
                  {LAYER_NAMES[fromLayer] || `Layer ${fromLayer}`}
                </span>
              </div>
              <p className="text-[13px] leading-relaxed text-muted-foreground italic">
                &ldquo;{pair.baseline}&rdquo;
              </p>
              <div className="mt-2.5 flex items-center gap-1">
                <AlertTriangle className="h-3 w-3 text-amber-500" />
                <span className="text-[10px] text-amber-600 font-medium">No source &bull; Vague</span>
              </div>
            </div>

            {/* Improved (vibrant) */}
            <div
              className="relative p-4"
              style={{
                background: "linear-gradient(135deg, rgba(6, 182, 212, 0.06), rgba(124, 58, 237, 0.06))",
              }}
            >
              {/* Glow accent bar */}
              <div
                className="absolute top-0 left-0 w-0.75 h-full"
                style={{
                  background: "linear-gradient(to bottom, #06B6D4, #7C3AED)",
                }}
              />
              <div className="flex items-center gap-1.5 mb-2.5 pl-1">
                <div className="flex h-5 w-5 items-center justify-center rounded-md bg-emerald-500/15">
                  <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                </div>
                <span className="text-[10px] font-semibold text-emerald-600 uppercase tracking-wide">
                  {LAYER_NAMES[toLayer] || `Layer ${toLayer}`}
                </span>
              </div>
              <p className="text-[13px] leading-relaxed text-foreground pl-1">
                &ldquo;{highlightDataPoints(pair.improved)}&rdquo;
              </p>
              {pair.source && (
                <div className="mt-2.5 flex items-center gap-1 pl-1">
                  <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                  <span className="text-[10px] text-emerald-700 font-medium">Source: {pair.source}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Style B: Stacked Reveal Cards ───────────────────────────────────────────

function StackedRevealCards({ pairs, fromLayer, toLayer }: EvidenceCardsProps) {
  return (
    <div className="space-y-4">
      {pairs.map((pair, i) => (
        <div
          key={i}
          className="rounded-xl border border-border bg-background p-4 shadow-sm"
        >
          {/* Category + Tags header */}
          <div className="flex items-center justify-between mb-3">
            <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
              {pair.category}
            </span>
            <div className="flex items-center gap-1.5 flex-wrap justify-end">
              {pair.tags.map((tag, j) => (
                <TagBadge key={j} tag={tag} />
              ))}
            </div>
          </div>

          {/* Baseline (faded, with strikethrough hint) */}
          <div className="rounded-lg border border-border bg-foreground/5 p-3 mb-1">
            <div className="flex items-center gap-1.5 mb-1.5">
              <AlertTriangle className="h-3 w-3 text-amber-500" />
              <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
                {LAYER_NAMES[fromLayer] || `Layer ${fromLayer}`}
              </span>
            </div>
            <p className="text-[13px] leading-relaxed text-muted-foreground line-through decoration-muted-foreground/30">
              &ldquo;{pair.baseline}&rdquo;
            </p>
          </div>

          {/* Arrow */}
          <div className="flex items-center justify-center py-1.5">
            <div className="flex items-center gap-1.5 text-muted-foreground/50">
              <ChevronDown className="h-3.5 w-3.5" />
              <span className="text-[9px] font-medium uppercase tracking-widest">
                transformed into
              </span>
              <ChevronDown className="h-3.5 w-3.5" />
            </div>
          </div>

          {/* Improved (glowing) */}
          <div
            className="rounded-lg border p-3"
            style={{
              borderColor: "rgba(6, 182, 212, 0.25)",
              background: "linear-gradient(135deg, rgba(6, 182, 212, 0.06), rgba(124, 58, 237, 0.06))",
              boxShadow: "0 0 20px rgba(6, 182, 212, 0.08), inset 0 0 20px rgba(124, 58, 237, 0.04)",
            }}
          >
            <div className="flex items-center gap-1.5 mb-1.5">
              <CheckCircle2 className="h-3 w-3 text-emerald-600" />
              <span className="text-[10px] font-semibold text-emerald-600 uppercase tracking-wide">
                {LAYER_NAMES[toLayer] || `Layer ${toLayer}`}
              </span>
            </div>
            <p className="text-[13px] leading-relaxed text-foreground">
              &ldquo;{highlightDataPoints(pair.improved)}&rdquo;
            </p>
            {pair.source && (
              <div className="mt-2.5 flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                <span className="text-[10px] text-emerald-700 font-medium">Source: {pair.source}</span>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Style C: Interactive Slider ─────────────────────────────────────────────

function SliderCard({
  pair,
  fromLayer,
  toLayer,
}: {
  pair: ClaimPair;
  fromLayer: number;
  toLayer: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [sliderPos, setSliderPos] = useState(50);
  const isDragging = useRef(false);

  const handleMove = useCallback((clientX: number) => {
    if (!containerRef.current || !isDragging.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const pct = Math.max(15, Math.min(85, (x / rect.width) * 100));
    setSliderPos(pct);
  }, []);

  const handleMouseDown = useCallback(() => {
    isDragging.current = true;
  }, []);

  useEffect(() => {
    const handleMouseUp = () => { isDragging.current = false; };
    const handleMouseMove = (e: MouseEvent) => handleMove(e.clientX);
    const handleTouchMove = (e: TouchEvent) => {
      if (e.touches[0]) handleMove(e.touches[0].clientX);
    };

    window.addEventListener("mouseup", handleMouseUp);
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("touchend", handleMouseUp);
    window.addEventListener("touchmove", handleTouchMove);
    return () => {
      window.removeEventListener("mouseup", handleMouseUp);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("touchend", handleMouseUp);
      window.removeEventListener("touchmove", handleTouchMove);
    };
  }, [handleMove]);

  return (
    <div
      ref={containerRef}
      className="relative rounded-xl border border-border overflow-hidden select-none shadow-sm"
      style={{ minHeight: "160px" }}
    >
      {/* Left: Baseline */}
      <div
        className="absolute inset-0 p-4 bg-foreground/5"
        style={{ clipPath: `inset(0 ${100 - sliderPos}% 0 0)` }}
      >
        <div className="flex items-center gap-1.5 mb-2">
          <AlertTriangle className="h-3 w-3 text-amber-500" />
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
            {LAYER_NAMES[fromLayer] || `Layer ${fromLayer}`}
          </span>
        </div>
        <p className="text-[13px] leading-relaxed text-muted-foreground italic pr-8">
          &ldquo;{pair.baseline}&rdquo;
        </p>
        <div className="mt-2 flex items-center gap-1">
          <AlertTriangle className="h-3 w-3 text-amber-500" />
          <span className="text-[10px] text-amber-600 font-medium">Unsourced</span>
        </div>
      </div>

      {/* Right: Improved */}
      <div
        className="absolute inset-0 p-4"
        style={{
          clipPath: `inset(0 0 0 ${sliderPos}%)`,
          background: "linear-gradient(135deg, rgba(6, 182, 212, 0.06), rgba(124, 58, 237, 0.06))",
        }}
      >
        <div className="flex items-center gap-1.5 mb-2">
          <CheckCircle2 className="h-3 w-3 text-emerald-600" />
          <span className="text-[10px] font-semibold text-emerald-600 uppercase tracking-wide">
            {LAYER_NAMES[toLayer] || `Layer ${toLayer}`}
          </span>
        </div>
        <p className="text-[13px] leading-relaxed text-foreground pl-8">
          &ldquo;{highlightDataPoints(pair.improved)}&rdquo;
        </p>
        {pair.source && (
          <div className="mt-2 flex items-center gap-1">
            <CheckCircle2 className="h-3 w-3 text-emerald-600" />
            <span className="text-[10px] text-emerald-700 font-medium">Source: {pair.source}</span>
          </div>
        )}
      </div>

      {/* Slider handle */}
      <div
        className="absolute top-0 bottom-0 z-10 cursor-col-resize flex items-center"
        style={{ left: `${sliderPos}%`, transform: "translateX(-50%)" }}
        onMouseDown={handleMouseDown}
        onTouchStart={handleMouseDown}
      >
        <div className="w-0.5 h-full bg-linear-to-b from-cyan-400 via-purple-500 to-cyan-400 opacity-70" />
        <div className="absolute top-1/2 -translate-y-1/2 left-1/2 -translate-x-1/2 flex h-8 w-6 items-center justify-center rounded-md bg-background border border-border shadow-lg">
          <GripVertical className="h-3.5 w-3.5 text-muted-foreground" />
        </div>
      </div>
    </div>
  );
}

function InteractiveSlider({ pairs, fromLayer, toLayer }: EvidenceCardsProps) {
  const [activePair, setActivePair] = useState(0);

  return (
    <div className="space-y-3">
      {/* Claim selector */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {pairs.map((pair, i) => (
          <button
            key={i}
            onClick={() => setActivePair(i)}
            className={cn(
              "shrink-0 rounded-lg border px-3 py-1.5 text-[10px] font-medium transition-all",
              i === activePair
                ? "border-cyan-500/40 bg-cyan-500/10 text-cyan-700"
                : "border-border bg-foreground/5 text-muted-foreground hover:text-foreground"
            )}
          >
            {pair.category}
          </button>
        ))}
      </div>

      {/* Tags for active pair */}
      <div className="flex items-center gap-1.5">
        {pairs[activePair]?.tags.map((tag, j) => (
          <TagBadge key={j} tag={tag} />
        ))}
      </div>

      {/* Slider */}
      {pairs[activePair] && (
        <SliderCard
          pair={pairs[activePair]}
          fromLayer={fromLayer}
          toLayer={toLayer}
        />
      )}

      <p className="text-center text-[10px] text-muted-foreground/60">
        Drag the slider to compare layers
      </p>
    </div>
  );
}

// ─── Style Toggle + Main Export ──────────────────────────────────────────────

type EvidenceStyle = "transformation" | "stacked" | "slider";

const STYLE_OPTIONS: { id: EvidenceStyle; icon: React.ElementType; label: string }[] = [
  { id: "transformation", icon: Columns2, label: "Side by Side" },
  { id: "stacked", icon: Rows3, label: "Stacked" },
  { id: "slider", icon: SlidersHorizontal, label: "Slider" },
];

export function EvidenceCards({ pairs, fromLayer, toLayer }: EvidenceCardsProps) {
  const [style, setStyle] = useState<EvidenceStyle>("transformation");

  if (!pairs || pairs.length === 0) return null;

  return (
    <div className="space-y-4">
      {/* Header + Style toggle */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-foreground">
            Claim Transformations
          </h3>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            Real examples showing how each claim improved across layers
          </p>
        </div>
        <div className="flex items-center rounded-lg border border-border bg-foreground/5 p-0.5">
          {STYLE_OPTIONS.map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              onClick={() => setStyle(id)}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[10px] font-medium transition-all",
                style === id
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
              title={label}
            >
              <Icon className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">{label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Render selected style */}
      {style === "transformation" && (
        <TransformationCards pairs={pairs} fromLayer={fromLayer} toLayer={toLayer} />
      )}
      {style === "stacked" && (
        <StackedRevealCards pairs={pairs} fromLayer={fromLayer} toLayer={toLayer} />
      )}
      {style === "slider" && (
        <InteractiveSlider pairs={pairs} fromLayer={fromLayer} toLayer={toLayer} />
      )}
    </div>
  );
}
