// ─── Report Generator Types ──────────────────────────────────

export interface SectionPlanSummary {
  number: number;
  type: string;
  title: string;
}

export interface ExtractionSummary {
  report_title: string;
  subtitle: string;
  section_count: number;
  sheet_count: number;
  sheets: string[];
  plans: SectionPlanSummary[];
}

export interface ExtractionResponse {
  extracted_data: Record<string, unknown>;
  summary: ExtractionSummary;
}

export interface GenerateResponse {
  job_id: string;
}

export interface HealthStatus {
  openai: boolean;
  searxng: boolean;
  tavily: boolean;
}

export interface ProgressMessage {
  type: "status" | "info" | "progress" | "warning" | "done";
  message: string;
  timestamp: number;
}

export interface DoneEvent {
  type: "done";
  success: boolean;
  file_size?: number;
  error?: string;
}

export type SectionType =
  | "overview"
  | "key_insights"
  | "segment"
  | "region"
  | "competitive"
  | "appendix";

export const SECTION_TYPE_COLORS: Record<string, string> = {
  overview: "bg-purple text-white",
  key_insights: "bg-orange-dark text-white",
  segment: "bg-emerald-600 text-white",
  region: "bg-amber-600 text-white",
  competitive: "bg-coral text-white",
  appendix: "bg-warm-gray text-white",
};

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

export interface LayerComparisonData {
  from_layer: number;
  to_layer: number;
  improvements: string[];
  score_delta: number;
  key_evidence: string;
  overall_verdict: string;
}

export interface ComparisonReport {
  topic: string;
  layers: LayerResult[];
  evaluations: LayerEvaluation[];
  summary: string;
  layer_comparisons?: LayerComparisonData[];
}

export const LAYER_NAMES: Record<number, string> = {
  0: "Baseline (Prompt-Driven)",
  1: "Enhanced (Search + Synthesis)",
  2: "CMI Expert (Agentic Pipeline)",
};

export const LAYER_DESCRIPTIONS: Record<number, string> = {
  0: "Model knowledge only — no web research",
  1: "Web search + synthesis via ReAct agent",
  2: "Full pipeline: Plan → Research → Verify → Write",
};

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
