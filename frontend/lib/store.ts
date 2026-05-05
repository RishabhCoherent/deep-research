"use client";

import { create } from "zustand";
import type { ComparisonReport, ResearchNodeData, ResearchNodeStatus } from "./types";
import type {
  Backend2Report,
  Backend2QueryVariantOption,
} from "./types-backend2";

// ─── Backend selection ────────────────────────────────────────
//
// "legacy"  -> the OLD 3-layer backend at http://localhost:8000  (backend/)
// "agentic" -> the NEW backend2 multi-crew system at :8001       (backend2/)
//
// Persisted to localStorage so the choice sticks across reloads. The
// `apiBase()` getter is what every fetch in `lib/api.ts` calls.

export type BackendChoice = "legacy" | "agentic";

const _LEGACY_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const _AGENTIC_BASE = process.env.NEXT_PUBLIC_API_URL_BACKEND2 || "http://localhost:8001";

function _loadBackend(): BackendChoice {
  if (typeof window === "undefined") return "agentic";
  try {
    const v = localStorage.getItem("dr.backend") as BackendChoice | null;
    return v === "legacy" || v === "agentic" ? v : "agentic";
  } catch {
    return "agentic";
  }
}

// ─── Research Store ───────────────────────────────────────────

interface ResearchProgressEvent {
  layer: number;
  status: string;
  message: string;
  timestamp: number;
}

// Backend2-shaped progress event (different from ResearchProgressEvent
// which is layer-based). Backend2 events fire per-node, not per-layer.
export interface Backend2ProgressEvent {
  event: string;       // "job_started" | "node_started" | "node_done" | "heartbeat" | "done"
  node?: string;       // present on node_started / node_done
  data?: unknown;
  timestamp: number;
}

interface ResearchStore {
  // ─── Backend selection (persisted to localStorage) ────────────────────
  backend: BackendChoice;
  setBackend: (backend: BackendChoice) => void;
  apiBase: () => string;

  // ─── Common (used by both backends) ──────────────────────────────────
  topic: string;
  brief: string;
  maxLayer: number;
  jobId: string | null;
  isResearching: boolean;
  error: string | null;

  // ─── Legacy backend state ────────────────────────────────────────────
  progressEvents: ResearchProgressEvent[];
  currentLayer: number;
  completedLayers: number[];
  report: ComparisonReport | null;

  // Live research tree (legacy L3 only)
  graphNodes: Record<string, ResearchNodeData>;
  selectedNodeId: string | null;

  // ─── Backend2 state ──────────────────────────────────────────────────
  backend2Events: Backend2ProgressEvent[];
  backend2NodesStarted: Set<string>;
  backend2NodesDone: Set<string>;
  backend2Report: Backend2Report | null;
  // Variant-pick pause: when the SSE stream emits awaiting_variant_choice
  // we capture the 4 variants here and the progress page mounts the picker
  // until the user POSTs /select_variant.
  backend2VariantOptions: Backend2QueryVariantOption[] | null;
  backend2ChosenQuery: string | null;

  setTopic: (topic: string) => void;
  setBrief: (brief: string) => void;
  setMaxLayer: (layer: number) => void;
  startResearch: (jobId: string) => void;

  // Legacy progress
  addProgressEvent: (event: ResearchProgressEvent) => void;
  setLayerStarted: (layer: number) => void;
  setLayerDone: (layer: number) => void;
  setReport: (report: ComparisonReport) => void;

  // Backend2 progress
  addBackend2Event: (event: Backend2ProgressEvent) => void;
  setBackend2NodeStarted: (node: string) => void;
  setBackend2NodeDone: (node: string) => void;
  setBackend2Report: (report: Backend2Report) => void;
  setBackend2VariantOptions: (variants: Backend2QueryVariantOption[] | null) => void;
  setBackend2ChosenQuery: (q: string | null) => void;

  setError: (error: string) => void;
  setDone: () => void;
  reset: () => void;

  // Graph actions (legacy L3 tree)
  addGraphNode: (node: ResearchNodeData) => void;
  updateGraphNode: (nodeId: string, patch: Partial<ResearchNodeData>) => void;
  setSelectedNodeId: (id: string | null) => void;
}

export const useResearchStore = create<ResearchStore>((set, get) => ({
  // Backend selection — initialised from localStorage on first read.
  backend: _loadBackend(),

  setBackend: (backend) => {
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem("dr.backend", backend);
      } catch {}
    }
    set({ backend });
  },

  apiBase: () => (get().backend === "agentic" ? _AGENTIC_BASE : _LEGACY_BASE),

  topic: "",
  brief: "",
  maxLayer: 2,
  jobId: null,
  isResearching: false,
  error: null,

  // Legacy slots
  progressEvents: [],
  currentLayer: -1,
  completedLayers: [],
  report: null,
  graphNodes: {},
  selectedNodeId: null,

  // Backend2 slots
  backend2Events: [],
  backend2NodesStarted: new Set(),
  backend2NodesDone: new Set(),
  backend2Report: null,
  backend2VariantOptions: null,
  backend2ChosenQuery: null,

  setTopic: (topic) => set({ topic }),
  setBrief: (brief) => set({ brief }),
  setMaxLayer: (layer) => set({ maxLayer: layer }),

  startResearch: (jobId) =>
    set({
      jobId,
      isResearching: true,
      // Reset both backends' progress slots — whichever runs uses its own.
      progressEvents: [],
      currentLayer: -1,
      completedLayers: [],
      report: null,
      backend2Events: [],
      backend2NodesStarted: new Set(),
      backend2NodesDone: new Set(),
      backend2Report: null,
      backend2VariantOptions: null,
      backend2ChosenQuery: null,
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

  // Backend2 setters
  addBackend2Event: (event) =>
    set((state) => ({
      backend2Events: [...state.backend2Events, event],
    })),

  setBackend2NodeStarted: (node) =>
    set((state) => {
      const next = new Set(state.backend2NodesStarted);
      next.add(node);
      return { backend2NodesStarted: next };
    }),

  setBackend2NodeDone: (node) =>
    set((state) => {
      const next = new Set(state.backend2NodesDone);
      next.add(node);
      return { backend2NodesDone: next };
    }),

  setBackend2Report: (backend2Report) => set({ backend2Report }),

  setBackend2VariantOptions: (backend2VariantOptions) =>
    set({ backend2VariantOptions }),

  setBackend2ChosenQuery: (backend2ChosenQuery) =>
    set({ backend2ChosenQuery }),

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
      backend2Events: [],
      backend2NodesStarted: new Set(),
      backend2NodesDone: new Set(),
      backend2Report: null,
      backend2VariantOptions: null,
      backend2ChosenQuery: null,
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
