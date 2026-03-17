"use client";

import { create } from "zustand";
import type {
  ExtractionSummary,
  ProgressMessage,
  SectionPlanSummary,
  ComparisonReport,
} from "./types";

interface WizardStore {
  // Extraction
  extractedData: Record<string, unknown> | null;
  reportTitle: string;
  sectionPlans: SectionPlanSummary[];
  extractionSummary: ExtractionSummary | null;

  // Config
  skipContent: boolean;
  topicOverride: string;

  // Generation
  jobId: string | null;
  progressMessages: ProgressMessage[];
  isGenerating: boolean;

  // Download
  downloadReady: boolean;
  outputSize: number;
  citationCount: number;

  // Actions
  setExtractionResult: (
    data: Record<string, unknown>,
    summary: ExtractionSummary
  ) => void;
  setSkipContent: (skip: boolean) => void;
  setTopicOverride: (topic: string) => void;
  startGeneration: (jobId: string) => void;
  addProgressMessage: (msg: ProgressMessage) => void;
  setDownloadReady: (size: number, citations: number) => void;
  reset: () => void;
}

export const useWizardStore = create<WizardStore>((set) => ({
  extractedData: null,
  reportTitle: "",
  sectionPlans: [],
  extractionSummary: null,
  skipContent: false,
  topicOverride: "",
  jobId: null,
  progressMessages: [],
  isGenerating: false,
  downloadReady: false,
  outputSize: 0,
  citationCount: 0,

  setExtractionResult: (data, summary) =>
    set({
      extractedData: data,
      reportTitle: summary.report_title,
      sectionPlans: summary.plans,
      extractionSummary: summary,
    }),

  setSkipContent: (skip) => set({ skipContent: skip }),
  setTopicOverride: (topic) => set({ topicOverride: topic }),

  startGeneration: (jobId) =>
    set({
      jobId,
      progressMessages: [],
      isGenerating: true,
      downloadReady: false,
    }),

  addProgressMessage: (msg) =>
    set((state) => ({
      progressMessages: [...state.progressMessages, msg],
    })),

  setDownloadReady: (size, citations) =>
    set({
      isGenerating: false,
      downloadReady: true,
      outputSize: size,
      citationCount: citations,
    }),

  reset: () =>
    set({
      extractedData: null,
      reportTitle: "",
      sectionPlans: [],
      extractionSummary: null,
      skipContent: false,
      topicOverride: "",
      jobId: null,
      progressMessages: [],
      isGenerating: false,
      downloadReady: false,
      outputSize: 0,
      citationCount: 0,
    }),
}));

// ─── Research Store ───────────────────────────────────────────

interface ResearchProgressEvent {
  layer: number;
  status: string;
  message: string;
  timestamp: number;
}

interface ResearchStore {
  topic: string;
  maxLayer: number;
  jobId: string | null;
  isResearching: boolean;
  progressEvents: ResearchProgressEvent[];
  currentLayer: number;
  completedLayers: number[];
  report: ComparisonReport | null;
  error: string | null;

  setTopic: (topic: string) => void;
  setMaxLayer: (layer: number) => void;
  startResearch: (jobId: string) => void;
  addProgressEvent: (event: ResearchProgressEvent) => void;
  setLayerStarted: (layer: number) => void;
  setLayerDone: (layer: number) => void;
  setReport: (report: ComparisonReport) => void;
  setError: (error: string) => void;
  setDone: () => void;
  reset: () => void;
}

export const useResearchStore = create<ResearchStore>((set) => ({
  topic: "",
  maxLayer: 2,
  jobId: null,
  isResearching: false,
  progressEvents: [],
  currentLayer: -1,
  completedLayers: [],
  report: null,
  error: null,

  setTopic: (topic) => set({ topic }),
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
      maxLayer: 2,
      jobId: null,
      isResearching: false,
      progressEvents: [],
      currentLayer: -1,
      completedLayers: [],
      report: null,
      error: null,
    }),
}));
