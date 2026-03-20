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

  useEffect(() => {
    if (isText || typeof value !== "number") {
      setDisplayValue(value);
      return;
    }

    const target = value;
    const duration = 1500;
    const steps = 40;
    const stepTime = duration / steps;
    let step = 0;

    const timer = setInterval(() => {
      step++;
      const progress = 1 - Math.pow(1 - step / steps, 3);
      setDisplayValue(Math.round(target * progress));

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
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-foreground/5 text-foreground">
          {icon}
        </div>
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">{label}</p>
          {isText ? (
            <p className="mt-0.5 text-sm font-semibold text-foreground truncate">
              {displayValue}
            </p>
          ) : (
            <p className="mt-0.5 text-2xl font-display">
              {displayValue}
              {suffix && (
                <span className="ml-1 text-sm font-normal text-muted-foreground">
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
