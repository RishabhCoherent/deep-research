import type {
  ComparisonReport,
  AgentWorkflowData,
  AgentToolCall,
  SearchToolCall,
  ScrapeToolCall,
  EvidenceEntry,
  CrossLinkEntry,
  PhaseDetail,
  PhaseTimings,
  SectionAnnotationDetail,
  ResearchTaskDetail,
} from "./types";

// ─── Helpers ────────────────────────────────────────────────────────────────

function meta(report: ComparisonReport, layerIndex: number): Record<string, unknown> {
  const layer = report.layers?.[layerIndex];
  if (!layer) return {};
  return (layer.metadata ?? {}) as Record<string, unknown>;
}

function asArray<T>(val: unknown): T[] {
  if (Array.isArray(val)) return val as T[];
  return [];
}

function asNumber(val: unknown, fallback = 0): number {
  if (typeof val === "number") return val;
  return fallback;
}

function asString(val: unknown, fallback = ""): string {
  if (typeof val === "string") return val;
  return fallback;
}

// ─── Tool call extraction ───────────────────────────────────────────────────

interface RawQuery {
  tool?: string;
  query?: string;
  results?: number;
  hits?: Array<{ title: string; snippet: string; url: string }>;
  url?: string;
  claim_id?: string;
  evidence_type?: string;
}

function extractToolCalls(m: Record<string, unknown>): AgentToolCall[] {
  const calls: AgentToolCall[] = [];

  // Primary source: iteration_history[].queries[]
  const iterHistory = asArray<{ queries?: unknown[] }>(m.iteration_history);
  for (const iter of iterHistory) {
    const queries = asArray<string | RawQuery>(iter.queries);
    for (const q of queries) {
      if (typeof q === "string") {
        calls.push({ tool: "search_web", query: q, results: 0, hits: [] });
        continue;
      }
      const tool = q.tool ?? "search_web";
      if (tool === "search_web") {
        calls.push({
          tool: "search_web",
          query: q.query ?? "",
          results: q.results ?? 0,
          hits: asArray(q.hits),
        } as SearchToolCall);
      } else if (tool === "scrape_page") {
        calls.push({ tool: "scrape_page", url: q.url ?? "" } as ScrapeToolCall);
      } else if (tool === "record_finding") {
        calls.push({
          tool: "record_finding",
          claim_id: q.claim_id ?? "",
          evidence_type: q.evidence_type ?? "",
        });
      }
    }
  }

  return calls;
}

// ─── Main extraction ────────────────────────────────────────────────────────

export function extractAgentWorkflow(report: ComparisonReport): AgentWorkflowData {
  // --- Layer 0: Baseline ---
  const m0 = meta(report, 0);
  const baseline: AgentWorkflowData["baseline"] = {
    wordCount: report.layers?.[0]?.word_count ?? 0,
    sourceCount: report.layers?.[0]?.source_count ?? 0,
    method: asString(m0.method, "single_prompt"),
  };

  // --- Layer 1: Enhanced (Web Research) ---
  let enhanced: AgentWorkflowData["enhanced"] = null;
  if (report.layers?.length > 1) {
    const m1 = meta(report, 1);
    const toolCalls = extractToolCalls(m1);
    const searches = toolCalls.filter((c): c is SearchToolCall => c.tool === "search_web");
    const scrapes = toolCalls.filter((c): c is ScrapeToolCall => c.tool === "scrape_page");

    enhanced = {
      toolCalls,
      searches,
      scrapes,
      totalSearches: asNumber(m1.searches_count, searches.length),
      totalScrapes: asNumber(m1.scrapes_count, scrapes.length),
      sourcesFound: asNumber(m1.sources_found, report.layers[1]?.source_count ?? 0),
    };
  }

  // --- Layer 2: Expert (5-Phase Pipeline) ---
  let expert: AgentWorkflowData["expert"] = null;
  if (report.layers?.length > 2) {
    const m2 = meta(report, 2);
    const toolCalls = extractToolCalls(m2);

    // Evidence ledger — flat list (not { entries: [...] })
    let rawLedger = m2.evidence_ledger;
    if (rawLedger && !Array.isArray(rawLedger) && typeof rawLedger === "object") {
      rawLedger = (rawLedger as Record<string, unknown>).entries ?? [];
    }
    const evidenceLedger = asArray<EvidenceEntry>(rawLedger);

    // Phase details
    const phaseDetails = asArray<PhaseDetail>(m2.phase_details);

    // Phase timings — dict of { phase_name: { elapsed_s, ... } }
    const phaseTimings = (m2.phases ?? {}) as PhaseTimings;

    // Cross-links
    const crossLinks = asArray<CrossLinkEntry>(m2.cross_links);

    // Insights — array of strings
    const insights = asArray<string>(m2.insights);

    // Coverage — float 0-1
    const coverage = asNumber(m2.claim_coverage, 0);

    // Plan sections
    const planSections = asArray<string>(m2.plan_sections);

    // Enriched metadata for Overview narrative
    const claimMap = asArray<SectionAnnotationDetail>(m2.claim_map);
    const researchTasks = asArray<ResearchTaskDetail>(m2.research_tasks);
    const contrarianRisks = asArray<string>(m2.contrarian_risks_detail);
    const resolvedContradictions = asArray<unknown>(m2.resolved_contradictions);
    const gapReport = asArray<string>(m2.gap_report);
    const coverageBeforeGapFill = m2.coverage_before_gap_fill != null
      ? asNumber(m2.coverage_before_gap_fill) : null;
    const gapFillPasses = asNumber(m2.gap_fill_passes, 0);

    expert = {
      phaseDetails,
      phaseTimings,
      toolCalls,
      evidenceLedger,
      crossLinks,
      insights,
      coverage,
      planSections,
      claimMap,
      researchTasks,
      contrarianRisks,
      resolvedContradictions,
      gapReport,
      coverageBeforeGapFill,
      gapFillPasses,
    };
  }

  return { baseline, enhanced, expert };
}
