"use client";

import { useEffect, useState, useRef } from "react";

const phases = [
  { city: "Phase 1 — UNDERSTAND", region: "Topic → Research Plan", latency: "12–16 questions" },
  { city: "Phase 2 — RESEARCH", region: "Plan → Knowledge Base", latency: "Concurrent batches" },
  { city: "Phase 3 — ANALYZE", region: "KB → Verified Insights", latency: "Cross-verification" },
  { city: "Phase 4 — WRITE", region: "Insights → Expert Report", latency: "Reasoning models" },
];

export function InfrastructureSection() {
  const [isVisible, setIsVisible] = useState(false);
  const [activePhase, setActivePhase] = useState(0);
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setIsVisible(true); },
      { threshold: 0.1 }
    );
    if (sectionRef.current) observer.observe(sectionRef.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      setActivePhase((prev) => (prev + 1) % phases.length);
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  return (
    <section ref={sectionRef} className="relative py-24 lg:py-32 overflow-hidden">
      <div className="max-w-350 mx-auto px-6 lg:px-12">
        <div className="grid lg:grid-cols-2 gap-16 lg:gap-24 items-center">
          <div
            className={`transition-all duration-700 ${
              isVisible ? "opacity-100 translate-x-0" : "opacity-0 -translate-x-8"
            }`}
          >
            <span className="inline-flex items-center gap-3 text-sm font-mono text-muted-foreground mb-6">
              <span className="w-8 h-px bg-foreground/30" />
              CMI Expert Pipeline
            </span>
            <h2 className="text-4xl lg:text-6xl font-display tracking-tight mb-8">
              Built for depth,
              <br />
              not speed.
            </h2>
            <p className="text-xl text-muted-foreground leading-relaxed mb-12">
              Every research run executes three parallel analysis strategies, each with 
              progressively deeper methodology. The CMI Expert layer alone runs four 
              sequential phases — understanding the domain, gathering evidence, 
              cross-verifying claims, and synthesizing expert-grade prose.
            </p>

            <div className="grid grid-cols-3 gap-8">
              <div>
                <div className="text-4xl lg:text-5xl font-display mb-2">4</div>
                <div className="text-sm text-muted-foreground">Pipeline phases</div>
              </div>
              <div>
                <div className="text-4xl lg:text-5xl font-display mb-2">7</div>
                <div className="text-sm text-muted-foreground">Quality dimensions</div>
              </div>
              <div>
                <div className="text-4xl lg:text-5xl font-display mb-2">3</div>
                <div className="text-sm text-muted-foreground">Parallel layers</div>
              </div>
            </div>
          </div>

          <div
            className={`transition-all duration-700 delay-200 ${
              isVisible ? "opacity-100 translate-x-0" : "opacity-0 translate-x-8"
            }`}
          >
            <div className="border border-foreground/10">
              <div className="px-6 py-4 border-b border-foreground/10 flex items-center justify-between">
                <span className="text-sm font-mono text-muted-foreground">CMI Expert Pipeline</span>
                <span className="flex items-center gap-2 text-xs font-mono text-green-600">
                  <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                  Pipeline ready
                </span>
              </div>
              <div>
                {phases.map((phase, index) => (
                  <div
                    key={phase.city}
                    className={`px-6 py-5 border-b border-foreground/5 last:border-b-0 flex items-center justify-between transition-all duration-300 ${
                      activePhase === index ? "bg-foreground/2" : ""
                    }`}
                  >
                    <div className="flex items-center gap-4">
                      <span 
                        className={`w-2 h-2 rounded-full transition-colors duration-300 ${
                          activePhase === index ? "bg-foreground" : "bg-foreground/20"
                        }`}
                      />
                      <div>
                        <div className="font-medium">{phase.city}</div>
                        <div className="text-sm text-muted-foreground">{phase.region}</div>
                      </div>
                    </div>
                    <span className="font-mono text-sm text-muted-foreground">{phase.latency}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
