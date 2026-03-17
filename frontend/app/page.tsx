"use client";

import Link from "next/link";
import Image from "next/image";
import {
  FileText,
  Brain,
  ArrowRight,
  Layers,
  Search,
  BarChart3,
  Shield,
  Activity,
} from "lucide-react";
import { useHealth } from "@/hooks/useHealth";

export default function HomePage() {
  const { health, loading } = useHealth();

  return (
    <div className="relative min-h-screen overflow-hidden bg-surface-0">
      {/* Decorative gradient orbs */}
      <div className="gradient-orb orb-purple" />
      <div className="gradient-orb orb-orange" />
      <div className="gradient-orb orb-coral" />

      {/* Header */}
      <header className="relative z-10 flex items-center justify-between px-8 py-6">
        <div className="flex items-center">
          <Image
            src="/cmi-logo.svg"
            alt="Coherent Market Insights"
            width={210}
            height={50}
            className="h-11 w-auto"
            priority
          />
        </div>

        {/* API Status */}
        <div className="flex items-center gap-4">
          <StatusDot
            label="OpenAI"
            ok={health?.openai ?? false}
            loading={loading}
          />
          <StatusDot
            label="SearXNG"
            ok={health?.searxng ?? false}
            loading={loading}
          />
        </div>
      </header>

      {/* Hero Section */}
      <main className="relative z-10 flex flex-col items-center px-8 pt-16 pb-12">
        <div className="animate-fade-in-up text-center max-w-3xl">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-purple/20 bg-purple/10 px-4 py-1.5 text-xs font-medium text-purple-light">
            <Activity className="h-3 w-3" />
            AI-Powered Market Intelligence
          </div>
          <h2 className="text-5xl font-extrabold leading-tight tracking-tight">
            <span className="text-gradient">Market Research</span>
            <br />
            <span className="text-foreground">& Report Generation</span>
          </h2>
          <p className="mx-auto mt-6 max-w-xl text-lg text-warm-gray leading-relaxed">
            Generate comprehensive market research reports or run multi-layer
            progressive analysis — powered by AI and real-time web research.
          </p>
        </div>

        {/* Feature Cards */}
        <div className="mt-16 grid w-full max-w-5xl grid-cols-1 gap-8 md:grid-cols-2">
          {/* Report Generator Card */}
          <Link href="/upload" className="group">
            <div className="glass-card-hover relative overflow-hidden p-8 h-full">
              {/* Gradient top accent */}
              <div className="absolute inset-x-0 top-0 h-1 gradient-purple-orange rounded-t-4xl" />

              <div className="flex items-start gap-4">
                <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl gradient-brand glow-sm">
                  <FileText className="h-7 w-7 text-white" />
                </div>
                <div>
                  <h3 className="text-xl font-bold text-foreground">
                    Report Generator
                  </h3>
                  <p className="mt-2 text-sm text-warm-gray leading-relaxed">
                    Upload TOC and Market Estimate data to generate comprehensive,
                    publication-ready DOCX reports with charts, tables, and citations.
                  </p>
                </div>
              </div>

              <div className="mt-6 grid grid-cols-2 gap-3">
                <FeatureItem icon={<Layers className="h-3.5 w-3.5" />} text="4-step wizard" />
                <FeatureItem icon={<Brain className="h-3.5 w-3.5" />} text="LLM content" />
                <FeatureItem icon={<BarChart3 className="h-3.5 w-3.5" />} text="Charts & tables" />
                <FeatureItem icon={<Search className="h-3.5 w-3.5" />} text="Web research" />
              </div>

              <div className="mt-8 flex items-center gap-2 text-sm font-semibold text-orange group-hover:text-orange-light transition-colors">
                Get Started
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
              </div>
            </div>
          </Link>

          {/* Research Agent Card */}
          <Link href="/research" className="group">
            <div className="glass-card-hover relative overflow-hidden p-8 h-full">
              {/* Gradient top accent */}
              <div className="absolute inset-x-0 top-0 h-1 gradient-orange-coral rounded-t-4xl" />

              <div className="flex items-start gap-4">
                <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl gradient-orange-coral glow-orange">
                  <Brain className="h-7 w-7 text-white" />
                </div>
                <div>
                  <h3 className="text-xl font-bold text-foreground">
                    Research Agent
                  </h3>
                  <p className="mt-2 text-sm text-warm-gray leading-relaxed">
                    Run multi-layer progressive analysis on any market topic — from
                    baseline through expert-level with quality scoring and cost tracking.
                  </p>
                </div>
              </div>

              <div className="mt-6 grid grid-cols-2 gap-3">
                <FeatureItem icon={<Layers className="h-3.5 w-3.5" />} text="4 research layers" />
                <FeatureItem icon={<BarChart3 className="h-3.5 w-3.5" />} text="Quality scoring" />
                <FeatureItem icon={<Shield className="h-3.5 w-3.5" />} text="Source verification" />
                <FeatureItem icon={<Activity className="h-3.5 w-3.5" />} text="Cost tracking" />
              </div>

              <div className="mt-8 flex items-center gap-2 text-sm font-semibold text-coral group-hover:text-orange-light transition-colors">
                Start Research
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
              </div>
            </div>
          </Link>
        </div>

        {/* Bottom tagline */}
        <p className="mt-16 text-center text-xs text-warm-gray/60">
          Powered by OpenAI GPT-4 &middot; SearXNG Web Search &middot; LangChain
        </p>
      </main>
    </div>
  );
}

function FeatureItem({
  icon,
  text,
}: {
  icon: React.ReactNode;
  text: string;
}) {
  return (
    <div className="flex items-center gap-2 rounded-lg bg-surface-2/50 px-3 py-2 text-xs text-warm-gray-light">
      <span className="text-purple-light">{icon}</span>
      {text}
    </div>
  );
}

function StatusDot({
  label,
  ok,
  loading,
}: {
  label: string;
  ok: boolean;
  loading: boolean;
}) {
  return (
    <div className="flex items-center gap-2 text-xs text-warm-gray">
      {loading ? (
        <span className="h-2 w-2 animate-pulse rounded-full bg-warm-gray" />
      ) : ok ? (
        <span className="h-2 w-2 rounded-full bg-success" />
      ) : (
        <span className="h-2 w-2 rounded-full bg-warning" />
      )}
      {label}
    </div>
  );
}
