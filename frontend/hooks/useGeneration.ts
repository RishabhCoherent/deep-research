"use client";

import { useEffect, useRef, useCallback } from "react";
import { useWizardStore } from "@/lib/store";
import { getProgressUrl } from "@/lib/api";
import type { DoneEvent } from "@/lib/types";

export function useGeneration(jobId: string | null) {
  const addProgressMessage = useWizardStore((s) => s.addProgressMessage);
  const setDownloadReady = useWizardStore((s) => s.setDownloadReady);
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

    const url = getProgressUrl(jobId);
    const es = new EventSource(url);
    eventSourceRef.current = es;

    const handleMessage = (type: string) => (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        addProgressMessage({
          type: data.type || type,
          message: data.message || "",
          timestamp: Date.now(),
        });
      } catch {
        // ignore parse errors
      }
    };

    es.addEventListener("status", handleMessage("status"));
    es.addEventListener("info", handleMessage("info"));
    es.addEventListener("progress", handleMessage("progress"));
    es.addEventListener("warning", handleMessage("warning"));

    es.addEventListener("done", (e: MessageEvent) => {
      try {
        const data: DoneEvent = JSON.parse(e.data);
        if (data.success) {
          // Extract citation count from progress messages
          const msgs = useWizardStore.getState().progressMessages;
          let citations = 0;
          for (const m of msgs) {
            if (m.type === "info" && m.message.includes("Citations:")) {
              const match = m.message.match(/Citations:\s*(\d+)/);
              if (match) citations = parseInt(match[1], 10);
            }
          }
          setDownloadReady(data.file_size || 0, citations);
        } else {
          addProgressMessage({
            type: "warning",
            message: `Generation failed: ${data.error || "Unknown error"}`,
            timestamp: Date.now(),
          });
        }
      } catch {
        // ignore
      }
      cleanup();
    });

    es.onerror = () => {
      // EventSource will auto-reconnect for transient errors
    };

    return cleanup;
  }, [jobId, addProgressMessage, setDownloadReady, cleanup]);

  return { cleanup };
}
