"use client";

import { create } from "zustand";
import type { ComparisonReport, ResearchNodeData, ResearchNodeStatus } from "./types";

// ─── Research Store ───────────────────────────────────────────

interface ResearchProgressEvent {
  layer: number;
  status: string;
  message: string;
  timestamp: number;
}

interface ResearchStore {
  topic: string;
  brief: string;
  maxLayer: number;
  jobId: string | null;
  isResearching: boolean;
  progressEvents: ResearchProgressEvent[];
  currentLayer: number;
  completedLayers: number[];
  report: ComparisonReport | null;
  error: string | null;

  // Research tree graph state (live during progress)
  graphNodes: Record<string, ResearchNodeData>;
  selectedNodeId: string | null;

  setTopic: (topic: string) => void;
  setBrief: (brief: string) => void;
  setMaxLayer: (layer: number) => void;
  startResearch: (jobId: string) => void;
  addProgressEvent: (event: ResearchProgressEvent) => void;
  setLayerStarted: (layer: number) => void;
  setLayerDone: (layer: number) => void;
  setReport: (report: ComparisonReport) => void;
  setError: (error: string) => void;
  setDone: () => void;
  reset: () => void;

  // Graph actions
  addGraphNode: (node: ResearchNodeData) => void;
  updateGraphNode: (nodeId: string, patch: Partial<ResearchNodeData>) => void;
  setSelectedNodeId: (id: string | null) => void;
}

export const useResearchStore = create<ResearchStore>((set) => ({
  topic: "",
  brief: "",
  maxLayer: 2,
  jobId: null,
  isResearching: false,
  progressEvents: [],
  currentLayer: -1,
  completedLayers: [],
  report: null,
  error: null,
  graphNodes: {},
  selectedNodeId: null,

  setTopic: (topic) => set({ topic }),
  setBrief: (brief) => set({ brief }),
  setMaxLayer: (layer) => set({ maxLayer: layer }),

  startResearch: (jobId) =>
    set({
      jobId,
      isResearching: true,
      progressEvents: [],
      currentLayer: -1,
      completedLayers: [],
      report: null,
      error: null,
    }),

  addProgressEvent: (event) =>
    set((state) => ({
      progressEvents: [...state.progressEvents, event],
    })),

  setLayerStarted: (layer) => set({ currentLayer: layer }),

  setLayerDone: (layer) =>
    set((state) => ({
      completedLayers: [...state.completedLayers, layer],
    })),

  setReport: (report) => set({ report }),

  setError: (error) => set({ error, isResearching: false }),

  setDone: () => set({ isResearching: false }),

  reset: () =>
    set({
      topic: "",
      brief: "",
      maxLayer: 2,
      jobId: null,
      isResearching: false,
      progressEvents: [],
      currentLayer: -1,
      completedLayers: [],
      report: null,
      error: null,
      graphNodes: {},
      selectedNodeId: null,
    }),

  addGraphNode: (node) =>
    set((state) => ({
      graphNodes: { ...state.graphNodes, [node.id]: node },
    })),

  updateGraphNode: (nodeId, patch) =>
    set((state) => {
      const existing = state.graphNodes[nodeId];
      if (!existing) return state;
      return {
        graphNodes: {
          ...state.graphNodes,
          [nodeId]: { ...existing, ...patch },
        },
      };
    }),

  setSelectedNodeId: (id) => set({ selectedNodeId: id }),
}));
