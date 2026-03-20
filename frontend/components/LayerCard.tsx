"use client";

import { useState } from "react";
import {
  Clock,
  FileText,
  Globe,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  TrendingDown,
  ArrowLeftRight,
  CheckCircle2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { LAYER_NAMES } from "@/lib/types";
import { MarkdownReport } from "@/components/MarkdownReport";
import type { SectionImpact } from "@/components/MarkdownReport";
import type { LayerResult, LayerEvaluation } from "@/lib/types";

interface LayerCardProps {
  result: LayerResult;
  evaluation?: LayerEvaluation;
}

/* ── Assumption Audit Panel (L3 only) ───────────────────────────── */
function AssumptionAuditPanel({ metadata }: { metadata: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);

  const assumptions = (metadata.assumptions_extracted as string[]) ?? [];
  const challenges = (metadata.assumption_challenges as number) ?? 0;
  const bearCases = (metadata.bear_cases_searched as number) ?? 0;
  const crossIndustry = (metadata.cross_industry_searches as number) ?? 0;

  if (!assumptions.length) return null;

  return (
    <div className="glass-card overflow-hidden">
      {/* Header row */}
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-5 py-3.5 text-left"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-purple/15">
            <AlertTriangle className="h-3.5 w-3.5 text-purple" />
          </div>
          <span className="text-sm font-semibold text-foreground">Assumption Audit</span>
          <span className="rounded-full bg-purple/15 px-2 py-0.5 text-[10px] font-semibold text-purple">
            {assumptions.length} assumptions
          </span>
        </div>
        <div className="flex items-center gap-4">
          {/* Stats */}
          <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <AlertTriangle className="h-3 w-3 text-purple" />
              {challenges} challenged
            </span>
            <span className="flex items-center gap-1">
              <TrendingDown className="h-3 w-3 text-foreground" />
              {bearCases} bear cases
            </span>
            <span className="flex items-center gap-1">
              <ArrowLeftRight className="h-3 w-3 text-success" />
              {crossIndustry} cross-industry
            </span>
          </div>
          {open ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </button>

      {/* Assumption list */}
      {open && (
        <div className="border-t border-foreground/10 px-5 py-3 space-y-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            Assumptions extracted from L2 and stress-tested
          </p>
          {assumptions.map((assumption, i) => (
            <div
              key={i}
              className="flex items-start gap-2.5 rounded-lg bg-foreground/5 px-3 py-2.5"
            >
              <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
              <p className="text-[12px] leading-relaxed text-muted-foreground">{assumption}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function LayerCard({ result, evaluation }: LayerCardProps) {
  const [expanded, setExpanded] = useState(true);
  const name = LAYER_NAMES[result.layer] || `Layer ${result.layer}`;

  const depthColor: Record<string, string> = {
    shallow: "bg-foreground/30 text-muted-foreground",
    moderate: "bg-purple/20 text-purple",
    deep: "bg-purple/20 text-purple-light",
    expert: "bg-foreground/20 text-foreground",
  };

  return (
    <div className="space-y-4">
      {/* Header card */}
      <div className="glass-card overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-purple/20 text-sm font-bold text-purple">
              L{result.layer}
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">{name}</h3>
              {evaluation && (
                <span
                  className={cn(
                    "mt-0.5 inline-block rounded-full px-2 py-0.5 text-[10px] font-medium",
                    depthColor[evaluation.insight_depth] ||
                      "bg-foreground/10 text-muted-foreground"
                  )}
                >
                  {evaluation.insight_depth} insight
                </span>
              )}
            </div>
          </div>

          {/* Stats */}
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <FileText className="h-3 w-3" />
              {result.word_count.toLocaleString()} words
            </span>
            <span className="flex items-center gap-1">
              <Globe className="h-3 w-3" />
              {result.source_count} sources
            </span>
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {result.elapsed_seconds}s
            </span>
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 text-xs font-medium text-purple hover:text-purple-light transition-colors ml-2"
            >
              {expanded ? (
                <>
                  <ChevronUp className="h-3.5 w-3.5" /> Collapse
                </>
              ) : (
                <>
                  <ChevronDown className="h-3.5 w-3.5" /> Expand
                </>
              )}
            </button>
          </div>
        </div>

        {/* Evaluation scores */}
        {evaluation && Object.keys(evaluation.scores).length > 0 && (
          <div className="border-t border-foreground/10 px-5 py-3">
            <div className="flex flex-wrap gap-2">
              {Object.entries(evaluation.scores).map(([key, val]) => (
                <div
                  key={key}
                  className="flex items-center gap-2 rounded-lg bg-foreground/5 px-2.5 py-1.5"
                >
                  <span className="text-[10px] text-muted-foreground capitalize">
                    {key.replace(/_/g, " ")}
                  </span>
                  <span className="text-xs font-semibold text-foreground">
                    {val.score}/10
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Content — section-based rendering */}
      {expanded && (
        <MarkdownReport
          content={result.content}
          sectionImpacts={
            result.layer === 3
              ? (result.metadata.section_impacts as SectionImpact[] | undefined)
              : undefined
          }
        />
      )}

      {/* Assumption Audit — L3 only */}
      {result.layer === 3 && (
        <AssumptionAuditPanel metadata={result.metadata} />
      )}
    </div>
  );
}
