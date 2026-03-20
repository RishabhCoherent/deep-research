"use client";

import { useEffect, useState, useRef } from "react";
import { Shield, Lock, Eye, FileCheck } from "lucide-react";

const securityFeatures = [
  {
    icon: Shield,
    title: "Tier 1 Gold Sources",
    description: "IDC, Reuters, Bloomberg, SEC, WHO, Nature, and other premier sources verified for accuracy and authority.",
  },
  {
    icon: Lock,
    title: "Competitor Auto-Filtering",
    description: "60+ competing research firms — Grand View, MarketsandMarkets, Mordor Intelligence — automatically detected and excluded from citations.",
  },
  {
    icon: Eye,
    title: "Cross-Verification",
    description: "Facts from Tier 3 sources are cross-checked against Tier 1 and Tier 2 sources. Conflicts resolved by preferring higher-tier evidence.",
  },
  {
    icon: FileCheck,
    title: "Qualitative-Only Policy",
    description: "No fabricated market sizes, percentages, or CAGR figures. All quantitative data comes from verified primary sources or is omitted entirely.",
  },
];

const tiers = ["Tier 1 Gold", "Tier 2 Known", "Tier 3 Unknown", "Auto-Filtered", "Cross-Verified"];

export function SecuritySection() {
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
    <section id="security" ref={sectionRef} className="relative py-24 lg:py-32 bg-foreground/2 overflow-hidden">
      <div className="max-w-350 mx-auto px-6 lg:px-12">
        <div className="grid lg:grid-cols-2 gap-16 lg:gap-24">
          <div
            className={`transition-all duration-700 ${
              isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
            }`}
          >
            <span className="inline-flex items-center gap-3 text-sm font-mono text-muted-foreground mb-6">
              <span className="w-8 h-px bg-foreground/30" />
              Source Integrity
            </span>
            <h2 className="text-4xl lg:text-6xl font-display tracking-tight mb-8">
              Source integrity is
              <br />
              non-negotiable.
            </h2>
            <p className="text-xl text-muted-foreground leading-relaxed mb-12">
              Market research is only as good as its sources. CoherentBot classifies 
              every source into credibility tiers, automatically filters competing research 
              firms, and cross-verifies claims across multiple independent sources.
            </p>

            <div className="flex flex-wrap gap-3">
              {tiers.map((tier, index) => (
                <span
                  key={tier}
                  className={`px-4 py-2 border border-foreground/10 text-sm font-mono transition-all duration-500 ${
                    isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
                  }`}
                  style={{ transitionDelay: `${index * 50 + 200}ms` }}
                >
                  {tier}
                </span>
              ))}
            </div>
          </div>

          <div className="grid gap-6">
            {securityFeatures.map((feature, index) => (
              <div
                key={feature.title}
                className={`p-6 border border-foreground/10 hover:border-foreground/20 transition-all duration-500 group ${
                  isVisible ? "opacity-100 translate-x-0" : "opacity-0 translate-x-8"
                }`}
                style={{ transitionDelay: `${index * 100}ms` }}
              >
                <div className="flex items-start gap-4">
                  <div className="shrink-0 w-10 h-10 flex items-center justify-center border border-foreground/10 group-hover:bg-foreground group-hover:text-background transition-colors duration-300">
                    <feature.icon className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-lg font-medium mb-1 group-hover:translate-x-1 transition-transform duration-300">
                      {feature.title}
                    </h3>
                    <p className="text-muted-foreground">{feature.description}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
