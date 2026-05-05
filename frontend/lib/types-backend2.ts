/**
 * Backend2 API types — mirror the JSON shape the FastAPI server in
 * `backend2/research/api/server.py` returns.
 *
 * NOT a translation to the legacy ComparisonReport. Backend2 has its own
 * structure (topic profile, outline-based brief with frameworks/causal
 * chains, dimensional clusters, verification grounding score). The
 * frontend's `Backend2Results` view consumes this shape directly via the
 * `frontend/components/backend2/*` components.
 */

// ─── Topic profile (a0 output) ──────────────────────────────────────────

export interface Backend2TopicProfile {
  topic_subject: string;
  topic_domain: string;
  expected_metric_kinds: string[];
  key_dimensions: string[];
  positive_signals: string[];
  negative_signals: string[];
  expected_unit_families: string[];
  profile_reasoning: string;
}

// ─── Sub-questions (a2 output) ──────────────────────────────────────────

export interface Backend2SubQuestion {
  text: string;
  category: string;
  metric_hint?: string | null;
  geography?: string | null;
  time_frame?: string | null;
  source: string;
  info_value: number;
  answerability: number;
  composite: number;
  reason: string;
}

// ─── Numeric claim ──────────────────────────────────────────────────────

export interface Backend2Citation {
  url: string;
  title?: string | null;
  publisher?: string | null;
  published?: string | null;
  accessed?: string | null;
  authority_tier?: string;
}

export interface Backend2NumericClaim {
  metric: string;
  value: number | string;
  unit: string;
  as_of?: string | null;
  scope?: string | null;
  raw_excerpt: string;
  citation: Backend2Citation;
  qualifiers?: Record<string, string>;
}

// ─── Outline (Phase 4a structured composition) ─────────────────────────

export interface Backend2FrameworkRow {
  label: string;
  cells: string[];
}

export interface Backend2FrameworkTable {
  title: string;
  headers: string[];
  rows: Backend2FrameworkRow[];
}

export interface Backend2CausalChainRow {
  cause: string;
  effect: string;
  implication: string;
}

export interface Backend2CaseStudy {
  title: string;
  body: string;
}

export interface Backend2OutlineSection {
  heading: string;
  thesis: string;
  framework_table?: Backend2FrameworkTable | null;
  causal_chain_rows: Backend2CausalChainRow[];
  case_studies: Backend2CaseStudy[];
  evidence_ids_to_cite: string[];
  prose: string;
}

export interface Backend2ReportOutline {
  sections: Backend2OutlineSection[];
  contrarian_claims: string[];
  key_stats: string[];
  target_word_count: number;
}

// ─── Consolidated brief (a6 output) ─────────────────────────────────────

export interface Backend2Footnote {
  n: number;
  citation: Backend2Citation;
}

export interface Backend2Theme {
  name: string;
  summary: string;
  claims: Backend2NumericClaim[];
}

export interface Backend2Consolidated {
  claims: Backend2NumericClaim[];
  themes: Backend2Theme[];
  narrative: string;
  footnotes: Backend2Footnote[];
  outline?: Backend2ReportOutline | null;
}

// ─── Dimensional clusters (a6.5 output) ────────────────────────────────

export interface Backend2ClusterDimension {
  descriptor: string;
  unit_family: string;
  qualifier_summary?: Record<string, string[]>;
}

export interface Backend2DimensionalCluster {
  dimension: Backend2ClusterDimension;
  claims: Backend2NumericClaim[];
  n_claims: number;
  n_unique_sources: number;
  values: number[];
  mean: number;
  weighted_mean: number;
  median: number;
  stddev: number;
  min_value: number;
  max_value: number;
  pct_spread: number;
  consensus_level:
    | "high"
    | "medium"
    | "low"
    | "contested"
    | "single_source";
  outlier_claim_indices: number[];
  trend_slope_pct_per_year?: number | null;
  family_id?: string | null;
}

// ─── Verification (a8.5 output) ────────────────────────────────────────

export interface Backend2Verification {
  grounding_score: number;
  total_claims: number;
  verified_claims: number;
  fabricated: string[];
  uncertain: string[];
}

// ─── Causation (a8 output) ─────────────────────────────────────────────

export interface Backend2Driver {
  name: string;
  description: string;
  evidence: Backend2Citation[];
  confidence: string;
}

export interface Backend2Causation {
  metric: string;
  prior?: Backend2NumericClaim | null;
  current?: Backend2NumericClaim | null;
  delta_pct: number;
  drivers: Backend2Driver[];
  confidence: number;
}

// ─── Conflict (a7 output) ──────────────────────────────────────────────

export interface Backend2Conflict {
  chosen: Backend2NumericClaim;
  rejected: Array<[Backend2NumericClaim, string]>;
}

// ─── Top-level Backend2Report (what /api/research/{id}/result returns) ─

export interface Backend2Report {
  _status?: "running" | "complete" | "error";
  error?: string;

  run_id: string;
  original_query: string;
  chosen_query: string;

  // a0
  topic_profile: Backend2TopicProfile | null;

  // a1 / a2
  intent?: string;
  query_variants: unknown[];   // legacy-shaped; not used by Backend2Results
  sub_questions: Backend2SubQuestion[];

  // a3 / a4 / a5
  topic_claims: Backend2NumericClaim[];
  topic_narrative: string;
  market_claims: Backend2NumericClaim[];
  market_narrative: string;
  news_claims: Backend2NumericClaim[];
  news_narrative: string;

  scratchpad_notes: unknown[];

  // a6
  consolidated: Backend2Consolidated | null;

  // a6.5
  dimensional_clusters: Backend2DimensionalCluster[];

  // a7
  validated_claims: Backend2NumericClaim[];
  conflicts: Backend2Conflict[];

  // a8
  causations: Backend2Causation[];

  // a8.5
  verification: Backend2Verification | null;

  cost_usd: number;
}

// ─── History list item ─────────────────────────────────────────────────

export interface Backend2HistoryItem {
  id: string;
  thread_id: string;
  source: "agentic";
  saved_at: string;
  topic: string;
  topic_domain: string | null;
  latest_node: string;
  is_complete: boolean;
  word_count: number;
  n_validated_claims: number;
  n_dimensional_clusters: number;
  n_total_claims: number;
  grounding_score: number | null;
}

// ─── SSE event payloads (from /api/research/{id}/progress) ─────────────

export interface Backend2NodeEvent {
  node: string;
}

export interface Backend2JobStartedEvent {
  job_id: string;
  topic: string;
  brief: string;
}

export interface Backend2DoneEvent {
  success: boolean;
  error?: string;
}

// Surfaced once after a1 finishes; pipeline pauses until the frontend POSTs
// /select_variant.
export interface Backend2QueryVariantOption {
  index: number;        // 1-based
  text: string;         // refined query
  composite: number;    // 0-10 composite score
  reason: string;       // why this variant
}

export interface Backend2AwaitingVariantEvent {
  variants: Backend2QueryVariantOption[];
  original_query: string;
}

export interface Backend2VariantChosenEvent {
  chosen_query: string;
}

export type Backend2SseEventName =
  | "job_started"
  | "node_started"
  | "node_done"
  | "awaiting_variant_choice"
  | "variant_chosen"
  | "heartbeat"
  | "done";
