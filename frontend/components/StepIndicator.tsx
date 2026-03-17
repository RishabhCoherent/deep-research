"use client";

import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

const STEPS = ["Upload", "Extract", "Generate", "Download"] as const;

interface StepIndicatorProps {
  currentStep: number; // 1-4
}

export function StepIndicator({ currentStep }: StepIndicatorProps) {
  return (
    <div className="flex items-center justify-center gap-0 py-6">
      {STEPS.map((label, i) => {
        const stepNum = i + 1;
        const isCompleted = stepNum < currentStep;
        const isActive = stepNum === currentStep;
        const isPending = stepNum > currentStep;

        return (
          <div key={label} className="flex items-center">
            {/* Step circle + label */}
            <div className="flex flex-col items-center gap-1.5">
              <div
                className={cn(
                  "flex h-10 w-10 items-center justify-center rounded-full text-sm font-semibold transition-all duration-500",
                  isCompleted &&
                    "bg-purple text-white",
                  isActive &&
                    "bg-orange text-white animate-pulse-glow",
                  isPending &&
                    "border border-surface-3 bg-surface-2 text-warm-gray"
                )}
              >
                {isCompleted ? (
                  <Check className="h-4 w-4" />
                ) : (
                  stepNum
                )}
              </div>
              <span
                className={cn(
                  "text-xs font-medium transition-colors duration-300",
                  isCompleted && "text-purple-light",
                  isActive && "text-orange",
                  isPending && "text-warm-gray"
                )}
              >
                {label}
              </span>
            </div>

            {/* Connector line */}
            {i < STEPS.length - 1 && (
              <div
                className={cn(
                  "mx-3 h-[2px] w-16 rounded-full transition-colors duration-500",
                  stepNum < currentStep ? "bg-purple" : "bg-surface-3"
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
