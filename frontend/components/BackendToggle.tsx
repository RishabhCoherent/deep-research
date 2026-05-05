"use client";

import { useEffect, useState } from "react";
import { useResearchStore, type BackendChoice } from "@/lib/store";
import { Cpu, Layers } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

export function BackendToggle({ className }: { className?: string }) {
  const backend = useResearchStore((s) => s.backend);
  const setBackend = useResearchStore((s) => s.setBackend);
  const isResearching = useResearchStore((s) => s.isResearching);

  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <div
        className={cn(
          "h-8 w-44 rounded-md border border-foreground/10 bg-foreground/5",
          className,
        )}
      />
    );
  }

  return (
    <Select
      value={backend}
      onValueChange={(v) => setBackend(v as BackendChoice)}
      disabled={isResearching}
    >
      <SelectTrigger
        size="sm"
        className={cn(
          "min-w-44 font-mono text-xs uppercase tracking-wider",
          backend === "agentic"
            ? "border-purple/40 text-purple"
            : "border-foreground/20 text-foreground/80",
          className,
        )}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="agentic">
          <Cpu className="size-3.5" />
          <span>Agentic · backend2</span>
        </SelectItem>
        <SelectItem value="legacy">
          <Layers className="size-3.5" />
          <span>Legacy · 3-layer</span>
        </SelectItem>
      </SelectContent>
    </Select>
  );
}
