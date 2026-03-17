"use client";

import { useState, useEffect } from "react";
import { checkHealth } from "@/lib/api";
import type { HealthStatus } from "@/lib/types";

export function useHealth(intervalMs = 30000) {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function check() {
      try {
        const status = await checkHealth();
        if (mounted) {
          setHealth(status);
          setLoading(false);
        }
      } catch {
        if (mounted) {
          setHealth(null);
          setLoading(false);
        }
      }
    }

    check();
    const id = setInterval(check, intervalMs);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [intervalMs]);

  return { health, loading };
}
