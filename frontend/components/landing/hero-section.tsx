"use client";

import { useEffect, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";
import { AnimatedSphere } from "./animated-sphere";
import Link from "next/link";

/* ── Phase 1: "This is — not GPT, not Claude AI, not Gemini" ── */
const negations = ["not GPT.", "not Claude AI.", "not Gemini."];

/* ── Phase 2: "An AI that researches like a seasoned ___" ────── */
const roles = ["analyst", "strategist", "consultant", "researcher"];

/* ── Timing (ms) ─────────────────────────────────────────────── */
const NEG_DISPLAY = 1800;   // how long each negation stays
const NEG_PAUSE = 600;      // pause between negations
const PHASE_GAP = 1200;     // gap between phase 1 → phase 2
const ROLE_DISPLAY = 2500;  // how long each role stays
const PHASE2_HOLD = 1500;   // hold after last role before looping

export function HeroSection() {
  const [isVisible, setIsVisible] = useState(false);

  // Phase: "negation" | "role"
  const [phase, setPhase] = useState<"negation" | "role">("negation");
  const [negIndex, setNegIndex] = useState(0);
  const [roleIndex, setRoleIndex] = useState(0);
  // Controls fade-in/out for negation words
  const [negVisible, setNegVisible] = useState(true);

  useEffect(() => {
    setIsVisible(true);
  }, []);

  const runLoop = useCallback(() => {
    // Phase 1: cycle through negations
    let timeout: ReturnType<typeof setTimeout>;

    setPhase("negation");
    setNegIndex(0);
    setNegVisible(true);

    let currentNeg = 0;

    const startPhase2 = () => {
      setPhase("role");
      let currentRole = 0;
      setRoleIndex(0);

      const showNextRole = () => {
        if (currentRole < roles.length) {
          setRoleIndex(currentRole);
          timeout = setTimeout(() => {
            currentRole++;
            showNextRole();
          }, ROLE_DISPLAY);
        } else {
          timeout = setTimeout(() => {
            runLoop();
          }, PHASE2_HOLD);
        }
      };

      showNextRole();
    };

    const showNextNeg = () => {
      if (currentNeg < negations.length) {
        setNegIndex(currentNeg);
        setNegVisible(true);

        const isLast = currentNeg === negations.length - 1;

        if (isLast) {
          // Last negation — keep visible, then transition to phase 2
          timeout = setTimeout(() => {
            startPhase2();
          }, NEG_DISPLAY + PHASE_GAP);
        } else {
          // Not last — fade out, then show next
          timeout = setTimeout(() => {
            setNegVisible(false);
            timeout = setTimeout(() => {
              currentNeg++;
              showNextNeg();
            }, NEG_PAUSE);
          }, NEG_DISPLAY);
        }
      }
    };

    showNextNeg();

    return () => clearTimeout(timeout);
  }, []);

  useEffect(() => {
    const cleanup = runLoop();
    return cleanup;
  }, [runLoop]);

  return (
    <section className="relative min-h-screen flex flex-col justify-center overflow-hidden">
      <div className="absolute right-0 top-1/2 -translate-y-1/2 w-150 h-150 lg:w-200 lg:h-200 opacity-40 pointer-events-none">
        <AnimatedSphere />
      </div>

      <div className="absolute inset-0 overflow-hidden pointer-events-none opacity-30">
        {[...Array(8)].map((_, i) => (
          <div
            key={`h-${i}`}
            className="absolute h-px bg-foreground/10"
            style={{
              top: `${12.5 * (i + 1)}%`,
              left: 0,
              right: 0,
            }}
          />
        ))}
        {[...Array(12)].map((_, i) => (
          <div
            key={`v-${i}`}
            className="absolute w-px bg-foreground/10"
            style={{
              left: `${8.33 * (i + 1)}%`,
              top: 0,
              bottom: 0,
            }}
          />
        ))}
      </div>

      <div className="relative z-10 max-w-350 mx-auto w-full px-6 lg:px-12 py-32 lg:py-40">
        <div className="max-w-[55%]">
          <div
            className={`mb-8 transition-all duration-700 ${
              isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
            }`}
          >
            <span className="inline-flex items-center gap-3 text-base font-mono text-muted-foreground">
              <span className="w-8 h-px bg-foreground/30" />
              Multi-Layer Agentic AI Research Platform for Desk Research
            </span>
          </div>

          <div className="mb-8 min-h-[clamp(12rem,30vw,22rem)]">
            <h1
              className={`text-[clamp(2.75rem,6vw,5rem)] font-display leading-[1.05] tracking-tight transition-all duration-1000 ${
                isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
              }`}
            >
              {/* ── Phase 1: "This is — not GPT." ────────────── */}
              <div
                className="transition-all duration-700 ease-out"
                style={{
                  opacity: phase === "negation" ? 1 : 0,
                  transform: phase === "negation" ? "translateY(0)" : "translateY(-20px)",
                  height: phase === "negation" ? "auto" : 0,
                  overflow: "hidden",
                  position: phase === "negation" ? "relative" : "absolute",
                }}
              >
                <span className="block text-muted-foreground/50">This is —</span>
                <span className="block relative">
                  <span
                    key={`neg-${negIndex}`}
                    className="inline-flex"
                    style={{
                      opacity: negVisible ? 1 : 0,
                      transition: "opacity 0.4s ease",
                    }}
                  >
                    {negations[negIndex].split("").map((char, i) => (
                      <span
                        key={`neg-${negIndex}-${i}`}
                        className="inline-block animate-char-in"
                        style={{
                          animationDelay: `${i * 40}ms`,
                        }}
                      >
                        {char === " " ? "\u00A0" : char}
                      </span>
                    ))}
                  </span>
                  <span className="absolute -bottom-1 left-0 right-0 h-2 bg-foreground/10" />
                </span>
              </div>

              {/* ── Phase 2: "An AI that researches like a seasoned ___" ── */}
              <div
                className="transition-all duration-700 ease-out"
                style={{
                  opacity: phase === "role" ? 1 : 0,
                  transform: phase === "role" ? "translateY(0)" : "translateY(20px)",
                  position: phase === "role" ? "relative" : "absolute",
                }}
              >
                <span className="block">An AI that researches</span>
                <span className="block relative">
                  <span className="text-muted-foreground/50">like a seasoned </span>
                  <span
                    key={`role-${roleIndex}`}
                    className="inline-flex"
                  >
                    {roles[roleIndex].split("").map((char, i) => (
                      <span
                        key={`role-${roleIndex}-${i}`}
                        className="inline-block animate-char-in"
                        style={{
                          animationDelay: `${i * 50}ms`,
                        }}
                      >
                        {char}
                      </span>
                    ))}
                  </span>
                  <span className="absolute -bottom-1 left-0 right-0 h-2 bg-foreground/10" />
                </span>
              </div>
            </h1>
          </div>

          <div className="space-y-6">
            <p
              className={`text-lg lg:text-xl text-muted-foreground leading-relaxed max-w-lg transition-all duration-700 delay-200 ${
                isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
              }`}
            >
              Desk research in minutes, not days. Zero hallucinations,
              100% source-validated insights backed by 25 years of domain expertise.
            </p>

            <div
              className={`flex items-center gap-4 transition-all duration-700 delay-300 ${
                isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
              }`}
            >
              <Link href="/research">
                <Button
                  size="lg"
                  className="bg-foreground hover:bg-foreground/90 text-background px-6 h-12 text-sm rounded-full group"
                >
                  Start Research
                  <ArrowRight className="w-4 h-4 ml-2 transition-transform group-hover:translate-x-1" />
                </Button>
              </Link>
              <a href="#how-it-works">
                <Button
                  size="lg"
                  variant="outline"
                  className="h-12 px-6 text-sm rounded-full border-foreground/20 hover:bg-foreground/5"
                >
                  Explore Pipeline
                </Button>
              </a>
            </div>
          </div>
        </div>
      </div>


    </section>
  );
}
