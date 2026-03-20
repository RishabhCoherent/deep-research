"use client";

import { useEffect, useRef, useCallback } from "react";
import { useResearchStore } from "@/lib/store";
import { getResearchProgressUrl, getResearchResult } from "@/lib/api";

export function useResearch(jobId: string | null) {
  const addProgressEvent = useResearchStore((s) => s.addProgressEvent);
  const setLayerStarted = useResearchStore((s) => s.setLayerStarted);
  const setLayerDone = useResearchStore((s) => s.setLayerDone);
  const setReport = useResearchStore((s) => s.setReport);
  const setError = useResearchStore((s) => s.setError);
  const setDone = useResearchStore((s) => s.setDone);
  const eventSourceRef = useRef<EventSource | null>(null);

  const cleanup = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!jobId) return;

    cleanup();

    const url = getResearchProgressUrl(jobId);
    const es = new EventSource(url);
    eventSourceRef.current = es;

    // layer_start events
    es.addEventListener("layer_start", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        const inner = typeof data === "string" ? JSON.parse(data) : data;
        setLayerStarted(inner.layer);
        addProgressEvent({
          layer: inner.layer,
          status: "start",
          message: inner.message || `Starting layer ${inner.layer}`,
          timestamp: Date.now(),
        });
      } catch {
        // ignore
      }
    });

    // layer_done events
    es.addEventListener("layer_done", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        const inner = typeof data === "string" ? JSON.parse(data) : data;
        setLayerDone(inner.layer);
        addProgressEvent({
          layer: inner.layer,
          status: "done",
          message: inner.message || `Layer ${inner.layer} complete`,
          timestamp: Date.now(),
        });
      } catch {
        // ignore
      }
    });

    // Intermediate phase events (expert pipeline: dissect, plan, investigate, synthesize, compose)
    const intermediateStatuses = [
      "dissect", "plan", "investigate", "synthesize", "compose", "format",
      "scoping", "evaluating",
    ];
    for (const status of intermediateStatuses) {
      es.addEventListener(`layer_${status}`, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          const inner = typeof data === "string" ? JSON.parse(data) : data;
          addProgressEvent({
            layer: inner.layer,
            status,
            message: inner.message || `${status}...`,
            timestamp: Date.now(),
          });
        } catch {
          // ignore
        }
      });
    }

    // done event — fetch the full result
    es.addEventListener("done", async (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        const inner = typeof data === "string" ? JSON.parse(data) : data;

        if (inner.success) {
          // Fetch the full comparison report
          const report = await getResearchResult(jobId);
          setReport(report);
        } else {
          setError(inner.error || "Research failed");
        }
      } catch {
        setError("Failed to parse completion event");
      }
      setDone();
      cleanup();
    });

    es.onerror = () => {
      // EventSource auto-reconnects for transient errors
    };

    return cleanup;
  }, [jobId, addProgressEvent, setLayerStarted, setLayerDone, setReport, setError, setDone, cleanup]);

  return { cleanup };
}
