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

// ─── Research Tree Types ─────────────────────────────────────

export type ResearchNodeStatus = "pending" | "exploring" | "complete" | "dead-end";
export type ResearchNodeWhy =
  | "root"
  | "vague_finding"
  | "contradiction"
  | "thin_data"
  | "surprising_data"
  | "missing_entity";

export interface ResearchNodeData {
  id: string;
  parent_id: string | null;
  depth: number;                    // 0=root, 1=drill-down, 2=deep verification
  query: string;
  why_created: ResearchNodeWhy;
  trigger_finding: string;
  sq_id: string | null;
  hypothesis: string;
  answer: string;
  confidence: number;
  status: ResearchNodeStatus;
  children_ids: string[];
  evidence_ids: string[];
}

export interface ResearchTreeData {
  total_nodes: number;
  max_depth: number;
  sq_to_root: Record<string, string>;
  nodes: Record<string, ResearchNodeData>;
}

// Live node event from SSE (node_created / node_complete)
export interface NodeCreatedEvent {
  node_id: string;
  parent_id: string | null;
  depth: number;
  query: string;
  why: ResearchNodeWhy;
  trigger_finding: string;
  sq_id: string;
}

export interface NodeCompleteEvent {
  node_id: string;
  depth: number;
  status: ResearchNodeStatus;
  confidence: number;
  answer: string;
  evidence_count: number;
}

export const LAYER_NAMES: Record<number, string> = {
  0: "L1 Baseline (Prompt-Driven)",
  1: "L2 Enhanced (AI Agent)",
  2: "L3 CMI Expert (Agentic AI System)",
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

// ─── Analyst Trace Types (from analyst agent metadata) ──────

export type AnalystPhase =
  | "decompose" | "think" | "search" | "scrape"
  | "reflect" | "analyze" | "quality" | "compose";

export interface TraceStep {
  phase: AnalystPhase;
  sq_id: string;
  title: string;
  content: Record<string, unknown>;
  elapsed_s: number;
}

export interface AnalystTrace {
  topic: string;
  started_at: number;
  total_steps: number;
  steps: TraceStep[];
}

export interface DecomposeContent {
  core_question: string;
  assumptions: string[];
  scope_in?: string[];
  scope_out?: string[];
  report_sections?: string[];
  sub_questions: Array<{
    id: string;
    question: string;
    answer_type: string;
    research_strategy: string;
    priority: number;
    depends_on: string[];
    search_queries: string[];
  }>;
}

export interface ThinkContent {
  hypothesis: string;
  would_change_mind: string;
  search_queries: string[];
  question?: string;
  priority?: number;
  answer_type?: string;
  research_strategy?: string;
}

export interface SearchContent {
  query: string;
  results: Array<{
    title: string;
    url: string;
    snippet: string;
    tier: number;
  }>;
}

export interface ScrapeContent {
  url: string;
  success: boolean;
  method: string;
  content_length: number;
  content_preview?: string;
  tier?: number;
}

export interface ReflectFinding {
  data_point: string;
  confidence: number;
  confirms_hypothesis: boolean;
  source_title: string;
  source_tier: number;
}

export interface ReflectContent {
  question?: string;
  hypothesis?: string;
  findings: ReflectFinding[];
  contradictions: string[];
  answer: string;
  confidence: number;
  hypothesis_revised: boolean;
  revised_hypothesis?: string;
}

export interface AnalyzeContent {
  key_findings: string[];
  judgments: Array<{
    claim: string;
    conviction: string;
    reasoning: string;
    supporting_evidence: string[];
    counter_evidence: string[];
  }>;
  causal_chains: string[];
  narrative_thread: string;
  evidence_gaps?: string[];
  overall_confidence?: number;
}

export interface QualityContent {
  coverage: number;
  evidence_strength: number;
  evidence_depth: number;
  contradiction_resolution: number;
  judgment_formation: number;
  gap_acknowledgment: number;
  overall: number;
  passes: boolean;
  feedback: string;
  remediation_queries?: string[];
  iteration?: number;
}

export interface ComposeContent {
  word_count: number;
  sections?: string[];
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
