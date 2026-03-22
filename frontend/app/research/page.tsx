"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Loader2,
  ArrowRight,
} from "lucide-react";
import { ResearchLayout } from "@/components/ResearchLayout";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useResearchStore } from "@/lib/store";
import { startResearch } from "@/lib/api";
import { WorkflowVisualization } from "@/components/WorkflowVisualization";

const words = ["research", "analyze", "compare", "deliver"];

export default function ResearchPage() {
  const router = useRouter();
  const {
    topic,
    setTopic,
    startResearch: storeStartResearch,
  } = useResearchStore();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isVisible, setIsVisible] = useState(false);
  const [wordIndex, setWordIndex] = useState(0);

  useEffect(() => {
    setIsVisible(true);
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      setWordIndex((prev) => (prev + 1) % words.length);
    }, 2500);
    return () => clearInterval(interval);
  }, []);

  async function handleStart() {
    if (!topic.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await startResearch(topic.trim(), 2);
      storeStartResearch(res.job_id);
      router.push("/research/progress");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start research");
    } finally {
      setLoading(false);
    }
  }

  return (
    <ResearchLayout currentStep={1}>
      <div className="flex flex-col min-h-[calc(100vh-10rem)]">

        {/* ── Full-width tagline ─────────────────────────────── */}
        <div
          className={`w-full mb-8 lg:mb-10 transition-all duration-700 ${
            isVisible
              ? "opacity-100 translate-y-0"
              : "opacity-0 translate-y-4"
          }`}
        >
          <h1 className="text-3xl sm:text-4xl lg:text-5xl xl:text-[3.25rem] font-display tracking-tight text-foreground whitespace-nowrap">
            Trained on 25,000+ reports and 2,00,000+ white papers
          </h1>
        </div>

        {/* ── Side-by-side: Input (left) + Pipeline (right) ── */}
        <div className="flex flex-col lg:flex-row lg:items-start lg:gap-10 xl:gap-14 flex-1">

          {/* ── Left: Hero + Input ───────────────────────────── */}
          <div
            className={`w-full lg:w-85 xl:w-95 shrink-0 transition-all duration-700 delay-100 ${
              isVisible
                ? "opacity-100 translate-y-0"
                : "opacity-0 translate-y-4"
            }`}
          >
            <h2 className="text-3xl lg:text-4xl font-display leading-[1.1] tracking-tight mb-3">
              <span className="block">What should we</span>
              <span className="block relative mt-1">
                <span key={wordIndex} className="inline-flex">
                  {words[wordIndex].split("").map((char, i) => (
                    <span
                      key={`${wordIndex}-${i}`}
                      className="inline-block animate-char-in"
                      style={{ animationDelay: `${i * 50}ms` }}
                    >
                      {char}
                    </span>
                  ))}
                </span>
                <span className="absolute -bottom-1.5 left-0 w-20 h-0.5 bg-foreground/10 rounded-full" />
              </span>
            </h2>

            <p className="text-sm text-muted-foreground leading-relaxed mb-5">
              Enter a topic to run 3-layer sequential AI research. Each layer
              builds on the last — compare quality at every level.
            </p>

            {error && (
              <div className="mb-4 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                {error}
              </div>
            )}

            <div className="glass-card rounded-2xl p-5">
              <label className="block font-mono text-[11px] uppercase tracking-wider text-muted-foreground mb-2">
                Research Topic
              </label>
              <Textarea
                placeholder="e.g., Global EV Battery Market — competitive landscape, technology trends, and 2025-2030 outlook"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                className="min-h-24 rounded-xl border-foreground/10 bg-background/50 text-foreground placeholder:text-muted-foreground/40 focus:border-purple/30 focus:ring-purple/10 text-sm leading-relaxed resize-none"
              />
            </div>

            <div className="mt-4 flex items-center gap-4">
              <Button
                onClick={handleStart}
                disabled={!topic.trim() || loading}
                className="bg-foreground hover:bg-foreground/90 text-background rounded-full h-11 px-7 text-sm font-medium group disabled:opacity-40"
              >
                {loading ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <>
                    Start Research
                    <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
                  </>
                )}
              </Button>
              <span className="font-mono text-xs text-muted-foreground">
                3 layers &middot; 3-8 min
              </span>
            </div>
          </div>

          {/* ── Right: Pipeline Visualization ────────────────── */}
          <div
            className={`flex-1 min-w-0 mt-10 lg:mt-0 transition-all duration-700 delay-300 ${
              isVisible
                ? "opacity-100 translate-y-0"
                : "opacity-0 translate-y-8"
            }`}
          >
            <div className="mb-3 text-center">
              <span className="inline-flex items-center gap-3 text-xs font-mono text-muted-foreground mb-1">
                <span className="w-5 h-px bg-foreground/30" />
                Pipeline
                <span className="w-5 h-px bg-foreground/30" />
              </span>
              <h3 className="text-xl lg:text-2xl font-display tracking-tight">
                Three layers of analysis (CoherentBot)
              </h3>
            </div>
            <WorkflowVisualization />
          </div>
        </div>
      </div>
    </ResearchLayout>
  );
}
