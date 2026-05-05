"use client";

/**
 * Backend2Results — page wrapper that mounts the five backend2 result
 * components in the canonical reading order:
 *
 *   1. TopicProfile          — "what was this run optimising for?"
 *   2. GroundingBadge        — "how grounded is the brief?" (KPI tile)
 *   3. OutlineBrief          — the actual brief (frameworks, causal chains,
 *                              case studies, contrarian view, references)
 *   4. DimensionalClusters   — quantitative consensus appendix
 *   5. InvestigationTree     — sub-question → evidence drill-down (collapsible)
 *
 * The order intentionally surfaces the meta-context (1, 2) first so the
 * reader knows the brief's domain framing and how trustworthy it is BEFORE
 * reading. The investigation tree at the bottom is the audit-trail panel.
 */

import type { Backend2Report } from "@/lib/types-backend2";
import Backend2TopicProfile from "./Backend2TopicProfile";
import Backend2GroundingBadge from "./Backend2GroundingBadge";
import Backend2OutlineBrief from "./Backend2OutlineBrief";
import Backend2DimensionalClusters from "./Backend2DimensionalClusters";
import Backend2InvestigationTree from "./Backend2InvestigationTree";
import Backend2PipelineTrace from "./Backend2PipelineTrace";

interface Props {
  report: Backend2Report;
}

export default function Backend2Results({ report }: Props) {
  return (
    <div className="space-y-0">
      {/* Header strip */}
      <div className="mb-8">
        <span className="inline-flex items-center gap-3 text-xs font-mono uppercase tracking-wider text-muted-foreground mb-2">
          <span className="w-6 h-px bg-foreground/30" />
          Query
        </span>
        <h1 className="font-display text-3xl md:text-4xl text-foreground leading-tight">
          {report.chosen_query || report.original_query}
        </h1>
        {report._status === "error" && report.error && (
          <p className="text-sm text-(--color-coral) mt-2">
            Run finished with error: {report.error}
          </p>
        )}
        {report._status === "running" && (
          <p className="text-sm text-(--color-orange) mt-2 animate-pulse">
            Run is still in progress — partial state shown below.
          </p>
        )}
      </div>

      <Backend2PipelineTrace report={report} />
      <Backend2TopicProfile profile={report.topic_profile} />
      <Backend2GroundingBadge verification={report.verification} />
      <Backend2OutlineBrief consolidated={report.consolidated} />
      <Backend2DimensionalClusters clusters={report.dimensional_clusters} />
      <Backend2InvestigationTree
        subQuestions={report.sub_questions}
        topicClaims={[
          ...report.topic_claims,
          ...report.market_claims,
          ...report.news_claims,
        ]}
      />
    </div>
  );
}
