"use client";

import { useEffect, useRef, useCallback } from "react";
import { useResearchStore } from "@/lib/store";
import { getResearchProgressUrl, getResearchResult } from "@/lib/api";
import type { ResearchNodeData, NodeCreatedEvent, NodeCompleteEvent } from "@/lib/types";

export function useResearch(jobId: string | null) {
  const addProgressEvent = useResearchStore((s) => s.addProgressEvent);
  const setLayerStarted = useResearchStore((s) => s.setLayerStarted);
  const setLayerDone = useResearchStore((s) => s.setLayerDone);
  const setReport = useResearchStore((s) => s.setReport);
  const setError = useResearchStore((s) => s.setError);
  const setDone = useResearchStore((s) => s.setDone);
  const addGraphNode = useResearchStore((s) => s.addGraphNode);
  const updateGraphNode = useResearchStore((s) => s.updateGraphNode);
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
      } catch { /* ignore */ }
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
      } catch { /* ignore */ }
    });

    // ── Node graph SSE events ────────────────────────────────────
    // node_created: a new deep-research node was spawned
    es.addEventListener("layer_node_created", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        const inner = typeof data === "string" ? JSON.parse(data) : data;
        // inner.message is a JSON string containing NodeCreatedEvent
        const evt: NodeCreatedEvent = typeof inner.message === "string"
          ? JSON.parse(inner.message)
          : inner.message;

        const newNode: ResearchNodeData = {
          id: evt.node_id,
          parent_id: evt.parent_id,
          depth: evt.depth,
          query: evt.query,
          why_created: evt.why,
          trigger_finding: evt.trigger_finding ?? "",
          sq_id: evt.sq_id || null,
          hypothesis: "",
          answer: "",
          confidence: 0,
          status: "exploring",
          children_ids: [],
          evidence_ids: [],
        };
        addGraphNode(newNode);

        addProgressEvent({
          layer: inner.layer ?? 2,
          status: "node_created",
          message: `↳ Depth ${evt.depth}: ${evt.query.slice(0, 60)}${evt.query.length > 60 ? "…" : ""}`,
          timestamp: Date.now(),
        });
      } catch { /* ignore */ }
    });

    // node_thinking: node is forming a hypothesis
    es.addEventListener("layer_node_thinking", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        const inner = typeof data === "string" ? JSON.parse(data) : data;
        const evt = typeof inner.message === "string" ? JSON.parse(inner.message) : inner.message;
        if (evt?.node_id) {
          updateGraphNode(evt.node_id, { status: "exploring" });
        }
      } catch { /* ignore */ }
    });

    // node_complete: node finished research
    es.addEventListener("layer_node_complete", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        const inner = typeof data === "string" ? JSON.parse(data) : data;
        const evt: NodeCompleteEvent = typeof inner.message === "string"
          ? JSON.parse(inner.message)
          : inner.message;

        if (evt?.node_id) {
          updateGraphNode(evt.node_id, {
            status: evt.status,
            confidence: evt.confidence,
            answer: evt.answer ?? "",
          });
          addProgressEvent({
            layer: inner.layer ?? 2,
            status: "node_complete",
            message: `✓ Node complete (${Math.round(evt.confidence * 100)}% confidence, ${evt.evidence_count} evidence)`,
            timestamp: Date.now(),
          });
        }
      } catch { /* ignore */ }
    });

    // node_graph: summary message (tree stats)
    es.addEventListener("layer_node_graph", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        const inner = typeof data === "string" ? JSON.parse(data) : data;
        addProgressEvent({
          layer: inner.layer ?? 2,
          status: "node_graph",
          message: inner.message || "Research tree updated",
          timestamp: Date.now(),
        });
      } catch { /* ignore */ }
    });

    // ── Standard intermediate phase events ───────────────────────
    const intermediateStatuses = [
      "dissect", "plan", "investigate", "synthesize", "compose", "format",
      "scoping", "evaluating", "analyze", "quality_gate",
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
        } catch { /* ignore */ }
      });
    }

    // done event — fetch the full result
    es.addEventListener("done", async (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        const inner = typeof data === "string" ? JSON.parse(data) : data;
        if (inner.success) {
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
  }, [jobId, addProgressEvent, setLayerStarted, setLayerDone, setReport, setError, setDone, addGraphNode, updateGraphNode, cleanup]);

  return { cleanup };
}
