"use client";

/**
 * Backend2OutlineBrief — the core brief renderer for backend2.
 *
 * Reads `consolidated.outline` (the structured ReportOutline from a6's
 * two-pass compose) and renders each section with:
 *   - Bold thesis line
 *   - Prose body (markdown)
 *   - Framework table (when present) — actual styled table
 *   - Causal-chain rows — cause → effect → implication 3-column grid
 *   - Case studies — nested cards
 *
 * Then a separate Contrarian View section when contrarian_claims is non-empty
 * (uses the coral accent to distinguish from consensus prose).
 *
 * If no outline is present, falls back to rendering the full narrative
 * markdown so older runs still render.
 *
 * Reuses: glass-card, evidence-highlight-* tokens, Instrument Serif heading,
 * existing MarkdownReport component for prose blocks.
 */

import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type {
  Backend2Consolidated,
  Backend2OutlineSection,
} from "@/lib/types-backend2";

interface Props {
  consolidated: Backend2Consolidated | null;
}

function _Markdown({ text }: { text: string }) {
  if (!text) return null;
  return (
    <div className="prose prose-slate prose-sm max-w-none prose-headings:font-display prose-a:text-[var(--color-purple)] prose-strong:text-foreground">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}

function _Section({ section, idx }: { section: Backend2OutlineSection; idx: number }) {
  const heading = section.heading.replace(/^#+\s*/, "");

  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-100px" }}
      transition={{ duration: 0.4, delay: idx * 0.05 }}
      className="mb-8 last:mb-0"
    >
      <h2 className="font-display text-2xl text-foreground mb-2">
        {heading}
      </h2>

      {section.thesis && (
        <p className="font-medium text-foreground leading-snug mb-4 pl-3 border-l-2 border-[var(--color-purple)]">
          {section.thesis}
        </p>
      )}

      {section.prose && (
        <div className="mb-4">
          <_Markdown text={section.prose} />
        </div>
      )}

      {section.framework_table && (
        <FrameworkTable table={section.framework_table} />
      )}

      {section.causal_chain_rows.length > 0 && (
        <CausalChain rows={section.causal_chain_rows} />
      )}

      {section.case_studies.length > 0 && (
        <div className="mt-4 space-y-3">
          {section.case_studies.map((cs, i) => (
            <CaseStudyCard key={i} title={cs.title} body={cs.body} />
          ))}
        </div>
      )}

    </motion.section>
  );
}

function FrameworkTable({
  table,
}: {
  table: NonNullable<Backend2OutlineSection["framework_table"]>;
}) {
  if (!table.headers.length || !table.rows.length) return null;
  return (
    <div className="my-4 glass-card p-3 overflow-x-auto">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-2">
        Framework · {table.title}
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-foreground/8">
            <th className="text-left font-medium text-muted-foreground text-xs px-2 py-1.5"></th>
            {table.headers.map((h, i) => (
              <th key={i} className="text-left font-medium text-foreground/70 text-xs px-2 py-1.5">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, i) => (
            <tr key={i} className="border-b border-foreground/6 last:border-0">
              <td className="font-medium text-foreground text-sm px-2 py-2">
                {row.label}
              </td>
              {row.cells.map((cell, j) => (
                <td key={j} className="text-foreground/75 text-sm px-2 py-2">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CausalChain({
  rows,
}: {
  rows: Backend2OutlineSection["causal_chain_rows"];
}) {
  return (
    <div className="my-4">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-2">
        Causal chain
      </div>
      <div className="space-y-2">
        {rows.map((r, i) => (
          <div
            key={i}
            className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr_auto_1fr] gap-2 md:gap-3 items-center text-sm p-3 glass-card"
          >
            <div className="text-foreground/75">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-0.5">Cause</div>
              {r.cause}
            </div>
            <div className="hidden md:block text-[var(--color-purple)] text-lg">→</div>
            <div className="text-foreground/75">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-0.5">Effect</div>
              {r.effect}
            </div>
            <div className="hidden md:block text-[var(--color-purple)] text-lg">→</div>
            <div className="text-foreground font-medium">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-0.5">Implication</div>
              {r.implication}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CaseStudyCard({ title, body }: { title: string; body: string }) {
  const cleanTitle = title.replace(/^Case Study:\s*/i, "");
  return (
    <div className="glass-card p-4 border-l-4 border-l-[var(--color-orange)]">
      <div className="text-[10px] uppercase tracking-wider text-[var(--color-orange)] font-medium mb-1">
        Case study
      </div>
      <h4 className="font-display text-lg text-foreground mb-2">
        {cleanTitle}
      </h4>
      <_Markdown text={body} />
    </div>
  );
}

function ContrarianView({ claims }: { claims: string[] }) {
  if (!claims.length) return null;
  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.4 }}
      className="mt-8 glass-card p-5 border-l-4 border-l-[var(--color-coral)]"
    >
      <div className="text-[10px] uppercase tracking-wider text-[var(--color-coral)] font-semibold mb-2">
        Contrarian View
      </div>
      <h2 className="font-display text-2xl text-foreground mb-3">
        Where the consensus might be wrong
      </h2>
      <ul className="space-y-2">
        {claims.map((c, i) => (
          <li key={i} className="text-foreground/85 leading-relaxed">
            <span className="text-[var(--color-coral)] font-semibold mr-2">{i + 1}.</span>
            {c}
          </li>
        ))}
      </ul>
    </motion.section>
  );
}

export default function Backend2OutlineBrief({ consolidated }: Props) {
  if (!consolidated || !consolidated.narrative) {
    return (
      <div className="glass-card p-6 mb-6">
        <p className="text-sm text-slate-500 italic">
          No brief was composed for this run.
        </p>
      </div>
    );
  }

  // If outline is present, render structurally. Otherwise fall back to the
  // raw narrative markdown.
  const outline = consolidated.outline;

  return (
    <div className="glass-card p-6 mb-6">
      <span className="inline-flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-muted-foreground mb-4">
        <span className="w-5 h-px bg-foreground/30" />
        Research Brief · a6 two-pass compose
      </span>

      {outline && outline.sections.length > 0 ? (
        <>
          {outline.sections.map((s, i) => (
            <_Section key={i} section={s} idx={i} />
          ))}
          <ContrarianView claims={outline.contrarian_claims} />
        </>
      ) : (
        <_Markdown text={consolidated.narrative} />
      )}

      {/* Sources & References footer */}
      {consolidated.footnotes.length > 0 && (
        <div className="mt-8 pt-6 border-t border-foreground/8">
          <h3 className="font-display text-lg text-foreground mb-3">
            Sources &amp; References
          </h3>
          <ol className="space-y-1.5 text-sm">
            {consolidated.footnotes.map((fn) => (
              <li key={fn.n} className="flex gap-2 text-foreground/60">
                <span className="text-foreground/40 shrink-0">[{fn.n}]</span>
                <a
                  href={fn.citation.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-[var(--color-purple)] hover:underline break-all"
                >
                  {fn.citation.title || fn.citation.url}
                </a>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
