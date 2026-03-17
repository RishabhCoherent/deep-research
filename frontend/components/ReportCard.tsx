"use client";

import { useEffect, useState } from "react";

interface ReportCardProps {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  suffix?: string;
  isText?: boolean;
}

export function ReportCard({
  icon,
  label,
  value,
  suffix,
  isText,
}: ReportCardProps) {
  const [displayValue, setDisplayValue] = useState(isText ? value : 0);

  // Count-up animation for numbers
  useEffect(() => {
    if (isText || typeof value !== "number") {
      setDisplayValue(value);
      return;
    }

    const target = value;
    const duration = 1500;
    const steps = 40;
    const stepTime = duration / steps;
    let current = 0;
    let step = 0;

    const timer = setInterval(() => {
      step++;
      // Ease-out curve
      const progress = 1 - Math.pow(1 - step / steps, 3);
      current = Math.round(target * progress);
      setDisplayValue(current);

      if (step >= steps) {
        setDisplayValue(target);
        clearInterval(timer);
      }
    }, stepTime);

    return () => clearInterval(timer);
  }, [value, isText]);

  return (
    <div className="glass-card-hover p-5">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple/20 text-orange">
          {icon}
        </div>
        <div className="min-w-0">
          <p className="text-xs text-warm-gray">{label}</p>
          {isText ? (
            <p className="mt-0.5 text-sm font-semibold text-foreground truncate">
              {displayValue}
            </p>
          ) : (
            <p className="mt-0.5 text-2xl font-bold text-gradient">
              {displayValue}
              {suffix && (
                <span className="ml-1 text-sm font-normal text-warm-gray">
                  {suffix}
                </span>
              )}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
