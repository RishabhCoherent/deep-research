"use client";

import { useEffect, useRef, useCallback } from "react";
import { useResearchStore } from "@/lib/store";
import {
  getResearchProgressUrl,
  getResearchResult,
  getBackend2Result,
} from "@/lib/api";
import type {
  ResearchNodeData,
  NodeCreatedEvent,
  NodeCompleteEvent,
} from "@/lib/types";

export function useResearch(jobId: string | null) {
  // Both backends share these.
  const backend = useResearchStore((s) => s.backend);
  const setError = useResearchStore((s) => s.setError);
  const setDone = useResearchStore((s) => s.setDone);

  // Legacy state setters
  const addProgressEvent = useResearchStore((s) => s.addProgressEvent);
  const setLayerStarted = useResearchStore((s) => s.setLayerStarted);
  const setLayerDone = useResearchStore((s) => s.setLayerDone);
  const setReport = useResearchStore((s) => s.setReport);
  const addGraphNode = useResearchStore((s) => s.addGraphNode);
  const updateGraphNode = useResearchStore((s) => s.updateGraphNode);

  // Backend2 state setters
  const addBackend2Event = useResearchStore((s) => s.addBackend2Event);
  const setBackend2NodeStarted = useResearchStore((s) => s.setBackend2NodeStarted);
  const setBackend2NodeDone = useResearchStore((s) => s.setBackend2NodeDone);
  const setBackend2Report = useResearchStore((s) => s.setBackend2Report);
  const setBackend2VariantOptions = useResearchStore((s) => s.setBackend2VariantOptions);
  const setBackend2ChosenQuery = useResearchStore((s) => s.setBackend2ChosenQuery);

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

    // ─── Backend2 wiring ────────────────────────────────────────
    // Backend2 events: job_started, node_started, node_done, heartbeat, done.
    // Each `data` is a JSON-encoded dict.
    if (backend === "agentic") {
      const _parse = (e: MessageEvent): unknown => {
        try {
          return JSON.parse(e.data);
        } catch {
          return null;
        }
      };

      es.addEventListener("job_started", (e: MessageEvent) => {
        const data = _parse(e);
        addBackend2Event({
          event: "job_started",
          data,
          timestamp: Date.now(),
        });
      });

      es.addEventListener("node_started", (e: MessageEvent) => {
        const data = _parse(e) as { node?: string } | null;
        if (data?.node) {
          setBackend2NodeStarted(data.node);
        }
        addBackend2Event({
          event: "node_started",
          node: data?.node,
          data,
          timestamp: Date.now(),
        });
      });

      es.addEventListener("node_done", (e: MessageEvent) => {
        const data = _parse(e) as { node?: string } | null;
        if (data?.node) {
          setBackend2NodeDone(data.node);
        }
        addBackend2Event({
          event: "node_done",
          node: data?.node,
          data,
          timestamp: Date.now(),
        });
      });

      // Mandatory variant pick after a1: pipeline pauses until /select_variant.
      es.addEventListener("awaiting_variant_choice", (e: MessageEvent) => {
        const data = _parse(e) as
          | { variants?: unknown; original_query?: string }
          | null;
        const variants = Array.isArray(data?.variants)
          ? // The shape is enforced server-side; cast loosely here and let
            // the picker component do the runtime narrowing.
            (data!.variants as Array<{
              index: number;
              text: string;
              composite: number;
              reason: string;
            }>)
          : null;
        if (variants && variants.length > 0) {
          setBackend2VariantOptions(variants);
        }
        addBackend2Event({
          event: "awaiting_variant_choice",
          data,
          timestamp: Date.now(),
        });
      });

      es.addEventListener("variant_chosen", (e: MessageEvent) => {
        const data = _parse(e) as { chosen_query?: string } | null;
        if (data?.chosen_query) {
          setBackend2ChosenQuery(data.chosen_query);
        }
        // Clear the picker now that the user has picked.
        setBackend2VariantOptions(null);
        addBackend2Event({
          event: "variant_chosen",
          data,
          timestamp: Date.now(),
        });
      });

      es.addEventListener("heartbeat", () => {
        // Connection-keepalive — no state mutation needed.
      });

      es.addEventListener("done", async (e: MessageEvent) => {
        const data = _parse(e) as { success?: boolean; error?: string } | null;
        addBackend2Event({
          event: "done",
          data,
          timestamp: Date.now(),
        });
        if (data?.success === false) {
          setError(data.error || "Backend2 run failed");
        } else {
          try {
            const report = await getBackend2Result(jobId);
            setBackend2Report(report);
          } catch (err) {
            setError(
              err instanceof Error ? err.message : "Failed to fetch backend2 result",
            );
          }
        }
        setDone();
        cleanup();
      });

      es.onerror = () => {
        // EventSource auto-reconnects for transient errors.
      };

      return cleanup;
    }

    // ─── Legacy (3-layer) wiring ────────────────────────────────
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
  }, [
    jobId,
    backend,
    addProgressEvent,
    setLayerStarted,
    setLayerDone,
    setReport,
    setError,
    setDone,
    addGraphNode,
    updateGraphNode,
    addBackend2Event,
    setBackend2NodeStarted,
    setBackend2NodeDone,
    setBackend2Report,
    setBackend2VariantOptions,
    setBackend2ChosenQuery,
    cleanup,
  ]);

  return { cleanup };
}
