"use client";

import { useMemo, useRef } from "react";
import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import {
  Lightbulb,
  AlertTriangle,
  GitBranch,
  ArrowLeftRight,
  TrendingUp,
  ArrowUp,
  ArrowRight,
  ArrowDown,
} from "lucide-react";

/* ── Section accent colours (cycle through these) ──────────────── */
const SECTION_ACCENTS = [
  {
    border: "border-l-purple",
    bg: "bg-purple/5",
    badge: "bg-purple/15 text-purple",
    dot: "bg-purple",
  },
  {
    border: "border-l-purple-light",
    bg: "bg-purple-light/5",
    badge: "bg-purple-light/15 text-purple-light",
    dot: "bg-purple-light",
  },
  {
    border: "border-l-foreground",
    bg: "bg-foreground/5",
    badge: "bg-foreground/15 text-muted-foreground",
    dot: "bg-foreground",
  },
  {
    border: "border-l-success",
    bg: "bg-success/5",
    badge: "bg-success/15 text-success",
    dot: "bg-success",
  },
  {
    border: "border-l-warning",
    bg: "bg-warning/5",
    badge: "bg-warning/15 text-warning",
    dot: "bg-warning",
  },
  {
    border: "border-l-purple-light",
    bg: "bg-purple-light/5",
    badge: "bg-purple-light/15 text-purple-light",
    dot: "bg-purple-light",
  },
];

/* ── Expert callout types ───────────────────────────────────────── */
const CALLOUT_CONFIG = {
  INSIGHT: {
    label: "Key Insight",
    Icon: Lightbulb,
    border: "border-l-purple",
    bg: "bg-purple/8",
    header: "text-purple",
  },
  COUNTEREVIDENCE: {
    label: "Counterevidence",
    Icon: AlertTriangle,
    border: "border-l-purple",
    bg: "bg-purple/8",
    header: "text-purple",
  },
  "SECOND-ORDER": {
    label: "Second-Order Effect",
    Icon: GitBranch,
    border: "border-l-foreground",
    bg: "bg-foreground/8",
    header: "text-foreground",
  },
  "CROSS-INDUSTRY": {
    label: "Cross-Industry Parallel",
    Icon: ArrowLeftRight,
    border: "border-l-success",
    bg: "bg-success/8",
    header: "text-success",
  },
  COMMERCIAL: {
    label: "Commercial Implication",
    Icon: TrendingUp,
    border: "border-l-warning",
    bg: "bg-warning/8",
    header: "text-warning",
  },
} as const;

type CalloutType = keyof typeof CALLOUT_CONFIG;

/* ── Impact level config ──────────────────────────────────────── */
export interface SectionImpact {
  section: string;
  impact: "high" | "moderate" | "low";
  reason: string;
}

const IMPACT_CONFIG = {
  high: {
    label: "High Impact",
    Icon: ArrowUp,
    bg: "bg-red-500/12",
    text: "text-red-400",
    border: "border-red-500/30",
  },
  moderate: {
    label: "Moderate Impact",
    Icon: ArrowRight,
    bg: "bg-amber-500/12",
    text: "text-amber-400",
    border: "border-amber-500/30",
  },
  low: {
    label: "Low Impact",
    Icon: ArrowDown,
    bg: "bg-emerald-500/12",
    text: "text-emerald-400",
    border: "border-emerald-500/30",
  },
} as const;

/* ── Parse markdown into sections split on ## headings ─────────── */
interface Section {
  id: string;
  title: string;
  body: string; // markdown body (may contain ### subsections)
}

function parseSections(markdown: string): Section[] {
  const lines = markdown.split("\n");

  // Detect which heading level to split on.
  // A level is only used for splitting if it appears 2+ times
  // (1 occurrence likely means it's just a document title, not sections).
  const countH2 = lines.filter((l) => /^##\s+/.test(l) && !/^###/.test(l)).length;
  const countH3 = lines.filter((l) => /^###\s+/.test(l) && !/^####/.test(l)).length;
  const countH1 = lines.filter((l) => /^#\s+/.test(l) && !/^##/.test(l)).length;

  const splitPattern =
    countH2 >= 2
      ? /^##(?!#)\s+(.+)$/
      : countH3 >= 2
      ? /^###(?!#)\s+(.+)$/
      : countH1 >= 2
      ? /^#(?!#)\s+(.+)$/
      : countH2 === 1
      ? /^##(?!#)\s+(.+)$/
      : countH1 === 1
      ? /^#(?!#)\s+(.+)$/
      : null;

  const sections: Section[] = [];
  let current: Section | null = null;
  const bodyLines: string[] = [];

  function flush() {
    if (current) {
      current.body = bodyLines.join("\n").trim();
      if (current.title || current.body) sections.push(current);
      bodyLines.length = 0;
    }
  }

  for (const line of lines) {
    const headingMatch = splitPattern ? line.match(splitPattern) : null;
    if (headingMatch) {
      flush();
      const title = headingMatch[1].trim();
      const id = title
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/(^-|-$)/g, "");
      current = { id, title, body: "" };
    } else {
      if (!current) {
        current = { id: "intro", title: "", body: "" };
      }
      bodyLines.push(line);
    }
  }
  flush();
  return sections;
}

/* ── Prose styles for markdown inside each section ─────────────── */
const PROSE_CLASSES = cn(
  "prose prose-sm max-w-none",
  "prose-headings:text-foreground prose-headings:font-semibold",
  // Sub-headings: visible, styled, with clear spacing
  "prose-h3:text-base prose-h3:font-semibold prose-h3:mt-6 prose-h3:mb-2 prose-h3:text-foreground prose-h3:border-b prose-h3:border-foreground/10 prose-h3:pb-1",
  "prose-h4:text-sm prose-h4:font-medium prose-h4:mt-4 prose-h4:mb-1.5 prose-h4:text-foreground/80",
  "prose-p:text-muted-foreground prose-p:leading-relaxed prose-p:my-2 prose-p:text-[13px]",
  "prose-strong:text-foreground prose-strong:font-semibold",
  "prose-ul:text-muted-foreground prose-ul:my-2 prose-ul:text-[13px] prose-ul:pl-5",
  "prose-ol:text-muted-foreground prose-ol:my-2 prose-ol:text-[13px] prose-ol:pl-5",
  "prose-li:my-1 prose-li:leading-relaxed",
  "prose-a:text-purple prose-a:no-underline hover:prose-a:underline",
  "prose-hr:border-foreground/10 prose-hr:my-3",
  // Tables: proper sizing with full grid borders
  "prose-table:text-sm prose-table:my-4 prose-table:w-full",
  "prose-th:text-foreground prose-th:bg-foreground/5 prose-th:px-4 prose-th:py-2.5 prose-th:text-left prose-th:font-semibold prose-th:border prose-th:border-foreground/15",
  "prose-td:px-4 prose-td:py-2 prose-td:text-muted-foreground prose-td:border prose-td:border-foreground/10",
  // Suppress default blockquote prose styles — we handle them custom
  "prose-blockquote:not-italic prose-blockquote:border-0 prose-blockquote:p-0 prose-blockquote:m-0",
);

/* ── Callout card renderer ──────────────────────────────────────── */
function CalloutCard({
  type,
  children,
}: {
  type: CalloutType;
  children: React.ReactNode;
}) {
  const cfg = CALLOUT_CONFIG[type];
  const Icon = cfg.Icon;
  return (
    <div
      className={cn(
        "rounded-xl border-l-[3px] px-4 py-3 my-3 not-prose",
        cfg.border,
        cfg.bg,
      )}
    >
      <div
        className={cn(
          "flex items-center gap-1.5 mb-1.5 text-[10px] font-bold uppercase tracking-widest",
          cfg.header,
        )}
      >
        <Icon size={11} />
        {cfg.label}
      </div>
      <p className="text-[13px] text-foreground/85 leading-relaxed m-0">
        {children}
      </p>
    </div>
  );
}

/* ── Custom ReactMarkdown components ────────────────────────────── */
function makeMarkdownComponents() {
  return {
    h3: ({ children, ...props }: React.HTMLAttributes<HTMLHeadingElement>) => (
      <h3
        className="text-base font-semibold text-foreground mt-6 mb-2 pb-1.5 border-b border-foreground/10"
        {...props}
      >
        {children}
      </h3>
    ),

    h4: ({ children, ...props }: React.HTMLAttributes<HTMLHeadingElement>) => (
      <h4
        className="text-sm font-medium text-foreground/80 mt-4 mb-1.5"
        {...props}
      >
        {children}
      </h4>
    ),

    table: ({
      children,
      ...props
    }: React.HTMLAttributes<HTMLTableElement>) => (
      <div className="overflow-x-auto rounded-lg border border-foreground/15 my-4">
        <table className="w-full text-sm border-collapse" {...props}>{children}</table>
      </div>
    ),

    thead: ({ children, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) => (
      <thead className="bg-foreground/5" {...props}>{children}</thead>
    ),

    th: ({ children, ...props }: React.HTMLAttributes<HTMLTableCellElement>) => (
      <th
        className="px-4 py-2.5 text-left text-foreground font-semibold border border-foreground/15 whitespace-nowrap"
        {...props}
      >
        {children}
      </th>
    ),

    td: ({ children, ...props }: React.HTMLAttributes<HTMLTableCellElement>) => (
      <td
        className="px-4 py-2 text-muted-foreground border border-foreground/10"
        {...props}
      >
        {children}
      </td>
    ),

    ul: ({ children, ...props }: React.HTMLAttributes<HTMLUListElement>) => (
      <ul className="list-disc pl-6 my-2 space-y-1 text-[13px] text-muted-foreground" {...props}>
        {children}
      </ul>
    ),

    ol: ({ children, ...props }: React.HTMLAttributes<HTMLOListElement>) => (
      <ol className="list-decimal pl-6 my-2 space-y-1 text-[13px] text-muted-foreground" {...props}>
        {children}
      </ol>
    ),

    li: ({ children, ...props }: React.HTMLAttributes<HTMLLIElement>) => (
      <li className="leading-relaxed" {...props}>
        {children}
      </li>
    ),

    blockquote: ({ children }: { children?: React.ReactNode }) => {
      // Try to detect callout type from first child paragraph
      const kids = React.Children.toArray(children);
      const firstP = kids[0] as React.ReactElement | undefined;

      if (firstP && React.isValidElement(firstP) && firstP.type === "p") {
        const pProps = firstP.props as { children?: React.ReactNode };
        const pKids = React.Children.toArray(pProps.children);
        const firstStrong = pKids[0] as React.ReactElement | undefined;

        if (
          firstStrong &&
          React.isValidElement(firstStrong) &&
          firstStrong.type === "strong"
        ) {
          const strongProps = firstStrong.props as { children?: React.ReactNode };
          const tag = String(strongProps.children)
            .replace(/[\[\]]/g, "")
            .trim() as CalloutType;

          if (tag in CALLOUT_CONFIG) {
            // Remaining content after the [TAG] token
            const rest = pKids.slice(1);
            // Strip leading whitespace/dash from rest
            const restClean = rest.map((node, i) =>
              i === 0 && typeof node === "string"
                ? node.replace(/^\s*[-–—]\s*/, "")
                : node,
            );
            return <CalloutCard type={tag}>{restClean}</CalloutCard>;
          }
        }
      }

      // Default plain blockquote
      return (
        <blockquote className="border-l-2 border-foreground/10 pl-4 text-muted-foreground italic my-2">
          {children}
        </blockquote>
      );
    },
  };
}

/* ── Impact badge component ────────────────────────────────────── */
function ImpactBadge({ impact }: { impact: SectionImpact }) {
  const cfg = IMPACT_CONFIG[impact.impact];
  const Icon = cfg.Icon;
  return (
    <div className="group relative">
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
          cfg.bg,
          cfg.text,
          cfg.border,
        )}
      >
        <Icon size={10} strokeWidth={2.5} />
        {impact.impact}
      </span>
      {impact.reason && (
        <div className="pointer-events-none absolute left-0 top-full z-50 mt-1.5 w-64 rounded-lg border border-foreground/10 bg-background px-3 py-2 text-[11px] text-muted-foreground opacity-0 shadow-xl transition-opacity group-hover:pointer-events-auto group-hover:opacity-100">
          {impact.reason}
        </div>
      )}
    </div>
  );
}

/* ── Main component ────────────────────────────────────────────── */
interface MarkdownReportProps {
  content: string;
  className?: string;
  sectionImpacts?: SectionImpact[];
}

export function MarkdownReport({ content, className, sectionImpacts }: MarkdownReportProps) {
  const sectionRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const sections = useMemo(() => parseSections(content), [content]);
  const markdownComponents = useMemo(() => makeMarkdownComponents(), []);

  // Build a lookup: normalised section title → impact data
  const impactMap = useMemo(() => {
    const map = new Map<string, SectionImpact>();
    if (!sectionImpacts?.length) return map;
    for (const si of sectionImpacts) {
      map.set(si.section.toLowerCase().trim(), si);
    }
    return map;
  }, [sectionImpacts]);

  function getImpact(title: string): SectionImpact | undefined {
    const norm = title.toLowerCase().trim();
    // Exact match first
    const exact = impactMap.get(norm);
    if (exact) return exact;
    // Fuzzy: check if section title starts with impact key or vice versa
    // (handles "Competitive Rivalry — Research market share..." vs "Competitive Rivalry")
    for (const [key, val] of impactMap) {
      if (norm.startsWith(key) || key.startsWith(norm)) return val;
    }
    return undefined;
  }

  // Sections that have a title (skip intro for TOC)
  const tocSections = sections.filter((s) => s.title);

  function scrollToSection(id: string) {
    sectionRefs.current[id]?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }

  return (
    <div className={cn("space-y-4", className)}>
      {/* ── Table of Contents ─────────────────────────────────── */}
      {tocSections.length > 1 && (
        <div className="glass-card px-5 py-3.5">
          <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Sections
          </p>
          <div className="flex flex-wrap gap-1.5">
            {tocSections.map((section, i) => {
              const accent = SECTION_ACCENTS[i % SECTION_ACCENTS.length];
              return (
                <button
                  key={section.id}
                  onClick={() => scrollToSection(section.id)}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all",
                    "hover:scale-[1.02] active:scale-[0.98]",
                    accent.badge,
                  )}
                >
                  <span
                    className={cn("h-1.5 w-1.5 rounded-full", accent.dot)}
                  />
                  {section.title}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Section Cards ─────────────────────────────────────── */}
      {sections.map((section) => {
        // Intro (no title) gets neutral styling
        if (!section.title) {
          return (
            <div key="intro" className="glass-card px-5 py-4">
              <div className={PROSE_CLASSES}>
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                  {section.body}
                </ReactMarkdown>
              </div>
            </div>
          );
        }

        const accentIdx =
          tocSections.findIndex((s) => s.id === section.id) %
          SECTION_ACCENTS.length;
        const accent = SECTION_ACCENTS[accentIdx];

        return (
          <div
            key={section.id}
            ref={(el) => {
              sectionRefs.current[section.id] = el;
            }}
            className={cn(
              "section-card border-l-[3px] rounded-2xl",
              accent.border,
              accent.bg,
            )}
          >
            {/* Section header */}
            <div className="flex items-center gap-2.5 px-5 pt-4 pb-2">
              <span
                className={cn(
                  "inline-flex h-6 min-w-6 items-center justify-center rounded-md text-[10px] font-bold",
                  accent.badge,
                )}
              >
                {tocSections.findIndex((s) => s.id === section.id) + 1}
              </span>
              <h2 className="text-sm font-bold text-foreground">
                {section.title}
              </h2>
              {(() => {
                const impact = getImpact(section.title);
                return impact ? <ImpactBadge impact={impact} /> : null;
              })()}
            </div>

            {/* Section content */}
            <div className="px-5 pb-4">
              <div className={PROSE_CLASSES}>
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                  {section.body}
                </ReactMarkdown>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
