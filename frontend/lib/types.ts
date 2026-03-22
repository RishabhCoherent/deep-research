export interface HealthStatus {
  openai: boolean;
  searxng: boolean;
  tavily: boolean;
}

// ─── Research Agent Types ────────────────────────────────────

export interface ResearchJobResponse {
  job_id: string;
}

export interface LayerResult {
  layer: number;
  word_count: number;
  source_count: number;
  elapsed_seconds: number;
  content: string;
  metadata: Record<string, unknown>;
}

export interface LayerEvaluation {
  layer: number;
  factual_density: number;
  source_diversity: number;
  specificity_score: number;
  framework_usage: string[];
  insight_depth: string;
  contrarian_views: number;
  word_count: number;
  elapsed_seconds: number;
  scores: Record<string, { score: number; justification: string }>;
}

export interface ClaimPair {
  category: string;
  baseline: string;
  improved: string;
  tags: string[];
  source: string;
}

export interface TransformationStep {
  action: string;
  query: string;
  source_title: string;
  source_url: string;
  data_point_added: string;
  why_it_matters: string;
}

export interface ClaimLayerSnapshot {
  layer: number;
  claim_text: string;
  data_points: string[];
  sources_cited: string[];
  quality_tags: string[];
  transformation_steps: TransformationStep[];
}

export interface ClaimJourney {
  category: string;
  topic_sentence: string;
  snapshots: ClaimLayerSnapshot[];
  overall_narrative: string;
  selection_reason: string;
}

export interface LayerComparisonData {
  from_layer: number;
  to_layer: number;
  improvements: string[];
  score_delta: number;
  key_evidence: string;
  overall_verdict: string;
  claim_pairs?: ClaimPair[];
}

export interface ComparisonReport {
  topic: string;
  layers: LayerResult[];
  evaluations: LayerEvaluation[];
  summary: string;
  layer_comparisons?: LayerComparisonData[];
  claim_journey?: ClaimJourney;
  hallucination_reduction?: number;
  outcome_efficiency?: number;
  relevancy?: number;
}

export const LAYER_NAMES: Record<number, string> = {
  0: "L1 Baseline (Prompt-Driven)",
  1: "L2 Enhanced (AI Agent)",
  2: "L3 CMI Expert (Agentic AI)",
};

export const LAYER_DESCRIPTIONS: Record<number, string> = {
  0: "Best model, no tools — report from model knowledge",
  1: "Web search agent — enriches baseline with real data",
  2: "Deep analysis agent — cross-references and substantiates",
};

// ─── Agent Workflow Types (from layers[].metadata) ──────────

export interface SearchToolCall {
  tool: "search_web";
  query: string;
  results: number;
  hits: Array<{ title: string; snippet: string; url: string }>;
}

export interface ScrapeToolCall {
  tool: "scrape_page";
  url: string;
}

export interface RecordFindingCall {
  tool: "record_finding";
  claim_id: string;
  evidence_type: string;
}

export type AgentToolCall = SearchToolCall | ScrapeToolCall | RecordFindingCall;

export interface EvidenceEntry {
  claim_id: string;
  fact: string;
  source_url: string;
  source_title: string;
  evidence_type: string;
  confidence?: string;
}

export interface CrossLinkEntry {
  from_section: string;
  to_section: string;
  from_claim_id: string;
  to_claim_id: string;
  relationship: string;
  narrative: string;
}

export interface ClaimDetail {
  id: string;
  text: string;
  evidence_quality: "strong" | "weak" | "unsupported" | "stale";
  data_type: string;
  needs_research: boolean;
  reasoning: string;
}

export interface SectionAnnotationDetail {
  section: string;
  thesis: string;
  overall_quality: "thin" | "adequate" | "strong";
  missing_angles: string[];
  claims: ClaimDetail[];
}

export interface ResearchTaskDetail {
  claim_id: string;
  section: string;
  rationale: string;
  queries: string[];
  expected_evidence: string;
  priority: number;
  target_sources: string[];
}

export interface PhaseTimings {
  [phase: string]: {
    elapsed_s: number;
    [key: string]: number;
  };
}

export interface PhaseDetail {
  phase: string;
  elapsed?: number;
  // dissect
  claims_total?: number;
  claims_weak?: number;
  // plan
  sections?: number;
  questions?: number;
  // investigate
  facts?: number;
  sources?: number;
  coverage?: number;
  searches?: number;
  scrapes?: number;
  // synthesize
  insights?: number;
  cross_links?: number;
  risks?: number;
  gaps?: number;
  // compose
  words?: number;
}

export interface AgentWorkflowData {
  baseline: {
    wordCount: number;
    sourceCount: number;
    method: string;
  };
  enhanced: {
    toolCalls: AgentToolCall[];
    searches: SearchToolCall[];
    scrapes: ScrapeToolCall[];
    totalSearches: number;
    totalScrapes: number;
    sourcesFound: number;
  } | null;
  expert: {
    phaseDetails: PhaseDetail[];
    phaseTimings: PhaseTimings;
    toolCalls: AgentToolCall[];
    evidenceLedger: EvidenceEntry[];
    crossLinks: CrossLinkEntry[];
    insights: string[];
    coverage: number;
    planSections: string[];
    claimMap: SectionAnnotationDetail[];
    researchTasks: ResearchTaskDetail[];
    contrarianRisks: string[];
    resolvedContradictions: unknown[];
    gapReport: string[];
    coverageBeforeGapFill: number | null;
    gapFillPasses: number;
  } | null;
}

// ─── Expert Pipeline Phase Progress ─────────────────────────

export interface ExpertPhaseProgress {
  phase: "dissect" | "plan" | "investigate" | "synthesize" | "compose";
  claims_total?: number;
  claims_weak?: number;
  queries_planned?: number;
  tasks?: number;
  searches?: number;
  scrapes?: number;
  findings?: number;
  coverage?: number;
  cross_links?: number;
  insights?: number;
  gaps?: number;
  word_count?: number;
  elapsed_s?: number;
}

// ─── Research History Types ─────────────────────────────────

export interface ResearchHistoryItem {
  id: string;
  saved_at: string;
  topic: string;
  layer_count: number;
  total_words: number;
  total_sources: number;
  avg_score: number;
}

export interface ResearchHistoryDetail extends ResearchHistoryItem {
  report: ComparisonReport;
}
