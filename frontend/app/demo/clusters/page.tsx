"use client";

import Backend2DimensionalClusters from "@/components/backend2/Backend2DimensionalClusters";
import type { Backend2DimensionalCluster } from "@/lib/types-backend2";

const DEMO_CLUSTERS: Backend2DimensionalCluster[] = [
  {
    dimension: { descriptor: "Global EV market size 2025", unit_family: "USD" },
    consensus_level: "high", n_unique_sources: 7, n_claims: 5,
    pct_spread: 0.08, weighted_mean: 320, mean: 310, median: 315,
    stddev: 12, min_value: 290, max_value: 350, values: [290,310,315,320,350],
    outlier_claim_indices: [], trend_slope_pct_per_year: 18, family_id: null, claims: [],
  },
  {
    dimension: { descriptor: "CAGR 2025–2030", unit_family: "percent" },
    consensus_level: "medium", n_unique_sources: 4, n_claims: 3,
    pct_spread: 0.22, weighted_mean: 21, mean: 22, median: 21,
    stddev: 3.2, min_value: 17, max_value: 26, values: [17,21,26],
    outlier_claim_indices: [], trend_slope_pct_per_year: null, family_id: null, claims: [],
  },
  {
    dimension: { descriptor: "Battery pack cost $/kWh", unit_family: "USD" },
    consensus_level: "high", n_unique_sources: 6, n_claims: 6,
    pct_spread: 0.12, weighted_mean: 110, mean: 112, median: 110,
    stddev: 8, min_value: 98, max_value: 128, values: [98,105,110,112,120,128],
    outlier_claim_indices: [5], trend_slope_pct_per_year: -9, family_id: null, claims: [],
  },
  {
    dimension: { descriptor: "Public charging infra spend 2025", unit_family: "USD" },
    consensus_level: "low", n_unique_sources: 2, n_claims: 2,
    pct_spread: 0.45, weighted_mean: 84, mean: 84, median: 84,
    stddev: 19, min_value: 65, max_value: 103, values: [65,103],
    outlier_claim_indices: [], trend_slope_pct_per_year: 22, family_id: null, claims: [],
  },
  {
    dimension: { descriptor: "Policy subsidy $/vehicle", unit_family: "USD" },
    consensus_level: "contested", n_unique_sources: 3, n_claims: 4,
    pct_spread: 0.61, weighted_mean: 7500, mean: 7200, median: 7000,
    stddev: 1800, min_value: 5000, max_value: 10000, values: [5000,6500,8000,10000],
    outlier_claim_indices: [3], trend_slope_pct_per_year: null, family_id: null, claims: [],
  },
  {
    dimension: { descriptor: "Average range improvement % YoY", unit_family: "percent" },
    consensus_level: "medium", n_unique_sources: 5, n_claims: 4,
    pct_spread: 0.18, weighted_mean: 15, mean: 14.8, median: 15,
    stddev: 1.6, min_value: 12, max_value: 18, values: [12,14,15,18],
    outlier_claim_indices: [], trend_slope_pct_per_year: null, family_id: null, claims: [],
  },
  {
    dimension: { descriptor: "Mineral supply risk score", unit_family: "score" },
    consensus_level: "single_source", n_unique_sources: 1, n_claims: 1,
    pct_spread: 0, weighted_mean: 6.8, mean: 6.8, median: 6.8,
    stddev: 0, min_value: 6.8, max_value: 6.8, values: [6.8],
    outlier_claim_indices: [], trend_slope_pct_per_year: null, family_id: null, claims: [],
  },
  {
    dimension: { descriptor: "BEV market share (global)", unit_family: "percent" },
    consensus_level: "high", n_unique_sources: 8, n_claims: 7,
    pct_spread: 0.09, weighted_mean: 18, mean: 17.8, median: 18,
    stddev: 1.2, min_value: 16, max_value: 21, values: [16,17,17,18,18,19,21],
    outlier_claim_indices: [], trend_slope_pct_per_year: 14, family_id: null, claims: [],
  },
  {
    dimension: { descriptor: "Fleet electrification rate — commercial", unit_family: "percent" },
    consensus_level: "low", n_unique_sources: 2, n_claims: 2,
    pct_spread: 0.38, weighted_mean: 9, mean: 9, median: 9,
    stddev: 2.4, min_value: 6.5, max_value: 11.5, values: [6.5,11.5],
    outlier_claim_indices: [], trend_slope_pct_per_year: 7, family_id: null, claims: [],
  },
  {
    dimension: { descriptor: "CO₂ reduction vs ICE lifetime", unit_family: "percent" },
    consensus_level: "high", n_unique_sources: 6, n_claims: 5,
    pct_spread: 0.14, weighted_mean: 52, mean: 51, median: 52,
    stddev: 4.5, min_value: 44, max_value: 59, values: [44,49,52,55,59],
    outlier_claim_indices: [], trend_slope_pct_per_year: null, family_id: null, claims: [],
  },
  {
    dimension: { descriptor: "Consumer payback period", unit_family: "months" },
    consensus_level: "medium", n_unique_sources: 3, n_claims: 3,
    pct_spread: 0.27, weighted_mean: 6.2, mean: 6.5, median: 6.2,
    stddev: 1.0, min_value: 5.5, max_value: 7.8, values: [5.5,6.2,7.8],
    outlier_claim_indices: [], trend_slope_pct_per_year: -4, family_id: null, claims: [],
  },
  {
    dimension: { descriptor: "Solid-state battery commercialisation ETA", unit_family: "years" },
    consensus_level: "contested", n_unique_sources: 3, n_claims: 4,
    pct_spread: 0.55, weighted_mean: 4, mean: 5, median: 4,
    stddev: 2.2, min_value: 2, max_value: 8, values: [2,3,5,8],
    outlier_claim_indices: [3], trend_slope_pct_per_year: null, family_id: null, claims: [],
  },
];

export default function ClusterDemoPage() {
  return (
    <div className="min-h-screen bg-background px-8 py-8 max-w-6xl mx-auto">
      <div className="mb-8">
        <p className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-1">
          Component preview · dummy data
        </p>
        <h1 className="text-3xl font-display">Cluster Scatter Plot</h1>
        <p className="text-sm text-muted-foreground mt-2">
          12 EV-market clusters — drag to orbit, hover a dot for detail
        </p>
      </div>

      <Backend2DimensionalClusters clusters={DEMO_CLUSTERS} />
    </div>
  );
}
