"use client";

import { Sidebar } from "./Sidebar";
import { Check, Settings, Loader2, BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";

const STEPS = [
  { label: "Configure", icon: Settings },
  { label: "Running", icon: Loader2 },
  { label: "Results", icon: BarChart3 },
];

interface ResearchLayoutProps {
  children: React.ReactNode;
  currentStep: number; // 1, 2, or 3
}

export function ResearchLayout({ children, currentStep }: ResearchLayoutProps) {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex flex-1 flex-col overflow-hidden">
        <div className="border-b border-surface-3 bg-surface-0">
          <div className="flex items-center justify-center gap-2 px-8 py-3">
            {STEPS.map((step, i) => {
              const stepNum = i + 1;
              const isActive = stepNum === currentStep;
              const isDone = stepNum < currentStep;
              const Icon = step.icon;

              return (
                <div key={step.label} className="flex items-center gap-2">
                  {i > 0 && (
                    <div
                      className={cn(
                        "h-px w-10",
                        isDone ? "bg-purple" : "bg-surface-3"
                      )}
                    />
                  )}
                  <div className="flex items-center gap-2">
                    <div
                      className={cn(
                        "flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold transition-all",
                        isActive && "bg-orange text-white",
                        isDone && "bg-purple text-white",
                        !isActive && !isDone && "bg-surface-3 text-warm-gray"
                      )}
                    >
                      {isDone ? (
                        <Check className="h-3.5 w-3.5" />
                      ) : isActive && stepNum === 2 ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Icon className="h-3.5 w-3.5" />
                      )}
                    </div>
                    <span
                      className={cn(
                        "text-xs font-medium",
                        isActive && "text-foreground",
                        isDone && "text-purple-light",
                        !isActive && !isDone && "text-warm-gray"
                      )}
                    >
                      {step.label}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-8 py-6">{children}</div>
      </main>
    </div>
  );
}
