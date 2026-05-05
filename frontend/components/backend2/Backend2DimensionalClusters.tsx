"use client";

/**
 * Backend2DimensionalClusters — 3D scatter plot of a6.5 dimensional clusters.
 *
 * Each cluster is a dot in 3D space:
 *   X = n_unique_sources   Y = pct_spread (%)   Z = consensus rank
 * Dot colour = consensus level   Dot size = n_claims
 *
 * Drag to orbit. Hover for tooltip. Falls back to dummy data when empty.
 */

import { useState } from "react";
import { motion } from "framer-motion";
import type { Backend2DimensionalCluster } from "@/lib/types-backend2";
import ClusterScatterPlot from "./ClusterScatterPlot";

interface Props {
  clusters: Backend2DimensionalCluster[];
}

export default function Backend2DimensionalClusters({ clusters }: Props) {
  const [showSingleSource, setShowSingleSource] = useState(false);

  const multi  = clusters.filter((c) => c.n_unique_sources >= 2).length;
  const single = clusters.length - multi;
  const isDummy = clusters.length === 0;

  const visible = showSingleSource
    ? clusters
    : clusters.filter((c) => c.n_unique_sources >= 2);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.1 }}
      className="glass-card p-6 mb-6"
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-5 gap-3 flex-wrap">
        <div>
          <span className="inline-flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-muted-foreground mb-1">
            <span className="w-5 h-px bg-foreground/30" />
            Dimensional Clusters · a6.5
          </span>
          <h3 className="font-display text-xl text-foreground">
            {isDummy ? "Cluster map — demo data" : "Numeric consensus across sources"}
          </h3>
          {isDummy && (
            <p className="text-xs text-muted-foreground mt-0.5">
              No clusters in this run — showing example layout
            </p>
          )}
        </div>

        {!isDummy && (
          <div className="flex items-center gap-3 text-xs font-mono">
            <span className="text-emerald-700 font-medium">{multi} multi-source</span>
            <span className="text-foreground/20">·</span>
            <span className="text-muted-foreground">{single} single-source</span>
            {single > 0 && (
              <button
                onClick={() => setShowSingleSource((v) => !v)}
                className="text-[var(--color-purple)] hover:underline"
              >
                {showSingleSource ? "hide" : "show"} single-source
              </button>
            )}
          </div>
        )}
      </div>

      {/* Scatter plot */}
      <ClusterScatterPlot clusters={visible} isDummy={isDummy} />
    </motion.div>
  );
}
