"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Brain,
  Loader2,
  Layers,
  Search,
  FileText,
  Target,
} from "lucide-react";
import { ResearchLayout } from "@/components/ResearchLayout";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { useResearchStore } from "@/lib/store";
import { startResearch } from "@/lib/api";

const LAYER_CARDS = [
  {
    layer: 0,
    name: "Baseline",
    Icon: FileText,
    color: "#6B7280",
    description: "Model knowledge only — no tools, no web research",
  },
  {
    layer: 1,
    name: "Enhanced",
    Icon: Search,
    color: "#7C3AED",
    description: "ReAct agent with web search, scraping, and source assessment",
  },
  {
    layer: 2,
    name: "CMI Expert",
    Icon: Target,
    color: "#E11D48",
    description: "Full pipeline: Plan → Research → Verify → Write",
  },
];

export default function ResearchPage() {
  const router = useRouter();
  const {
    topic,
    setTopic,
    startResearch: storeStartResearch,
  } = useResearchStore();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      <div className="mx-auto max-w-3xl animate-fade-in-up">
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-orange/20">
              <Brain className="h-5 w-5 text-orange" />
            </div>
            <h2 className="text-2xl font-bold text-foreground">
              Research Agent
            </h2>
          </div>
          <p className="text-sm text-warm-gray">
            Enter a topic to run 3-layer parallel AI research. Each layer uses
            a different methodology — from baseline to full CMI expert pipeline —
            so you can compare quality at every level.
          </p>
        </div>

        {error && (
          <div className="mb-6 rounded-lg border border-error/30 bg-error/10 px-4 py-3 text-sm text-error">
            {error}
          </div>
        )}

        {/* Topic Input */}
        <div className="glass-card p-6 mb-6">
          <Label className="text-sm font-medium text-foreground">
            Research Topic
          </Label>
          <Textarea
            placeholder="e.g., Global EV Battery Market — competitive landscape, technology trends, and 2025-2030 outlook"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            className="mt-2 min-h-24 bg-surface-2 text-foreground placeholder:text-warm-gray/50"
          />
        </div>

        {/* Layer Preview */}
        <div className="glass-card p-6 mb-6">
          <Label className="text-sm font-medium text-foreground mb-4 block">
            3 Layers — Running in Parallel
          </Label>
          <div className="grid grid-cols-3 gap-3">
            {LAYER_CARDS.map((card) => {
              const Icon = card.Icon;
              return (
                <div
                  key={card.layer}
                  className="flex flex-col items-center gap-2 rounded-2xl border p-4 text-center"
                  style={{
                    borderColor: `${card.color}35`,
                    background: `${card.color}08`,
                  }}
                >
                  <div
                    className="flex h-10 w-10 items-center justify-center rounded-xl"
                    style={{ background: `${card.color}20` }}
                  >
                    <Icon className="h-5 w-5" style={{ color: card.color }} />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-foreground">
                      {card.name}
                    </p>
                    <p className="mt-0.5 text-[10px] leading-tight text-warm-gray">
                      {card.description}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Summary + Start */}
        <div className="glass-card p-6">
          <div className="rounded-lg bg-surface-2 px-4 py-3 text-xs text-warm-gray">
            <p>
              All <span className="text-foreground font-medium">3 layers</span>{" "}
              run simultaneously — Baseline (no research), Enhanced (web search),
              and CMI Expert (full pipeline with verification). Compare results
              side by side.
            </p>
          </div>

          <Button
            onClick={handleStart}
            disabled={!topic.trim() || loading}
            className="mt-4 w-full gradient-brand text-white hover:opacity-90 h-12 text-sm font-semibold"
          >
            {loading ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Layers className="mr-2 h-4 w-4" />
            )}
            Start Research
          </Button>
        </div>
      </div>
    </ResearchLayout>
  );
}
