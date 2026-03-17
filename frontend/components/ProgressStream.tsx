"use client";

import { useEffect, useRef } from "react";
import {
  Info,
  AlertTriangle,
  Activity,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ProgressMessage } from "@/lib/types";

interface ProgressStreamProps {
  messages: ProgressMessage[];
  progress: number; // 0-100
}

export function ProgressStream({ messages, progress }: ProgressStreamProps) {
  const logRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [messages]);

  // Current status (last "status" message)
  const currentStatus =
    [...messages].reverse().find((m) => m.type === "status")?.message ||
    "Initializing...";

  return (
    <div className="space-y-6">
      {/* Phase indicator */}
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-orange/10 animate-pulse-glow">
          <Activity className="h-5 w-5 text-orange" />
        </div>
        <div>
          <p className="text-sm font-semibold text-foreground">
            {currentStatus}
          </p>
          <p className="text-xs text-warm-gray">
            {progress > 0 ? `${progress}% complete` : "Starting up..."}
          </p>
        </div>
      </div>

      {/* Progress bar */}
      <div className="relative h-3 overflow-hidden rounded-full bg-surface-3">
        <div
          className="h-full rounded-full gradient-brand transition-all duration-500 ease-out"
          style={{ width: `${Math.max(progress, 2)}%` }}
        />
        {progress > 0 && progress < 100 && (
          <div
            className="absolute inset-0 animate-shimmer rounded-full"
            style={{ width: `${progress}%` }}
          />
        )}
      </div>

      {/* Log console */}
      <div className="glass-card overflow-hidden">
        <div className="flex items-center gap-2 border-b border-surface-3 px-4 py-2.5">
          <div className="flex gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-error/60" />
            <span className="h-2.5 w-2.5 rounded-full bg-warning/60" />
            <span className="h-2.5 w-2.5 rounded-full bg-success/60" />
          </div>
          <span className="text-[11px] text-warm-gray font-mono">
            Generation Log
          </span>
        </div>
        <div
          ref={logRef}
          className="max-h-80 overflow-y-auto p-4 font-mono text-xs leading-relaxed"
        >
          {messages.length === 0 && (
            <p className="text-warm-gray">
              Waiting for generation to start...
            </p>
          )}
          {messages.map((msg, i) => (
            <LogEntry key={i} message={msg} index={i} />
          ))}
        </div>
      </div>
    </div>
  );
}

function LogEntry({
  message,
  index,
}: {
  message: ProgressMessage;
  index: number;
}) {
  const time = new Date(message.timestamp).toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  const iconMap = {
    status: <ChevronRight className="h-3 w-3 text-orange" />,
    info: <Info className="h-3 w-3 text-purple-light" />,
    progress: <ChevronRight className="h-3 w-3 text-warm-gray" />,
    warning: <AlertTriangle className="h-3 w-3 text-warning" />,
    done: <Activity className="h-3 w-3 text-success" />,
  };

  const textColor = {
    status: "text-foreground font-semibold",
    info: "text-purple-light",
    progress: "text-warm-gray-light",
    warning: "text-warning",
    done: "text-success",
  };

  return (
    <div
      className={cn(
        "flex items-start gap-2 py-0.5 animate-fade-in-up"
      )}
      style={{ animationDelay: `${index * 20}ms` }}
    >
      <span className="shrink-0 text-warm-gray select-none">{time}</span>
      <span className="shrink-0 mt-0.5">{iconMap[message.type]}</span>
      <span className={cn(textColor[message.type])}>{message.message}</span>
    </div>
  );
}
