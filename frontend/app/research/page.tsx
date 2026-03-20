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
      {/* ── Hero Section ──────────────────────────────────── */}
      <div className="mx-auto max-w-5xl text-center">
        <div
          className={`mb-8 transition-all duration-700 ${
            isVisible
              ? "opacity-100 translate-y-0"
              : "opacity-0 translate-y-4"
          }`}
        >
          <span className="block text-2xl sm:text-3xl lg:text-5xl font-display tracking-tight text-foreground">
            Trained on 25,000+ reports and 2,00,000+ white papers
          </span>
        </div>

        <h1
          className={`text-4xl lg:text-6xl font-display leading-[1.05] tracking-tight transition-all duration-1000 ${
            isVisible
              ? "opacity-100 translate-y-0"
              : "opacity-0 translate-y-8"
          }`}
        >
          <span className="block">What should we</span>
          <span className="block relative mt-2">
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
            <span className="absolute -bottom-2 left-1/2 -translate-x-1/2 w-32 h-1 bg-foreground/10 rounded-full" />
          </span>
        </h1>

        <p
          className={`mt-8 text-lg text-muted-foreground leading-relaxed max-w-lg mx-auto transition-all duration-700 delay-200 ${
            isVisible
              ? "opacity-100 translate-y-0"
              : "opacity-0 translate-y-4"
          }`}
        >
          Enter a topic to run 3-layer sequential AI research. Each layer
          builds on the last — compare quality at every level.
        </p>
      </div>

      {/* ── Topic Input ──────────────────────────────────── */}
      <div
        className={`mx-auto max-w-2xl mt-12 transition-all duration-700 delay-300 ${
          isVisible
            ? "opacity-100 translate-y-0"
            : "opacity-0 translate-y-8"
        }`}
      >
        {error && (
          <div className="mb-6 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        <div className="glass-card rounded-2xl p-8">
          <label className="block font-mono text-xs uppercase tracking-wider text-muted-foreground mb-4">
            Research Topic
          </label>
          <Textarea
            placeholder="e.g., Global EV Battery Market — competitive landscape, technology trends, and 2025-2030 outlook"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            className="min-h-40 rounded-xl border-foreground/10 bg-background/50 text-foreground placeholder:text-muted-foreground/40 focus:border-purple/30 focus:ring-purple/10 text-base leading-relaxed resize-none"
          />
        </div>

        <div className="mt-6 text-center">
          <p className="font-mono text-xs text-muted-foreground mb-4">
            3 layers run sequentially &middot; 3-8 minutes
          </p>
          <Button
            onClick={handleStart}
            disabled={!topic.trim() || loading}
            className="bg-foreground hover:bg-foreground/90 text-background rounded-full h-14 px-10 text-base font-medium group disabled:opacity-40"
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
        </div>
      </div>

      {/* ── Pipeline Workflow (below fold) ─────────────────── */}
      <div className="mt-24 lg:mt-32">
        <div className="text-center mb-12">
          <span className="inline-flex items-center gap-3 text-sm font-mono text-muted-foreground mb-4">
            <span className="w-8 h-px bg-foreground/30" />
            Pipeline
            <span className="w-8 h-px bg-foreground/30" />
          </span>
          <h2 className="text-3xl lg:text-4xl font-display tracking-tight">
            Three layers of analysis
          </h2>
        </div>
        <WorkflowVisualization />
      </div>
    </ResearchLayout>
  );
}
