"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  Search,
  Target,
  Sparkles,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Globe,
  CheckCircle2,
  Lightbulb,
  GitMerge,
  MapPin,
  Scissors,
  ArrowRight,
  ShieldAlert,
  FileText,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { highlightDataPoints } from "@/lib/highlight";
import { extractAgentWorkflow } from "@/lib/extract-agent-steps";
import type {
  ComparisonReport,
  AgentWorkflowData,
  SearchToolCall,
  EvidenceEntry,
} from "@/lib/types";

// ─── Framer Motion Variants ────────────────────────────────────────────────

const easeOutExpo: [number, number, number, number] = [0.22, 1, 0.36, 1];
const easeOutBack: [number, number, number, number] = [0.34, 1.56, 0.64, 1];

const stepFadeVariants = {
  initial: (direction: number) => ({
    opacity: 0,
    y: direction > 0 ? 30 : -30,
    scale: 0.97,
    filter: "blur(4px)",
  }),
  animate: {
    opacity: 1,
    y: 0,
    scale: 1,
    filter: "blur(0px)",
    transition: { duration: 0.5, ease: easeOutExpo },
  },
  exit: (direction: number) => ({
    opacity: 0,
    y: direction > 0 ? -20 : 20,
    scale: 0.97,
    filter: "blur(4px)",
    transition: { duration: 0.35, ease: easeOutExpo },
  }),
};

const staggerContainer = {
  animate: {
    transition: { staggerChildren: 0.06, delayChildren: 0.15 },
  },
};

const staggerChild = {
  initial: { opacity: 0, y: 16, scale: 0.97 },
  animate: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.4, ease: easeOutExpo },
  },
};

const popIn = {
  initial: { opacity: 0, scale: 0.8 },
  animate: (i: number) => ({
    opacity: 1,
    scale: 1,
    transition: {
      delay: i * 0.06,
      duration: 0.35,
      ease: easeOutBack,
    },
  }),
};

const slideInLeft = {
  initial: { opacity: 0, x: -20 },
  animate: (i: number) => ({
    opacity: 1,
    x: 0,
    transition: {
      delay: i * 0.07,
      duration: 0.4,
      ease: easeOutExpo,
    },
  }),
};

const headerVariants = {
  initial: { opacity: 0, y: -8 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.35, ease: easeOutExpo },
  },
  exit: {
    opacity: 0,
    y: 8,
    transition: { duration: 0.2 },
  },
};

// ─── Step Config ─────────────────────────────────────────────────────────────

interface StepConfig {
  id: string;
  label: string;
  sublabel: string;
  icon: typeof Search;
  bg: [number, number, number, number];
  dotColor: string;
}

const ALL_STEPS: StepConfig[] = [
  { id: "baseline", label: "THE FOG", sublabel: "Baseline — Model Knowledge", icon: AlertTriangle, bg: [217, 119, 6, 0.04], dotColor: "bg-amber-500" },
  { id: "search", label: "THE SEARCH", sublabel: "Web Research Agent", icon: Search, bg: [124, 58, 237, 0.05], dotColor: "bg-purple" },
  { id: "l1-result", label: "THE DISCOVERY", sublabel: "Enhanced Report", icon: CheckCircle2, bg: [5, 150, 105, 0.04], dotColor: "bg-green-500" },
  { id: "dissect", label: "THE DISSECTION", sublabel: "Claim Analysis", icon: Scissors, bg: [217, 119, 6, 0.05], dotColor: "bg-amber-500" },
  { id: "plan", label: "THE STRATEGY", sublabel: "Research Planning", icon: MapPin, bg: [59, 130, 246, 0.04], dotColor: "bg-blue-500" },
  { id: "investigate", label: "THE INVESTIGATION", sublabel: "Evidence Gathering", icon: Target, bg: [124, 58, 237, 0.06], dotColor: "bg-purple" },
  { id: "synthesize", label: "THE SYNTHESIS", sublabel: "Cross-Referencing", icon: GitMerge, bg: [15, 10, 30, 0.06], dotColor: "bg-foreground" },
  { id: "expert-result", label: "THE EXPERT REPORT", sublabel: "Agentic Pipeline Output", icon: FileText, bg: [5, 150, 105, 0.05], dotColor: "bg-emerald-500" },
  { id: "result", label: "THE TRANSFORMATION", sublabel: "Final Result", icon: Sparkles, bg: [124, 58, 237, 0.07], dotColor: "bg-purple" },
];

const EVIDENCE_TYPE_COLORS: Record<string, string> = {
  confirms: "evidence-bar-confirms",
  supports: "evidence-bar-supports",
  contradicts: "evidence-bar-contradicts",
  extends: "evidence-bar-extends",
  quantifies: "evidence-bar-quantifies",
};

// ─── Helpers ────────────────────────────────────────────────────────────────

function safeDomain(url: string): string {
  try { return new URL(url).hostname.replace("www.", ""); }
  catch { return url; }
}

function lerpRgba(a: [number, number, number, number], b: [number, number, number, number], t: number): string {
  const r = Math.round(a[0] + (b[0] - a[0]) * t);
  const g = Math.round(a[1] + (b[1] - a[1]) * t);
  const bl = Math.round(a[2] + (b[2] - a[2]) * t);
  const al = a[3] + (b[3] - a[3]) * t;
  return `rgba(${r},${g},${bl},${al.toFixed(3)})`;
}

function firstSentences(text: string, n = 2): string {
  const sentences = text.match(/[^.!?]+[.!?]+/g);
  if (!sentences) return text.slice(0, 200);
  return sentences.slice(0, n).join(" ").trim();
}

// ─── AnimatedCounter ────────────────────────────────────────────────────────

function AnimatedCounter({ value, duration = 1200, suffix = "" }: { value: number; duration?: number; suffix?: string }) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    const start = performance.now();
    let animId: number;
    const animate = (now: number) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(value * eased));
      if (progress < 1) animId = requestAnimationFrame(animate);
    };
    animId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animId);
  }, [value, duration]);
  return <span>{display.toLocaleString()}{suffix}</span>;
}

// ─── MetricCard ─────────────────────────────────────────────────────────────

function MetricCard({ label, value, accent, small }: { label: string; value: number; accent?: "amber" | "green"; small?: boolean }) {
  const colorClass = accent === "amber" ? "text-amber-600" : accent === "green" ? "text-green-600" : "";
  return (
    <div className={cn("rounded-xl bg-foreground/3 text-center", small ? "p-2" : "p-4 flex-1")}>
      <div className={cn("font-display", colorClass, small ? "text-lg" : "text-2xl")}>{value.toLocaleString()}</div>
      <div className={cn("font-mono text-muted-foreground uppercase", small ? "text-[8px]" : "text-[10px] mt-1")}>{label}</div>
    </div>
  );
}

// ─── EvidenceCard ───────────────────────────────────────────────────────────

function EvidenceCard({ entry, index, claimText }: { entry: EvidenceEntry; index: number; claimText?: string }) {
  const barClass = EVIDENCE_TYPE_COLORS[entry.evidence_type] || "evidence-bar-supports";
  return (
    <div className={cn("glass-card p-3 data-point-pop", barClass)} style={{ animationDelay: `${index * 60}ms` }}>
      {claimText && (
        <p className="text-[10px] font-mono text-muted-foreground/60 mb-1 truncate">
          Claim: {claimText}
        </p>
      )}
      <p className="text-sm mb-1">{entry.fact}</p>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="inline-flex items-center gap-1 text-[10px] font-mono text-muted-foreground">
          <ExternalLink className="h-2.5 w-2.5" />
          {entry.source_title || safeDomain(entry.source_url)}
        </span>
        <span className={cn(
          "px-1.5 py-0.5 rounded text-[9px] font-mono",
          entry.evidence_type === "confirms" || entry.evidence_type === "supports"
            ? "bg-green-500/10 text-green-700"
            : entry.evidence_type === "contradicts"
            ? "bg-red-500/10 text-red-700"
            : "bg-purple/10 text-purple"
        )}>
          {entry.evidence_type}
        </span>
        {entry.confidence && (
          <span className="flex items-center gap-1 text-[9px] font-mono text-muted-foreground">
            <span className={cn("w-1.5 h-1.5 rounded-full",
              entry.confidence === "high" ? "bg-green-500" : entry.confidence === "medium" ? "bg-amber-500" : "bg-red-500"
            )} />
            {entry.confidence}
          </span>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// STEP 0 — THE FOG (Baseline)
// ═══════════════════════════════════════════════════════════════════════════

function StepBaseline({ report, workflow }: { report: ComparisonReport; workflow: AgentWorkflowData }) {
  const claimText = report.claim_journey?.snapshots?.find(s => s.layer === 0)?.claim_text
    || firstSentences(report.layers[0]?.content || "", 2);
  const warnings = ["Unsourced", "No Data", "Vague"];

  return (
    <motion.div
      className="flex flex-col items-center justify-center gap-8 relative max-w-2xl mx-auto w-full"
      variants={staggerContainer}
      initial="initial"
      animate="animate"
    >
      <div className="absolute inset-0 fog-overlay bg-amber-100/30 rounded-3xl pointer-events-none" />
      <motion.div className="relative z-10 max-w-2xl w-full" variants={staggerChild}>
        <div className="glass-card p-8 lg:p-10 border border-amber-500/20">
          <div className="flex items-center gap-2 mb-6">
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 flex items-center justify-center">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
            </div>
            <div>
              <p className="text-[10px] font-mono uppercase tracking-widest text-amber-600">The Raw Claim</p>
              <p className="text-xs text-muted-foreground">Baseline — Model Knowledge</p>
            </div>
          </div>
          <blockquote className="text-lg lg:text-xl font-display italic text-foreground/70 leading-relaxed border-l-2 border-amber-500/30 pl-5 mb-6">
            &ldquo;{claimText}&rdquo;
          </blockquote>
          <div className="flex flex-wrap gap-2 mb-6">
            {warnings.map((w, i) => (
              <motion.span
                key={w}
                variants={popIn}
                custom={i}
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono bg-amber-500/10 text-amber-700"
              >
                <AlertTriangle className="h-3 w-3" />{w}
              </motion.span>
            ))}
          </div>
          <div className="flex items-center gap-4 text-xs font-mono text-muted-foreground pt-4 border-t border-foreground/5">
            <span>No searches. No sources. No verification.</span>
          </div>
        </div>
      </motion.div>
      <motion.div className="relative z-10 flex gap-6 text-center" variants={staggerChild}>
        <div>
          <div className="text-2xl font-display">{workflow.baseline.wordCount.toLocaleString()}</div>
          <div className="text-[10px] font-mono text-muted-foreground uppercase">words</div>
        </div>
        <div className="w-px bg-foreground/10" />
        <div>
          <div className="text-2xl font-display">{workflow.baseline.sourceCount}</div>
          <div className="text-[10px] font-mono text-muted-foreground uppercase">sources</div>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// STEP 1 — THE SEARCH (L1 Web Research)
// ═══════════════════════════════════════════════════════════════════════════

function StepSearch({ workflow }: { workflow: AgentWorkflowData }) {
  const [showAll, setShowAll] = useState(false);
  const enhanced = workflow.enhanced;
  if (!enhanced) return <p className="text-muted-foreground text-center">No search data available.</p>;

  const searches = enhanced.searches;
  const visibleSearches = showAll ? searches : searches.slice(0, 5);
  const hiddenCount = searches.length - 5;

  return (
    <motion.div
      className="max-w-2xl w-full mx-auto space-y-6 overflow-y-auto max-h-full"
      variants={staggerContainer}
      initial="initial"
      animate="animate"
    >
      {/* Stats banner */}
      <motion.div className="glass-card p-4 flex items-center justify-center gap-6 text-center" variants={staggerChild}>
        <div>
          <div className="text-2xl font-mono font-semibold text-purple"><AnimatedCounter value={enhanced.totalSearches} /></div>
          <div className="text-[10px] font-mono text-muted-foreground uppercase">searches</div>
        </div>
        <div className="w-px h-8 bg-foreground/10" />
        <div>
          <div className="text-2xl font-mono font-semibold text-purple"><AnimatedCounter value={enhanced.totalScrapes} /></div>
          <div className="text-[10px] font-mono text-muted-foreground uppercase">scraped</div>
        </div>
        <div className="w-px h-8 bg-foreground/10" />
        <div>
          <div className="text-2xl font-mono font-semibold text-purple"><AnimatedCounter value={enhanced.sourcesFound} /></div>
          <div className="text-[10px] font-mono text-muted-foreground uppercase">sources</div>
        </div>
      </motion.div>

      {/* Search timeline */}
      <motion.div className="relative" variants={staggerChild}>
        <p className="text-xs font-mono uppercase tracking-wider text-muted-foreground mb-4">Search Timeline</p>
        <div className="absolute left-4 top-10 bottom-0 w-px bg-purple/20" />
        <div className="space-y-3">
          {visibleSearches.map((search, i) => (
            <motion.div
              key={i}
              className="relative pl-10"
              variants={slideInLeft}
              custom={i}
              initial="initial"
              animate="animate"
            >
              <div className="absolute left-2.5 top-3 w-3 h-3 rounded-full bg-purple/30 border-2 border-purple" />
              <div className="glass-card p-3">
                <div className="flex items-center gap-2 mb-1.5">
                  <Search className="h-3.5 w-3.5 text-purple" />
                  <span className="text-sm font-mono flex-1 truncate">{search.query}</span>
                  {search.results > 0 && (
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-purple/10 text-purple shrink-0">{search.results} hits</span>
                  )}
                </div>
                {search.hits && search.hits.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-1.5">
                    {search.hits.slice(0, 3).map((hit, j) => (
                      <span key={j} className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-foreground/3 text-muted-foreground" title={hit.title}>
                        <Globe className="h-2.5 w-2.5" />{safeDomain(hit.url)}
                      </span>
                    ))}
                    {search.hits.length > 3 && <span className="text-[10px] text-muted-foreground px-2 py-0.5">+{search.hits.length - 3} more</span>}
                  </div>
                )}
              </div>
            </motion.div>
          ))}
        </div>
        {hiddenCount > 0 && (
          <button onClick={() => setShowAll(!showAll)} className="ml-10 mt-3 text-xs font-mono text-purple hover:text-purple-light transition-colors flex items-center gap-1">
            {showAll ? <><ChevronUp className="h-3 w-3" /> Show less</> : <><ChevronDown className="h-3 w-3" /> Show {hiddenCount} more queries</>}
          </button>
        )}
      </motion.div>
    </motion.div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// STEP 2 — THE DISCOVERY (L1 Result)
// ═══════════════════════════════════════════════════════════════════════════

function StepL1Result({ report, workflow }: { report: ComparisonReport; workflow: AgentWorkflowData }) {
  const l1 = report.layers?.[1];
  if (!l1) return <p className="text-muted-foreground text-center">No enhanced layer data.</p>;

  const claimText = report.claim_journey?.snapshots?.find(s => s.layer === 1)?.claim_text
    || firstSentences(l1.content || "", 3);
  const dataPoints = report.claim_journey?.snapshots?.find(s => s.layer === 1)?.data_points || [];
  const l0Words = report.layers[0]?.word_count ?? 0;

  return (
    <motion.div
      className="max-w-2xl w-full mx-auto space-y-6"
      variants={staggerContainer}
      initial="initial"
      animate="animate"
    >
      {/* Improvement metrics */}
      <motion.div className="glass-card p-4 flex items-center justify-center gap-6 text-center" variants={staggerChild}>
        <div>
          <div className="text-xl font-mono font-semibold text-green-600">
            {l0Words > 0 ? `+${Math.round(((l1.word_count - l0Words) / l0Words) * 100)}%` : l1.word_count.toLocaleString()}
          </div>
          <div className="text-[10px] font-mono text-muted-foreground uppercase">word growth</div>
        </div>
        <div className="w-px h-8 bg-foreground/10" />
        <div>
          <div className="text-xl font-mono font-semibold text-green-600">{l1.source_count}</div>
          <div className="text-[10px] font-mono text-muted-foreground uppercase">sources found</div>
        </div>
        <div className="w-px h-8 bg-foreground/10" />
        <div>
          <div className="text-xl font-mono font-semibold text-green-600">{l1.word_count.toLocaleString()}</div>
          <div className="text-[10px] font-mono text-muted-foreground uppercase">total words</div>
        </div>
      </motion.div>

      {/* Enhanced claim */}
      <motion.div className="glass-card p-6 lg:p-8 border border-green-500/20" variants={staggerChild}>
        <div className="flex items-center gap-2 mb-4">
          <div className="w-8 h-8 rounded-lg bg-green-500/10 flex items-center justify-center">
            <CheckCircle2 className="h-4 w-4 text-green-600" />
          </div>
          <div>
            <p className="text-[10px] font-mono uppercase tracking-widest text-green-600">Enhanced Output</p>
            <p className="text-xs text-muted-foreground">Web-enriched with real data</p>
          </div>
        </div>
        <p className="text-base leading-relaxed border-l-2 border-green-500/30 pl-5 mb-4">
          {highlightDataPoints(claimText)}
        </p>
        <div className="flex flex-wrap gap-2">
          {["+Web Sources", "+Data Points", "+Verified Claims"].map(tag => (
            <span key={tag} className="px-2 py-0.5 rounded text-[10px] bg-green-500/10 text-green-700">{tag}</span>
          ))}
        </div>
      </motion.div>

      {/* Data points discovered */}
      {dataPoints.length > 0 && (
        <motion.div className="flex flex-wrap gap-2 justify-center" variants={staggerChild}>
          {dataPoints.map((dp, i) => (
            <motion.span
              key={i}
              variants={popIn}
              custom={i}
              className="px-3 py-1 rounded-full text-sm font-mono bg-purple/5 border border-purple/10"
            >
              {highlightDataPoints(dp)}
            </motion.span>
          ))}
        </motion.div>
      )}
    </motion.div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// STEP 3 — THE DISSECTION (Expert Claim Analysis)
// ═══════════════════════════════════════════════════════════════════════════

function StepDissect({ workflow }: { workflow: AgentWorkflowData }) {
  const [expandedSection, setExpandedSection] = useState<string | null>(null);
  const expert = workflow.expert;
  if (!expert) return <p className="text-muted-foreground text-center">No expert data available.</p>;

  const claimMap = expert.claimMap;
  if (claimMap.length === 0) {
    // Fallback: show summary from phase details
    const dissectPhase = expert.phaseDetails.find(p => p.phase === "dissect");
    return (
      <div className="max-w-2xl mx-auto w-full text-center space-y-4">
        <div className="glass-card p-6">
          <p className="text-sm font-medium mb-4">Claim Analysis Summary</p>
          <div className="flex gap-4 justify-center">
            <MetricCard label="Claims Found" value={dissectPhase?.claims_total ?? 0} />
            <MetricCard label="Need Research" value={dissectPhase?.claims_weak ?? 0} accent="amber" />
          </div>
        </div>
      </div>
    );
  }

  const totalClaims = claimMap.reduce((s, sec) => s + sec.claims.length, 0);
  const weakClaims = claimMap.reduce((s, sec) => s + sec.claims.filter(c => c.needs_research).length, 0);

  const qualityColor = (q: string) => {
    if (q === "strong") return "claim-strong";
    if (q === "weak") return "claim-weak";
    if (q === "unsupported") return "claim-unsupported";
    return "claim-stale";
  };

  return (
    <motion.div
      className="max-w-2xl w-full mx-auto space-y-4 overflow-y-auto max-h-full"
      variants={staggerContainer}
      initial="initial"
      animate="animate"
    >
      {/* Summary bar */}
      <motion.div className="glass-card p-4 flex items-center justify-between" variants={staggerChild}>
        <div className="text-sm">
          <span className="font-semibold text-amber-600">{weakClaims}</span>
          <span className="text-muted-foreground"> of {totalClaims} claims need research</span>
        </div>
        <div className="h-2 w-32 rounded-full bg-foreground/5 overflow-hidden">
          <motion.div
            className="h-full rounded-full bg-linear-to-r from-green-500 to-amber-500"
            initial={{ width: 0 }}
            animate={{ width: `${totalClaims > 0 ? ((totalClaims - weakClaims) / totalClaims) * 100 : 0}%` }}
            transition={{ duration: 1, ease: easeOutExpo, delay: 0.3 }}
          />
        </div>
      </motion.div>

      {/* Sections */}
      {claimMap.map((section, si) => {
        const isExpanded = expandedSection === section.section;
        return (
          <motion.div key={si} className="glass-card overflow-hidden" variants={staggerChild}>
            <button
              onClick={() => setExpandedSection(isExpanded ? null : section.section)}
              className="w-full p-4 flex items-center justify-between text-left hover:bg-foreground/2 transition-colors"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{section.section}</p>
                {section.thesis && <p className="text-xs text-muted-foreground truncate mt-0.5">{section.thesis}</p>}
              </div>
              <div className="flex items-center gap-2 ml-3 shrink-0">
                <span className={cn("px-2 py-0.5 rounded text-[10px] font-mono border", qualityColor(section.overall_quality))}>
                  {section.overall_quality}
                </span>
                <span className="text-xs text-muted-foreground">{section.claims.length} claims</span>
                <motion.div animate={{ rotate: isExpanded ? 180 : 0 }} transition={{ duration: 0.25 }}>
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                </motion.div>
              </div>
            </button>

            <AnimatePresence>
              {isExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.3, ease: easeOutExpo }}
                  className="overflow-hidden"
                >
                  <div className="px-4 pb-4 space-y-2 border-t border-foreground/5 pt-3">
                    {section.claims.map((claim, ci) => (
                      <motion.div
                        key={ci}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: ci * 0.05, duration: 0.3 }}
                        className={cn("p-3 rounded-lg border text-sm", qualityColor(claim.evidence_quality))}
                      >
                        <div className="flex items-start gap-2">
                          <span className="text-[9px] font-mono text-muted-foreground shrink-0 mt-1">[{claim.id}]</span>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm">{claim.text}</p>
                            {claim.reasoning && (
                              <p className="text-xs text-muted-foreground/70 mt-1 italic">
                                Why: {claim.reasoning}
                              </p>
                            )}
                          </div>
                          <span className={cn("px-1.5 py-0.5 rounded text-[9px] font-mono shrink-0", qualityColor(claim.evidence_quality))}>
                            {claim.evidence_quality}
                          </span>
                        </div>
                      </motion.div>
                    ))}
                    {section.missing_angles.length > 0 && (
                      <div className="mt-2 p-2 rounded bg-amber-500/5">
                        <p className="text-[10px] font-mono text-amber-600 uppercase mb-1">Missing Angles</p>
                        <ul className="text-xs text-muted-foreground space-y-0.5">
                          {section.missing_angles.map((angle, ai) => <li key={ai}>• {angle}</li>)}
                        </ul>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        );
      })}
    </motion.div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// STEP 4 — THE STRATEGY (Research Planning)
// ═══════════════════════════════════════════════════════════════════════════

function StepPlan({ workflow }: { workflow: AgentWorkflowData }) {
  const [showAll, setShowAll] = useState(false);
  const expert = workflow.expert;

  // Build claim text lookup — must be before any conditional returns (Rules of Hooks)
  const claimTextMap = useMemo(() => {
    const map: Record<string, string> = {};
    if (expert) {
      for (const sec of expert.claimMap) {
        for (const c of sec.claims) {
          map[c.id] = c.text;
        }
      }
    }
    return map;
  }, [expert]);

  if (!expert) return <p className="text-muted-foreground text-center">No expert data available.</p>;

  const tasks = expert.researchTasks;
  if (tasks.length === 0) {
    const planPhase = expert.phaseDetails.find(p => p.phase === "plan");
    return (
      <div className="max-w-2xl mx-auto w-full text-center space-y-4">
        <div className="glass-card p-6">
          <p className="text-sm font-medium mb-4">Research Plan Summary</p>
          <div className="flex gap-4 justify-center">
            <MetricCard label="Sections" value={planPhase?.sections ?? expert.planSections.length} />
            <MetricCard label="Queries Planned" value={planPhase?.questions ?? 0} />
          </div>
        </div>
      </div>
    );
  }

  const visibleTasks = showAll ? tasks : tasks.slice(0, 5);
  const hiddenCount = tasks.length - 5;
  const totalQueries = tasks.reduce((s, t) => s + t.queries.length, 0);

  const priorityClass = (p: number) => {
    if (p === 1) return "bg-red-500/10 text-red-700";
    if (p === 2) return "bg-amber-500/10 text-amber-700";
    return "bg-blue-500/10 text-blue-700";
  };

  return (
    <motion.div
      className="max-w-2xl w-full mx-auto space-y-4 overflow-y-auto max-h-full"
      variants={staggerContainer}
      initial="initial"
      animate="animate"
    >
      {/* Summary */}
      <motion.div className="glass-card p-4 flex items-center justify-center gap-6 text-center" variants={staggerChild}>
        <div>
          <div className="text-xl font-mono font-semibold text-blue-600">{tasks.length}</div>
          <div className="text-[10px] font-mono text-muted-foreground uppercase">research tasks</div>
        </div>
        <div className="w-px h-8 bg-foreground/10" />
        <div>
          <div className="text-xl font-mono font-semibold text-blue-600">{totalQueries}</div>
          <div className="text-[10px] font-mono text-muted-foreground uppercase">search queries</div>
        </div>
        <div className="w-px h-8 bg-foreground/10" />
        <div>
          <div className="text-xl font-mono font-semibold text-blue-600">{expert.planSections.length}</div>
          <div className="text-[10px] font-mono text-muted-foreground uppercase">sections covered</div>
        </div>
      </motion.div>

      {/* Tasks */}
      {visibleTasks.map((task, i) => (
        <motion.div
          key={i}
          className="glass-card p-4"
          variants={popIn}
          custom={i}
          initial="initial"
          animate="animate"
        >
          <div className="flex items-start gap-3">
            <span className={cn("px-1.5 py-0.5 rounded text-[9px] font-mono shrink-0 mt-0.5", priorityClass(task.priority))}>
              P{task.priority}
            </span>
            <div className="flex-1 min-w-0 space-y-2">
              {claimTextMap[task.claim_id] && (
                <p className="text-xs text-muted-foreground/60 truncate">
                  <span className="font-mono">[{task.claim_id}]</span> {claimTextMap[task.claim_id]}
                </p>
              )}
              <p className="text-sm">
                <span className="text-muted-foreground">Why: </span>{task.rationale}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {task.queries.map((q, qi) => (
                  <span key={qi} className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono bg-blue-500/5 border border-blue-500/10 text-muted-foreground">
                    <Search className="h-2.5 w-2.5" />{q}
                  </span>
                ))}
              </div>
              <div className="flex flex-wrap gap-2 text-[10px] text-muted-foreground">
                {task.expected_evidence && (
                  <span className="font-mono">Expects: {task.expected_evidence}</span>
                )}
                {task.target_sources.length > 0 && (
                  <span className="font-mono">Targets: {task.target_sources.join(", ")}</span>
                )}
              </div>
            </div>
          </div>
        </motion.div>
      ))}

      {hiddenCount > 0 && (
        <button onClick={() => setShowAll(!showAll)} className="text-xs font-mono text-blue-600 hover:text-blue-500 transition-colors flex items-center gap-1 mx-auto">
          {showAll ? <><ChevronUp className="h-3 w-3" /> Show less</> : <><ChevronDown className="h-3 w-3" /> Show {hiddenCount} more tasks</>}
        </button>
      )}
    </motion.div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// STEP 5 — THE INVESTIGATION (Evidence Gathering)
// ═══════════════════════════════════════════════════════════════════════════

function StepInvestigate({ workflow }: { workflow: AgentWorkflowData }) {
  const [showAllEvidence, setShowAllEvidence] = useState(false);
  const expert = workflow.expert;

  // Build claim text lookup — must be before any conditional returns (Rules of Hooks)
  const claimTextMap = useMemo(() => {
    const map: Record<string, string> = {};
    if (expert) {
      for (const sec of expert.claimMap) {
        for (const c of sec.claims) {
          map[c.id] = c.text;
        }
      }
    }
    return map;
  }, [expert]);

  if (!expert) return <p className="text-muted-foreground text-center">No expert data available.</p>;

  const invPhase = expert.phaseDetails.find(p => p.phase === "investigate");
  const evidenceSlice = showAllEvidence ? expert.evidenceLedger : expert.evidenceLedger.slice(0, 5);
  const hiddenEvidence = expert.evidenceLedger.length - 5;

  return (
    <motion.div
      className="max-w-2xl w-full mx-auto space-y-5 overflow-y-auto max-h-full"
      variants={staggerContainer}
      initial="initial"
      animate="animate"
    >
      {/* Coverage bar */}
      <motion.div variants={staggerChild}>
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-mono text-muted-foreground">Claim Coverage</span>
          <span className="text-xs font-mono font-semibold">{Math.round(expert.coverage * 100)}%</span>
        </div>
        <div className="h-2.5 rounded-full bg-foreground/5 overflow-hidden">
          <motion.div
            className="h-full rounded-full"
            style={{ background: "linear-gradient(90deg, #D97706, #059669)" }}
            initial={{ width: 0 }}
            animate={{ width: `${expert.coverage * 100}%` }}
            transition={{ duration: 1.2, ease: easeOutExpo, delay: 0.3 }}
          />
        </div>
        {expert.gapFillPasses > 0 && expert.coverageBeforeGapFill != null && (
          <p className="text-[10px] font-mono text-muted-foreground mt-1">
            Coverage improved from {Math.round(expert.coverageBeforeGapFill * 100)}% to {Math.round(expert.coverage * 100)}% after {expert.gapFillPasses} gap-fill pass{expert.gapFillPasses > 1 ? "es" : ""}
          </p>
        )}
      </motion.div>

      {/* Stats grid */}
      <motion.div className="grid grid-cols-4 gap-2" variants={staggerChild}>
        <MetricCard label="Searches" value={invPhase?.searches ?? 0} small />
        <MetricCard label="Scraped" value={invPhase?.scrapes ?? 0} small />
        <MetricCard label="Findings" value={invPhase?.facts ?? expert.evidenceLedger.length} small />
        <MetricCard label="Sources" value={invPhase?.sources ?? 0} small />
      </motion.div>

      {/* Evidence ledger */}
      {expert.evidenceLedger.length > 0 && (
        <motion.div className="space-y-2" variants={staggerChild}>
          <p className="text-xs font-mono uppercase tracking-wider text-muted-foreground">Evidence Found</p>
          {evidenceSlice.map((entry, i) => (
            <motion.div key={i} variants={slideInLeft} custom={i} initial="initial" animate="animate">
              <EvidenceCard
                entry={entry}
                index={i}
                claimText={claimTextMap[entry.claim_id] ? `[${entry.claim_id}] ${claimTextMap[entry.claim_id].slice(0, 60)}...` : undefined}
              />
            </motion.div>
          ))}
          {hiddenEvidence > 0 && (
            <button onClick={() => setShowAllEvidence(!showAllEvidence)} className="text-xs font-mono text-purple hover:text-purple-light transition-colors flex items-center gap-1">
              {showAllEvidence ? <><ChevronUp className="h-3 w-3" /> Show less</> : <><ChevronDown className="h-3 w-3" /> +{hiddenEvidence} more entries</>}
            </button>
          )}
        </motion.div>
      )}
    </motion.div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// STEP 6 — THE SYNTHESIS (Cross-Referencing)
// ═══════════════════════════════════════════════════════════════════════════

function StepSynthesize({ workflow }: { workflow: AgentWorkflowData }) {
  const expert = workflow.expert;
  if (!expert) return <p className="text-muted-foreground text-center">No expert data available.</p>;

  return (
    <motion.div
      className="max-w-2xl w-full mx-auto space-y-5 overflow-y-auto max-h-full"
      variants={staggerContainer}
      initial="initial"
      animate="animate"
    >
      {/* Summary stats */}
      <motion.div className="glass-card p-4 flex items-center justify-center gap-6 text-center" variants={staggerChild}>
        <div>
          <div className="text-xl font-mono font-semibold">{expert.crossLinks.length}</div>
          <div className="text-[10px] font-mono text-muted-foreground uppercase">cross-links</div>
        </div>
        <div className="w-px h-8 bg-foreground/10" />
        <div>
          <div className="text-xl font-mono font-semibold">{expert.insights.length}</div>
          <div className="text-[10px] font-mono text-muted-foreground uppercase">insights</div>
        </div>
        <div className="w-px h-8 bg-foreground/10" />
        <div>
          <div className="text-xl font-mono font-semibold">{expert.contrarianRisks.length}</div>
          <div className="text-[10px] font-mono text-muted-foreground uppercase">risks</div>
        </div>
        {expert.gapReport.length > 0 && (
          <>
            <div className="w-px h-8 bg-foreground/10" />
            <div>
              <div className="text-xl font-mono font-semibold text-amber-600">{expert.gapReport.length}</div>
              <div className="text-[10px] font-mono text-muted-foreground uppercase">gaps</div>
            </div>
          </>
        )}
      </motion.div>

      {/* Cross-links */}
      {expert.crossLinks.length > 0 && (
        <motion.div className="space-y-2" variants={staggerChild}>
          <p className="text-xs font-mono uppercase tracking-wider text-muted-foreground">Cross-Links</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {expert.crossLinks.slice(0, 6).map((link, i) => (
              <motion.div
                key={i}
                className="glass-card p-3 text-xs"
                variants={popIn}
                custom={i}
                initial="initial"
                animate="animate"
              >
                <div className="flex items-center gap-2 font-mono">
                  <span className="text-purple truncate">{link.from_section}</span>
                  <ArrowRight className="h-3 w-3 text-muted-foreground shrink-0" />
                  <span className="text-purple truncate">{link.to_section}</span>
                </div>
                <p className="text-muted-foreground mt-1">{link.relationship}</p>
                {link.narrative && <p className="text-muted-foreground/60 mt-0.5 text-[10px]">{link.narrative}</p>}
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Insights */}
      {expert.insights.length > 0 && (
        <motion.div className="space-y-2" variants={staggerChild}>
          <p className="text-xs font-mono uppercase tracking-wider text-muted-foreground">Insights ({expert.insights.length})</p>
          {expert.insights.slice(0, 4).map((insight, i) => (
            <motion.div
              key={i}
              className="glass-card p-3 flex gap-3 items-start"
              variants={slideInLeft}
              custom={i}
              initial="initial"
              animate="animate"
            >
              <Lightbulb className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
              <p className="text-sm text-muted-foreground">{insight}</p>
            </motion.div>
          ))}
          {expert.insights.length > 4 && (
            <p className="text-xs text-muted-foreground font-mono ml-7">+{expert.insights.length - 4} more insights</p>
          )}
        </motion.div>
      )}

      {/* Contrarian risks */}
      {expert.contrarianRisks.length > 0 && (
        <motion.div className="space-y-2" variants={staggerChild}>
          <p className="text-xs font-mono uppercase tracking-wider text-muted-foreground">Contrarian Risks</p>
          {expert.contrarianRisks.slice(0, 3).map((risk, i) => (
            <motion.div
              key={i}
              className="glass-card p-3 flex gap-3 items-start border border-amber-500/15"
              variants={slideInLeft}
              custom={i}
              initial="initial"
              animate="animate"
            >
              <ShieldAlert className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
              <p className="text-sm text-muted-foreground">{risk}</p>
            </motion.div>
          ))}
        </motion.div>
      )}

      {/* Gap report */}
      {expert.gapReport.length > 0 && (
        <motion.div className="p-3 rounded-lg bg-amber-500/5 border border-amber-500/10" variants={staggerChild}>
          <p className="text-[10px] font-mono text-amber-600 uppercase mb-1">Remaining Gaps ({expert.gapReport.length} claims)</p>
          <p className="text-xs text-muted-foreground">
            Claims still lacking evidence: {expert.gapReport.join(", ")}
          </p>
        </motion.div>
      )}
    </motion.div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// STEP 7 — THE EXPERT REPORT (Agentic Pipeline Output)
// ═══════════════════════════════════════════════════════════════════════════

function StepExpertResult({ report, workflow }: { report: ComparisonReport; workflow: AgentWorkflowData }) {
  const expert = workflow.expert;
  const expertLayer = report.layers.find(l => l.layer === 2);
  const journey = report.claim_journey;

  // The final expert claim — the last snapshot from the claim journey
  const expertSnapshot = journey?.snapshots?.[journey.snapshots.length - 1];
  const claimText = expertSnapshot?.claim_text
    || firstSentences(expertLayer?.content || "", 3);
  const dataPoints = expertSnapshot?.data_points || [];
  const sourcesCited = expertSnapshot?.sources_cited || [];
  const qualityTags = expertSnapshot?.quality_tags || [];

  // Transformation steps that led to this claim
  const transformSteps = expertSnapshot?.transformation_steps || [];

  const wordCount = expertLayer?.word_count ?? 0;
  const sourceCount = expertLayer?.source_count ?? 0;
  const coverage = expert?.coverage ?? 0;

  return (
    <motion.div
      className="max-w-2xl w-full mx-auto space-y-5 overflow-y-auto max-h-full"
      variants={staggerContainer}
      initial="initial"
      animate="animate"
    >
      <motion.div className="text-center" variants={staggerChild}>
        <h3 className="text-2xl font-display text-gradient">The Expert Claim</h3>
        <p className="text-sm text-muted-foreground mt-1">
          What the agentic pipeline produced
        </p>
      </motion.div>

      {/* The final claim — hero card */}
      <motion.div className="glass-card p-6 lg:p-8 border-emerald-500/20 glow-sm" variants={staggerChild}>
        <div className="flex items-center gap-2 mb-4">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center">
            <FileText className="h-4 w-4 text-emerald-500" />
          </div>
          <div>
            <p className="text-[10px] font-mono uppercase tracking-widest text-emerald-600">Expert Output</p>
            <p className="text-xs text-muted-foreground">Verified, sourced, cross-referenced</p>
          </div>
        </div>
        <p className="text-base leading-relaxed border-l-2 border-emerald-500/30 pl-5">
          {highlightDataPoints(claimText)}
        </p>

        {qualityTags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-4">
            {qualityTags.map((tag, i) => (
              <motion.span
                key={tag}
                variants={popIn}
                custom={i}
                className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-700 border border-emerald-500/10"
              >
                {tag}
              </motion.span>
            ))}
          </div>
        )}
      </motion.div>

      {/* Metrics */}
      <motion.div className="grid grid-cols-3 gap-2" variants={staggerChild}>
        <div className="glass-card p-3 text-center">
          <div className="text-xl font-display text-gradient"><AnimatedCounter value={wordCount} /></div>
          <div className="text-[9px] font-mono text-muted-foreground uppercase mt-0.5">words</div>
        </div>
        <div className="glass-card p-3 text-center">
          <div className="text-xl font-display text-gradient"><AnimatedCounter value={sourceCount} /></div>
          <div className="text-[9px] font-mono text-muted-foreground uppercase mt-0.5">sources</div>
        </div>
        <div className="glass-card p-3 text-center">
          <div className="text-xl font-display text-gradient"><AnimatedCounter value={Math.round(coverage * 100)} suffix="%" /></div>
          <div className="text-[9px] font-mono text-muted-foreground uppercase mt-0.5">coverage</div>
        </div>
      </motion.div>

      {/* Data points extracted */}
      {dataPoints.length > 0 && (
        <motion.div className="glass-card p-4" variants={staggerChild}>
          <p className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-2">
            Data Points ({dataPoints.length})
          </p>
          <div className="flex flex-wrap gap-2">
            {dataPoints.map((dp, i) => (
              <motion.span
                key={i}
                variants={popIn}
                custom={i}
                className="px-3 py-1 rounded-full text-sm font-mono bg-emerald-500/5 border border-emerald-500/10"
              >
                {highlightDataPoints(dp)}
              </motion.span>
            ))}
          </div>
        </motion.div>
      )}

      {/* Sources cited */}
      {sourcesCited.length > 0 && (
        <motion.div className="glass-card p-4" variants={staggerChild}>
          <p className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-2">
            Sources Cited ({sourcesCited.length})
          </p>
          <div className="space-y-1.5">
            {sourcesCited.map((src, i) => (
              <motion.div
                key={i}
                className="flex items-center gap-2 text-xs"
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.3 + i * 0.05, duration: 0.3 }}
              >
                <ExternalLink className="h-3 w-3 text-emerald-500 shrink-0" />
                <span className="text-muted-foreground truncate">{src}</span>
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Key transformation steps */}
      {transformSteps.length > 0 && (
        <motion.div className="glass-card p-4" variants={staggerChild}>
          <p className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-3">
            How We Got Here
          </p>
          <div className="space-y-2">
            {transformSteps.slice(0, 4).map((step, i) => (
              <motion.div
                key={i}
                className="flex gap-3 items-start text-xs"
                variants={slideInLeft}
                custom={i}
                initial="initial"
                animate="animate"
              >
                <div className="w-5 h-5 rounded-full bg-emerald-500/10 flex items-center justify-center shrink-0 mt-0.5">
                  <span className="text-[9px] font-mono text-emerald-600">{i + 1}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm">{step.data_point_added}</p>
                  <p className="text-muted-foreground/60 text-[10px] mt-0.5 truncate">
                    {step.source_title || step.source_url}
                  </p>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}
    </motion.div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// STEP 8 — THE TRANSFORMATION (Final Result)
// ═══════════════════════════════════════════════════════════════════════════

function StepTransformation({ report, workflow }: { report: ComparisonReport; workflow: AgentWorkflowData }) {
  const totalSearches = (workflow.enhanced?.totalSearches ?? 0)
    + (workflow.expert?.phaseDetails.find(p => p.phase === "investigate")?.searches ?? 0);
  const evidenceCount = workflow.expert?.evidenceLedger.length ?? 0;
  const coverage = workflow.expert?.coverage ?? 0;

  const journey = report.claim_journey;
  const beforeText = journey?.snapshots?.find(s => s.layer === 0)?.claim_text
    || firstSentences(report.layers[0]?.content || "", 2);
  const afterSnapshot = journey?.snapshots?.[journey.snapshots.length - 1];
  const afterText = afterSnapshot?.claim_text
    || firstSentences(report.layers[report.layers.length - 1]?.content || "", 2);

  return (
    <motion.div
      className="max-w-2xl w-full mx-auto space-y-6 overflow-y-auto max-h-full"
      variants={staggerContainer}
      initial="initial"
      animate="animate"
    >
      <motion.div className="text-center" variants={staggerChild}>
        <h3 className="text-2xl font-display text-gradient">The Transformation</h3>
        <p className="text-sm text-muted-foreground mt-1">From model knowledge to verified research</p>
      </motion.div>

      {/* Aggregate metrics */}
      <motion.div className="grid grid-cols-3 gap-3" variants={staggerChild}>
        <div className="glass-card p-4 text-center">
          <div className="text-2xl font-display text-gradient"><AnimatedCounter value={totalSearches} /></div>
          <div className="text-[10px] font-mono text-muted-foreground uppercase mt-1">searches total</div>
        </div>
        <div className="glass-card p-4 text-center">
          <div className="text-2xl font-display text-gradient"><AnimatedCounter value={evidenceCount} /></div>
          <div className="text-[10px] font-mono text-muted-foreground uppercase mt-1">evidence entries</div>
        </div>
        <div className="glass-card p-4 text-center">
          <div className="text-2xl font-display text-gradient"><AnimatedCounter value={Math.round(coverage * 100)} suffix="%" /></div>
          <div className="text-[10px] font-mono text-muted-foreground uppercase mt-1">coverage</div>
        </div>
      </motion.div>

      {/* Before / After */}
      <motion.div className="grid grid-cols-1 lg:grid-cols-2 gap-4 relative" variants={staggerChild}>
        <motion.div
          className="glass-card p-5 border-amber-500/20"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 0.7, x: 0 }}
          transition={{ duration: 0.5, ease: easeOutExpo, delay: 0.2 }}
        >
          <p className="text-[10px] font-mono uppercase tracking-wider text-amber-600 mb-3">Before — Baseline</p>
          <p className="text-sm text-foreground/60 italic leading-relaxed">&ldquo;{beforeText}&rdquo;</p>
          <div className="flex flex-wrap gap-1 mt-3">
            {["Unsourced", "No Data", "Vague"].map(w => (
              <span key={w} className="px-2 py-0.5 rounded text-[10px] bg-amber-500/10 text-amber-700">{w}</span>
            ))}
          </div>
        </motion.div>
        <motion.div
          className="hidden lg:flex absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-10"
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: 0.5, duration: 0.4, ease: easeOutBack }}
        >
          <div className="w-10 h-10 rounded-full bg-background border border-purple/20 flex items-center justify-center animate-pulse-glow">
            <ArrowRight className="h-4 w-4 text-purple" />
          </div>
        </motion.div>
        <motion.div
          className="glass-card p-5 border-purple/20 glow-sm"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5, ease: easeOutExpo, delay: 0.35 }}
        >
          <p className="text-[10px] font-mono uppercase tracking-wider text-purple mb-3">After — Expert</p>
          <p className="text-sm leading-relaxed">{highlightDataPoints(afterText)}</p>
          <div className="flex flex-wrap gap-1 mt-3">
            {["+Named Source", "+Quantified", "+Cross-Referenced"].map(tag => (
              <span key={tag} className="px-2 py-0.5 rounded text-[10px] bg-green-500/10 text-green-700">{tag}</span>
            ))}
          </div>
        </motion.div>
      </motion.div>

      {/* Narrative */}
      {journey?.overall_narrative && (
        <motion.div className="glass-card p-5 border-l-2 border-purple/30" variants={staggerChild}>
          <p className="text-sm leading-relaxed text-muted-foreground">{journey.overall_narrative}</p>
        </motion.div>
      )}

      {/* Layer progression fallback */}
      {!journey && (
        <motion.div className="flex gap-3" variants={staggerChild}>
          {report.layers.map((layer, i) => (
            <motion.div
              key={layer.layer}
              className="flex-1 glass-card p-3 text-center"
              variants={popIn}
              custom={i}
            >
              <div className="text-xs font-mono text-muted-foreground mb-1">L{layer.layer}</div>
              <div className="text-lg font-display">{layer.word_count.toLocaleString()}</div>
              <div className="text-[9px] font-mono text-muted-foreground">words</div>
              <div className="text-sm font-display mt-1">{layer.source_count}</div>
              <div className="text-[9px] font-mono text-muted-foreground">sources</div>
            </motion.div>
          ))}
        </motion.div>
      )}
    </motion.div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// PROGRESS RAIL
// ═══════════════════════════════════════════════════════════════════════════

function ProgressRail({
  steps,
  activeStep,
  scrollProgress,
  onClickStep,
}: {
  steps: StepConfig[];
  activeStep: number;
  scrollProgress: number;
  onClickStep: (i: number) => void;
}) {
  return (
    <div className="w-14 shrink-0 hidden lg:flex flex-col items-center py-8 z-20">
      <div className="relative flex flex-col justify-between h-full items-center">
        {/* Background track line */}
        <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-px bg-foreground/8" />
        {/* Active progress line */}
        <motion.div
          className="absolute top-0 left-1/2 -translate-x-1/2 w-px bg-purple/60 origin-top"
          animate={{ height: `${Math.min(scrollProgress * 100, 100)}%` }}
          transition={{ duration: 0.4, ease: easeOutExpo }}
        />
        {steps.map((s, i) => {
          const isActive = i === activeStep;
          const isPast = i < activeStep;
          const Icon = s.icon;
          return (
            <button
              key={s.id}
              onClick={() => onClickStep(i)}
              className="relative z-10 group flex items-center"
              title={s.label}
            >
              {/* Dot */}
              <motion.div
                className={cn(
                  "rounded-full flex items-center justify-center",
                  isActive
                    ? `${s.dotColor} shadow-lg shadow-purple/20`
                    : isPast
                      ? s.dotColor
                      : "bg-foreground/10 border border-foreground/15"
                )}
                animate={{
                  width: isActive ? 28 : 12,
                  height: isActive ? 28 : 12,
                }}
                transition={{ type: "spring", stiffness: 400, damping: 25 }}
              >
                <AnimatePresence mode="wait">
                  {isActive && (
                    <motion.div
                      key={`icon-${s.id}`}
                      initial={{ opacity: 0, scale: 0.5 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.5 }}
                      transition={{ duration: 0.2 }}
                    >
                      <Icon className="w-3.5 h-3.5 text-white" />
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
              {/* Hover label */}
              <motion.span
                className="absolute left-10 text-[9px] font-mono whitespace-nowrap pointer-events-none"
                animate={{
                  opacity: isActive ? 1 : 0,
                  x: isActive ? 0 : -4,
                }}
                whileHover={{ opacity: 0.7, x: 0 }}
                transition={{ duration: 0.25 }}
              >
                {s.label}
              </motion.span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT — Sticky Viewport Scroll Pipeline
// ═══════════════════════════════════════════════════════════════════════════

interface ScrollPipelineProps {
  report: ComparisonReport;
}

export function ScrollPipeline({ report }: ScrollPipelineProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [activeStep, setActiveStep] = useState(0);
  const [scrollProgress, setScrollProgress] = useState(0);
  const [bgColor, setBgColor] = useState("rgba(217,119,6,0.04)");
  const prevStepRef = useRef(0);
  const direction = activeStep >= prevStepRef.current ? 1 : -1;

  // Track direction changes
  useEffect(() => {
    prevStepRef.current = activeStep;
  }, [activeStep]);

  const workflow = useMemo(() => extractAgentWorkflow(report), [report]);

  // Determine available steps based on layer data
  const steps = useMemo(() => {
    const s: StepConfig[] = [ALL_STEPS[0]]; // baseline always
    if (report.layers.length > 1) {
      s.push(ALL_STEPS[1]); // search
      s.push(ALL_STEPS[2]); // l1-result
    }
    if (report.layers.length > 2) {
      s.push(ALL_STEPS[3]); // dissect
      s.push(ALL_STEPS[4]); // plan
      s.push(ALL_STEPS[5]); // investigate
      s.push(ALL_STEPS[6]); // synthesize
      s.push(ALL_STEPS[7]); // expert-result
    }
    s.push(ALL_STEPS[8]); // transformation always
    return s;
  }, [report.layers.length]);

  const NUM_STEPS = steps.length;

  // Scroll handler — drives step transitions from scroll position
  const handleScroll = useCallback(() => {
    const track = trackRef.current;
    if (!track) return;

    // Find the scroll parent (ResultsPopup's overflow-y-auto div)
    const scrollParent = track.closest(".overflow-y-auto") as HTMLElement | null;
    if (!scrollParent) return;

    const trackRect = track.getBoundingClientRect();
    const parentRect = scrollParent.getBoundingClientRect();

    // How far the track top has scrolled above the parent top
    const scrolled = parentRect.top - trackRect.top;
    const maxScroll = track.offsetHeight - parentRect.height;
    if (maxScroll <= 0) return;

    const progress = Math.max(0, Math.min(1, scrolled / maxScroll));
    setScrollProgress(progress);

    const stepIndex = Math.min(Math.floor(progress * NUM_STEPS), NUM_STEPS - 1);
    setActiveStep(stepIndex);

    // Background color interpolation
    const stageProgress = (progress * NUM_STEPS) % 1;
    const fromStep = steps[stepIndex];
    const toStep = steps[Math.min(stepIndex + 1, NUM_STEPS - 1)];
    setBgColor(lerpRgba(fromStep.bg, toStep.bg, stageProgress));
  }, [steps, NUM_STEPS]);

  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;
    const scrollParent = track.closest(".overflow-y-auto") as HTMLElement | null;
    if (!scrollParent) return;

    scrollParent.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll(); // initial position
    return () => scrollParent.removeEventListener("scroll", handleScroll);
  }, [handleScroll]);

  const scrollToStep = useCallback((i: number) => {
    const track = trackRef.current;
    if (!track) return;
    const scrollParent = track.closest(".overflow-y-auto") as HTMLElement | null;
    if (!scrollParent) return;

    const maxScroll = track.offsetHeight - scrollParent.clientHeight;
    const targetScroll = (i / NUM_STEPS) * maxScroll;
    // Account for the track's offset within the scroll parent
    const trackOffset = track.offsetTop;
    scrollParent.scrollTo({ top: trackOffset + targetScroll, behavior: "smooth" });
  }, [NUM_STEPS]);

  if (!report.layers || report.layers.length === 0) {
    return <div className="text-center py-12 text-muted-foreground">No research data available.</div>;
  }

  const activeStepConfig = steps[activeStep];

  // Render step content based on step id
  const renderStep = (stepId: string) => {
    switch (stepId) {
      case "baseline": return <StepBaseline report={report} workflow={workflow} />;
      case "search": return <StepSearch workflow={workflow} />;
      case "l1-result": return <StepL1Result report={report} workflow={workflow} />;
      case "dissect": return <StepDissect workflow={workflow} />;
      case "plan": return <StepPlan workflow={workflow} />;
      case "investigate": return <StepInvestigate workflow={workflow} />;
      case "synthesize": return <StepSynthesize workflow={workflow} />;
      case "expert-result": return <StepExpertResult report={report} workflow={workflow} />;
      case "result": return <StepTransformation report={report} workflow={workflow} />;
      default: return null;
    }
  };

  return (
    <div
      ref={trackRef}
      style={{ height: `${NUM_STEPS * 70}vh` }}
      className="relative"
    >
      {/* Sticky viewport — stays in place while track scrolls */}
      <motion.div
        className="sticky top-0 flex"
        style={{ height: "calc(100vh - 10rem)" }}
        animate={{ backgroundColor: bgColor }}
        transition={{ duration: 0.6, ease: "easeOut" }}
      >
        {/* Progress rail */}
        <ProgressRail
          steps={steps}
          activeStep={activeStep}
          scrollProgress={scrollProgress}
          onClickStep={scrollToStep}
        />

        {/* Step content area */}
        <div className="relative flex-1 overflow-hidden">
          {/* Step header — animated label transitions */}
          <div className="text-center pt-6 pb-4 px-4">
            <AnimatePresence mode="wait">
              <motion.div
                key={activeStepConfig?.id}
                variants={headerVariants}
                initial="initial"
                animate="animate"
                exit="exit"
              >
                <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground mb-0.5">
                  {activeStepConfig?.label}
                </p>
                <p className="text-sm text-muted-foreground">
                  {activeStepConfig?.sublabel}
                </p>
              </motion.div>
            </AnimatePresence>
          </div>

          {/* Step content — AnimatePresence crossfade with direction-aware slide */}
          <div className="relative flex-1 px-4 pb-6" style={{ height: "calc(100% - 5rem)" }}>
            <AnimatePresence mode="wait" custom={direction}>
              <motion.div
                key={activeStepConfig?.id}
                custom={direction}
                variants={stepFadeVariants}
                initial="initial"
                animate="animate"
                exit="exit"
                className="absolute inset-0 flex items-start justify-center overflow-y-auto px-4 pb-6"
              >
                {renderStep(activeStepConfig?.id)}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
