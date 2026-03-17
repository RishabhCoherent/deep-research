"use client";

import { Badge } from "@/components/ui/badge";
import type { SectionPlanSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

const TYPE_STYLES: Record<string, string> = {
  overview: "bg-purple/20 text-purple-light border-purple/40",
  key_insights: "bg-orange-dark/20 text-orange-light border-orange-dark/40",
  segment: "bg-emerald-600/20 text-emerald-400 border-emerald-600/40",
  region: "bg-amber-600/20 text-amber-400 border-amber-600/40",
  competitive: "bg-coral/20 text-orange-light border-coral/40",
  appendix: "bg-warm-gray/20 text-warm-gray-light border-warm-gray/40",
};

interface SectionPlanListProps {
  plans: SectionPlanSummary[];
}

export function SectionPlanList({ plans }: SectionPlanListProps) {
  return (
    <div className="space-y-2">
      {plans.map((plan, i) => (
        <div
          key={i}
          className="flex items-center gap-3 rounded-lg border border-surface-3 bg-surface-2/40 px-4 py-3 transition-colors hover:bg-surface-2/70"
          style={{ animationDelay: `${i * 50}ms` }}
        >
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-surface-3 text-xs font-bold text-warm-gray">
            S{plan.number}
          </span>
          <Badge
            variant="outline"
            className={cn(
              "shrink-0 text-[10px] uppercase tracking-wider",
              TYPE_STYLES[plan.type] || TYPE_STYLES.appendix
            )}
          >
            {plan.type.replace("_", " ")}
          </Badge>
          <span className="truncate text-sm text-foreground">{plan.title}</span>
        </div>
      ))}
    </div>
  );
}
