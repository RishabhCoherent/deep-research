"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Check, Loader2, Settings, BarChart3, History } from "lucide-react";
import { cn } from "@/lib/utils";
import { useHealth } from "@/hooks/useHealth";

const STEPS = [
  { label: "Configure", icon: Settings },
  { label: "Running", icon: Loader2 },
  { label: "Results", icon: BarChart3 },
];

interface ResearchLayoutProps {
  children: React.ReactNode;
  currentStep?: number; // 1, 2, or 3 — undefined hides step indicator
}

export function ResearchLayout({ children, currentStep }: ResearchLayoutProps) {
  const pathname = usePathname();
  const { health } = useHealth();
  const isHistory = pathname.startsWith("/research/history");

  const allConnected = health?.openai && (health?.tavily || health?.searxng);

  return (
    <div className="min-h-screen bg-background">
      {/* ── Top Navigation Bar ──────────────────────────────── */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-background/80 backdrop-blur-xl border-b border-foreground/10">
        <nav className="mx-auto max-w-350 flex items-center justify-between px-6 lg:px-12 h-16">
          {/* Left: Logo */}
          <Link href="/" className="flex flex-col group">
            <span className="font-display text-xl tracking-tight">
              CoherentBot
            </span>
            <span className="text-[10px] font-mono text-muted-foreground tracking-wide">
              0 hallucination · 100% validation · 25 year experience
            </span>
          </Link>

          {/* Center: Step Indicator (only during research flow) */}
          {currentStep && (
            <div className="hidden md:flex items-center gap-2">
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
                          "h-px w-12 transition-colors duration-500",
                          isDone ? "bg-purple" : "bg-foreground/10"
                        )}
                      />
                    )}
                    <div className="flex items-center gap-2">
                      <div
                        className={cn(
                          "flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold transition-all",
                          isActive && "bg-foreground text-background",
                          isDone && "bg-purple text-white",
                          !isActive &&
                            !isDone &&
                            "bg-foreground/5 text-muted-foreground"
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
                          "text-xs font-mono uppercase tracking-wider transition-colors",
                          isActive && "text-foreground",
                          isDone && "text-purple",
                          !isActive && !isDone && "text-muted-foreground"
                        )}
                      >
                        {step.label}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Right: History link + Status dot */}
          <div className="flex items-center gap-6">
            <Link
              href="/research/history"
              className={cn(
                "flex items-center gap-1.5 text-sm transition-colors duration-300 relative group",
                isHistory
                  ? "text-foreground"
                  : "text-foreground/70 hover:text-foreground"
              )}
            >
              <History className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">History</span>
              <span className="absolute -bottom-1 left-0 h-px bg-foreground transition-all duration-300 group-hover:w-full w-0" />
            </Link>

            {/* System status dot */}
            <div className="relative group/status">
              <span
                className={cn(
                  "block h-2.5 w-2.5 rounded-full transition-colors",
                  allConnected
                    ? "bg-green-500"
                    : health?.openai
                    ? "bg-yellow-500"
                    : "bg-foreground/20"
                )}
              />
              {/* Tooltip */}
              <div className="absolute right-0 top-full mt-2 hidden group-hover/status:block z-50">
                <div className="glass-card rounded-lg p-3 text-xs font-mono space-y-1.5 min-w-35">
                  <StatusRow label="OpenAI" ok={health?.openai ?? false} />
                  <StatusRow label="Tavily" ok={health?.tavily ?? false} />
                  <StatusRow label="SearXNG" ok={health?.searxng ?? false} />
                </div>
              </div>
            </div>
          </div>
        </nav>
      </header>

      {/* ── Content Area with Background Effects ──────────── */}
      <div className="relative min-h-screen pt-24">
        {/* Gradient orbs */}
        <div
          className="pointer-events-none fixed -right-25 top-25 h-125 w-125 rounded-full opacity-[0.07]"
          style={{
            background: "radial-gradient(circle, #7C3AED 0%, transparent 70%)",
            filter: "blur(80px)",
          }}
        />
        <div
          className="pointer-events-none fixed -bottom-12.5 left-50 h-100 w-100 rounded-full opacity-[0.05]"
          style={{
            background: "radial-gradient(circle, #EA580C 0%, transparent 70%)",
            filter: "blur(80px)",
          }}
        />

        {/* Subtle grid lines */}
        <div className="pointer-events-none fixed inset-0 overflow-hidden opacity-30">
          {[...Array(4)].map((_, i) => (
            <div
              key={`h-${i}`}
              className="absolute h-px bg-foreground/5"
              style={{ top: `${25 * (i + 1)}%`, left: 0, right: 0 }}
            />
          ))}
          {[...Array(6)].map((_, i) => (
            <div
              key={`v-${i}`}
              className="absolute w-px bg-foreground/5"
              style={{ left: `${16.66 * (i + 1)}%`, top: 0, bottom: 0 }}
            />
          ))}
        </div>

        {/* Noise overlay + content */}
        <div className="noise-overlay relative">
          <div className="mx-auto max-w-350 px-6 lg:px-12 py-8 lg:py-12">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatusRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span
        className={cn(
          "flex items-center gap-1 text-[10px] font-medium",
          ok ? "text-green-600" : "text-muted-foreground"
        )}
      >
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            ok ? "bg-green-500" : "bg-foreground/20"
          )}
        />
        {ok ? "OK" : "\u2014"}
      </span>
    </div>
  );
}
