"use client";

import { useEffect, useState, useRef } from "react";

const integrations = [
  { name: "OpenAI GPT-4o", category: "Language Model" },
  { name: "GPT-4.1", category: "Premium Model" },
  { name: "GPT-5.2", category: "Reasoning Model" },
  { name: "SearXNG", category: "Meta-Search Engine" },
  { name: "DuckDuckGo", category: "Search Fallback" },
  { name: "Google Scholar", category: "Academic Search" },
];

const sources = [
  { name: "Reuters", category: "T1 Source" },
  { name: "Bloomberg", category: "T1 Source" },
  { name: "SEC Filings", category: "T1 Source" },
  { name: "Nature", category: "T1 Source" },
  { name: "WHO", category: "T1 Source" },
  { name: "IDC", category: "T1 Source" },
];

export function IntegrationsSection() {
  const [isVisible, setIsVisible] = useState(false);
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setIsVisible(true); },
      { threshold: 0.1 }
    );
    if (sectionRef.current) observer.observe(sectionRef.current);
    return () => observer.disconnect();
  }, []);

  return (
    <section id="integrations" ref={sectionRef} className="relative py-24 lg:py-32 overflow-hidden">
      <div className="max-w-350 mx-auto px-6 lg:px-12">
        <div
          className={`text-center max-w-3xl mx-auto mb-16 lg:mb-24 transition-all duration-700 ${
            isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
          }`}
        >
          <span className="inline-flex items-center gap-3 text-sm font-mono text-muted-foreground mb-6">
            <span className="w-8 h-px bg-foreground/30" />
            Data Sources & Models
            <span className="w-8 h-px bg-foreground/30" />
          </span>
          <h2 className="text-4xl lg:text-6xl font-display tracking-tight mb-6">
            Powered by best-in-class
            <br />
            research-grade tools.
          </h2>
          <p className="text-xl text-muted-foreground">
            State-of-the-art language models paired with multi-source web search and Tier 1 verified data sources.
          </p>
        </div>
      </div>
      
      <div className="w-full mb-6">
        <div className="flex gap-6 marquee">
          {[...Array(2)].map((_, setIndex) => (
            <div key={setIndex} className="flex gap-6 shrink-0">
              {integrations.map((integration) => (
                <div
                  key={`${integration.name}-${setIndex}`}
                  className="shrink-0 px-8 py-6 border border-foreground/10 hover:border-foreground/30 hover:bg-foreground/2 transition-all duration-300 group"
                >
                  <div className="text-lg font-medium group-hover:translate-x-1 transition-transform">
                    {integration.name}
                  </div>
                  <div className="text-sm text-muted-foreground">{integration.category}</div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
      
      <div className="w-full">
        <div className="flex gap-6 marquee-reverse">
          {[...Array(2)].map((_, setIndex) => (
            <div key={setIndex} className="flex gap-6 shrink-0">
              {sources.map((source) => (
                <div
                  key={`${source.name}-reverse-${setIndex}`}
                  className="shrink-0 px-8 py-6 border border-foreground/10 hover:border-foreground/30 hover:bg-foreground/2 transition-all duration-300 group"
                >
                  <div className="text-lg font-medium group-hover:translate-x-1 transition-transform">
                    {source.name}
                  </div>
                  <div className="text-sm text-muted-foreground">{source.category}</div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
