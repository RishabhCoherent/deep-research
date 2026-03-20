"use client";

import React, {
  useEffect,
  useRef,
  useState,
  useMemo,
  useCallback,
} from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  MessageSquareText,
  ScanSearch,
  Crosshair,
  FileText,
  Bot,
  BrainCircuit,
  BarChart3,
  FileCheck,
  Scissors,
  Map,
  SearchCheck,
  Merge,
  PenTool,
  Paintbrush,
  RefreshCw,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

/* ─── Types ────────────────────────────────────────────────── */

interface WNode {
  id: string;
  label: string;
  sublabel?: string;
  description?: string;
  Icon: LucideIcon;
  type: "start" | "process" | "layer" | "phase" | "end";
  x: number;
  y: number;
  w: number;
  h: number;
}

interface WEdge {
  from: string;
  to: string;
  type: "main" | "internal" | "loop" | "vertical";
}

interface WGroup {
  id: string;
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

/* ────────────────────────────────────────────────────────────
   Compact 4-row layout — 1400×560 viewBox (tighter rows)

   Row 1 (y=20):  Topic → Interpret → Scope
   Row 2 (y=145): Baseline → Enhanced ↻ → Expert
   Row 3 (y=290): Dissect→Plan→Investigate→Synth→Compose→Format
   Row 4 (y=425): Evaluate → Report
   ──────────────────────────────────────────────────────────── */

const VB_W = 1400;
const VB_H = 530;
const CX = VB_W / 2;

/* — Row 1: Pre-processing ——————————————————————————————————— */
const R1 = 22;
const ROW1_NODES: WNode[] = [
  {
    id: "input",
    label: "Topic Input",
    sublabel: "User query",
    description: "User enters a research topic and brief",
    Icon: MessageSquareText,
    type: "start",
    x: CX - 310,
    y: R1,
    w: 160,
    h: 66,
  },
  {
    id: "interpret",
    label: "Interpret",
    sublabel: "Disambiguate",
    description: "Interpret and disambiguate the research topic",
    Icon: ScanSearch,
    type: "process",
    x: CX - 80,
    y: R1,
    w: 160,
    h: 66,
  },
  {
    id: "scope",
    label: "Scope",
    sublabel: "Set boundaries",
    description: "Auto-generate research boundaries and scope",
    Icon: Crosshair,
    type: "process",
    x: CX + 150,
    y: R1,
    w: 160,
    h: 66,
  },
];

/* — Row 2: Three layers ————————————————————————————————————— */
const R2 = 150;
const ROW2_NODES: WNode[] = [
  {
    id: "baseline",
    label: "Baseline",
    sublabel: "L0  ·  No tools",
    description: "Single LLM prompt — model knowledge only, no web research",
    Icon: FileText,
    type: "layer",
    x: CX - 340,
    y: R2,
    w: 195,
    h: 78,
  },
  {
    id: "enhanced",
    label: "Enhanced",
    sublabel: "L1  ·  Agent loop",
    description:
      "ReAct agent with web search, page scraping, and source assessment. Loops until quality threshold met.",
    Icon: Bot,
    type: "layer",
    x: CX - 98,
    y: R2,
    w: 195,
    h: 78,
  },
  {
    id: "expert",
    label: "Expert",
    sublabel: "L2  ·  6 phases",
    description:
      "Full agentic pipeline with claim analysis, evidence gathering, synthesis, and composition",
    Icon: BrainCircuit,
    type: "layer",
    x: CX + 145,
    y: R2,
    w: 195,
    h: 78,
  },
];

/* — Row 3: Expert phases ———————————————————————————————————— */
const R3 = 300;
const R3_GAP = 178;
const R3_X0 = (VB_W - R3_GAP * 5 - 155) / 2;

const PHASE_NODES: WNode[] = [
  {
    id: "dissect",
    label: "Dissect",
    sublabel: "Grade claims",
    Icon: Scissors,
    type: "phase",
    x: R3_X0,
    y: R3,
    w: 155,
    h: 60,
    description: "Extract and grade every claim from the prior report",
  },
  {
    id: "plan",
    label: "Plan",
    sublabel: "Research queries",
    Icon: Map,
    type: "phase",
    x: R3_X0 + R3_GAP,
    y: R3,
    w: 155,
    h: 60,
    description: "Generate targeted research queries per weak claim",
  },
  {
    id: "investigate",
    label: "Investigate",
    sublabel: "Gather evidence",
    Icon: SearchCheck,
    type: "phase",
    x: R3_X0 + R3_GAP * 2,
    y: R3,
    w: 155,
    h: 60,
    description: "Agent with evidence tracking — search, scrape, record findings",
  },
  {
    id: "synthesize",
    label: "Synthesize",
    sublabel: "Cross-reference",
    Icon: Merge,
    type: "phase",
    x: R3_X0 + R3_GAP * 3,
    y: R3,
    w: 155,
    h: 60,
    description: "Cross-reference findings, resolve contradictions, surface insights",
  },
  {
    id: "compose",
    label: "Compose",
    sublabel: "Write report",
    Icon: PenTool,
    type: "phase",
    x: R3_X0 + R3_GAP * 4,
    y: R3,
    w: 155,
    h: 60,
    description: "Write the final report with evidence anchoring",
  },
  {
    id: "format",
    label: "Format",
    sublabel: "Final polish",
    Icon: Paintbrush,
    type: "phase",
    x: R3_X0 + R3_GAP * 5,
    y: R3,
    w: 155,
    h: 60,
    description: "Reformat for readability — tables, bullets, structure",
  },
];

/* — Row 4: Output ——————————————————————————————————————————— */
const R4 = 438;
const ROW4_NODES: WNode[] = [
  {
    id: "evaluate",
    label: "Evaluate",
    sublabel: "7 dimensions",
    description: "Score all layers on factual density, analytical depth, specificity and more",
    Icon: BarChart3,
    type: "process",
    x: CX - 230,
    y: R4,
    w: 170,
    h: 66,
  },
  {
    id: "report",
    label: "Final Report",
    sublabel: "Comparative output",
    description: "Comparative report with evaluations, claim journeys, and executive summary",
    Icon: FileCheck,
    type: "end",
    x: CX + 60,
    y: R4,
    w: 170,
    h: 66,
  },
];

const ALL_NODES = [...ROW1_NODES, ...ROW2_NODES, ...PHASE_NODES, ...ROW4_NODES];

/* ─── Edges ────────────────────────────────────────────────── */

const EDGES: WEdge[] = [
  { from: "input", to: "interpret", type: "main" },
  { from: "interpret", to: "scope", type: "main" },
  { from: "scope", to: "baseline", type: "vertical" },
  { from: "baseline", to: "enhanced", type: "main" },
  { from: "enhanced", to: "expert", type: "main" },
  { from: "enhanced", to: "enhanced", type: "loop" },
  { from: "expert", to: "dissect", type: "vertical" },
  { from: "dissect", to: "plan", type: "internal" },
  { from: "plan", to: "investigate", type: "internal" },
  { from: "investigate", to: "synthesize", type: "internal" },
  { from: "synthesize", to: "compose", type: "internal" },
  { from: "compose", to: "format", type: "internal" },
  { from: "format", to: "evaluate", type: "vertical" },
  { from: "evaluate", to: "report", type: "main" },
];

/* ─── Groups (with filled backgrounds) ─────────────────────── */

const GROUPS: WGroup[] = [
  {
    id: "g-pre",
    label: "Pre-processing",
    x: CX - 330,
    y: R1 - 20,
    w: 660,
    h: 106,
  },
  {
    id: "g-layers",
    label: "Research Layers",
    x: CX - 360,
    y: R2 - 22,
    w: 720,
    h: 122,
  },
  {
    id: "g-phases",
    label: "Expert Pipeline  ·  Layer 2",
    x: R3_X0 - 16,
    y: R3 - 22,
    w: R3_GAP * 5 + 155 + 32,
    h: 104,
  },
  {
    id: "g-output",
    label: "Output",
    x: CX - 250,
    y: R4 - 20,
    w: 500,
    h: 106,
  },
];

/* ─── Highlight cycle ──────────────────────────────────────── */

const HIGHLIGHT_ORDER = [
  "input", "interpret", "scope",
  "baseline", "enhanced", "expert",
  "dissect", "plan", "investigate", "synthesize", "compose", "format",
  "evaluate", "report",
];

/* ─── Helpers ──────────────────────────────────────────────── */

function nodeById(id: string) {
  return ALL_NODES.find((n) => n.id === id);
}
function midX(n: WNode) { return n.x + n.w / 2; }
function midY(n: WNode) { return n.y + n.h / 2; }

function buildEdgePath(edge: WEdge): string {
  const from = nodeById(edge.from);
  const to = nodeById(edge.to);
  if (!from || !to) return "";

  if (edge.type === "loop") {
    const x = midX(from);
    const top = from.y;
    return `M ${x - 32} ${top} C ${x - 65} ${top - 50}, ${x + 65} ${top - 50}, ${x + 32} ${top}`;
  }

  if (edge.type === "vertical") {
    const fx = midX(from), fy = from.y + from.h;
    const tx = midX(to), ty = to.y;
    const my = (fy + ty) / 2;
    return `M ${fx} ${fy} C ${fx} ${my}, ${tx} ${my}, ${tx} ${ty}`;
  }

  const fx = from.x + from.w, fy = midY(from);
  const tx = to.x, ty = midY(to);
  const dx = Math.max((tx - fx) * 0.4, 20);
  return `M ${fx} ${fy} C ${fx + dx} ${fy}, ${tx - dx} ${ty}, ${tx} ${ty}`;
}

/* ─── Easing ───────────────────────────────────────────────── */

const ease = [0.22, 1, 0.36, 1] as unknown as number[];

/* ─── Node component ───────────────────────────────────────── */

const WorkflowNode = React.memo(function WorkflowNode({
  node, index, isActive, isHovered, onHover, visible,
}: {
  node: WNode; index: number; isActive: boolean;
  isHovered: boolean; onHover: (id: string | null) => void; visible: boolean;
}) {
  const isLayer = node.type === "layer";
  const isPhase = node.type === "phase";

  return (
    <motion.div
      className="absolute select-none cursor-pointer"
      style={{
        left: `${(node.x / VB_W) * 100}%`,
        top: `${(node.y / VB_H) * 100}%`,
        width: `${(node.w / VB_W) * 100}%`,
        height: `${(node.h / VB_H) * 100}%`,
      }}
      initial={{ opacity: 0, scale: 0.88, filter: "blur(6px)" }}
      animate={
        visible
          ? { opacity: 1, scale: isActive ? 1.05 : isHovered ? 1.03 : 1, filter: "blur(0px)" }
          : { opacity: 0, scale: 0.88, filter: "blur(6px)" }
      }
      transition={{ delay: visible ? index * 0.06 : 0, duration: 0.5, ease, scale: { duration: 0.3 } }}
      onMouseEnter={() => onHover(node.id)}
      onMouseLeave={() => onHover(null)}
    >
      <div
        className={`relative h-full ${isLayer ? "rounded-2xl" : "rounded-xl"}`}
        style={{
          background: isActive
            ? "rgba(255,255,255,1)"
            : isLayer
              ? "rgba(255,255,255,0.95)"
              : "rgba(255,255,255,0.92)",
          border: `1.5px solid ${
            isActive ? "rgba(0,0,0,0.28)" : isHovered ? "rgba(0,0,0,0.20)" : "rgba(0,0,0,0.14)"
          }`,
          boxShadow: isActive
            ? "0 4px 20px rgba(0,0,0,0.10), 0 1px 4px rgba(0,0,0,0.06)"
            : isHovered
              ? "0 3px 14px rgba(0,0,0,0.07), 0 1px 3px rgba(0,0,0,0.04)"
              : "0 2px 8px rgba(0,0,0,0.05), 0 1px 2px rgba(0,0,0,0.03)",
          transition: "border-color 0.3s, box-shadow 0.3s, background 0.3s",
        }}
      >
        {/* Left accent bar */}
        <div
          className={`absolute left-0 top-2.5 bottom-2.5 w-1 ${isLayer ? "rounded-l-2xl" : "rounded-l-xl"}`}
          style={{
            background: "#000",
            opacity: isActive ? 0.35 : 0.12,
            transition: "opacity 0.3s",
          }}
        />

        <div className="flex items-center gap-3 h-full px-4">
          <node.Icon
            className={`shrink-0 ${isLayer ? "h-5 w-5" : "h-4.5 w-4.5"}`}
            style={{ opacity: isActive ? 0.9 : 0.55, transition: "opacity 0.3s" }}
          />
          <div className="min-w-0 flex-1">
            <div className={`font-medium leading-tight ${isLayer ? "text-[15px]" : isPhase ? "text-[13px]" : "text-sm"}`}>
              {node.label}
            </div>
            {node.sublabel && (
              <div className={`font-mono leading-tight mt-0.5 ${
                isLayer ? "text-[11px] text-foreground/50" : "text-[10px] text-foreground/45"
              }`}>
                {node.sublabel}
              </div>
            )}
          </div>
        </div>

        {/* Breathing pulse */}
        <div
          className="absolute inset-0 pointer-events-none workflow-node-breathe"
          style={{
            background: "radial-gradient(ellipse at center, rgba(0,0,0,0.025) 0%, transparent 70%)",
            borderRadius: "inherit",
          }}
        />
      </div>

      {/* Tooltip */}
      <AnimatePresence>
        {isHovered && node.description && (
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.96 }}
            transition={{ duration: 0.18 }}
            className="absolute left-1/2 -translate-x-1/2 z-50 pointer-events-none"
            style={{ top: `calc(100% + 12px)` }}
          >
            <div
              className="rounded-xl px-4 py-2.5 text-[12px] leading-relaxed max-w-[260px] text-center"
              style={{
                background: "rgba(8,8,12,0.92)",
                color: "rgba(255,255,255,0.90)",
                border: "1px solid rgba(255,255,255,0.08)",
                boxShadow: "0 8px 32px rgba(0,0,0,0.25)",
                backdropFilter: "blur(20px)",
              }}
            >
              {node.description}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
});

/* ─── Edge component ───────────────────────────────────────── */

const WorkflowEdge = React.memo(function WorkflowEdge({
  edge, index, visible, isActive,
}: {
  edge: WEdge; index: number; visible: boolean; isActive: boolean;
}) {
  const path = useMemo(() => buildEdgePath(edge), [edge]);
  if (!path) return null;

  const isLoop = edge.type === "loop";
  const isInternal = edge.type === "internal";
  const isVertical = edge.type === "vertical";
  const sw = isInternal ? 1.5 : isLoop ? 1.5 : 2;

  return (
    <g>
      {isActive && (
        <path d={path} fill="none" stroke="#000" strokeWidth={sw + 6}
          strokeOpacity={0.04} filter="url(#edge-glow)" />
      )}

      <motion.path
        d={path} fill="none" stroke="#000" strokeWidth={sw} strokeLinecap="round"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={visible
          ? { pathLength: 1, opacity: isActive ? 0.40 : isInternal ? 0.18 : 0.22 }
          : { pathLength: 0, opacity: 0 }
        }
        transition={{ delay: index * 0.05 + 0.3, duration: 0.8, ease }}
        className={isActive ? "workflow-edge-active" : "workflow-edge"}
        style={{ strokeDasharray: "5 9" }}
      />

      {/* Particle */}
      {visible && (
        <circle r={isInternal ? 3 : 3.5} fill="#000" opacity={isActive ? 0.5 : 0.25}>
          <animateMotion
            dur={isLoop ? "1.8s" : isVertical ? "1.6s" : isInternal ? "2s" : "2.5s"}
            repeatCount="indefinite" path={path}
          />
        </circle>
      )}

      {/* Loop icon */}
      {isLoop && visible && (() => {
        const n = nodeById(edge.from);
        if (!n) return null;
        return (
          <foreignObject x={midX(n) - 10} y={n.y - 38} width={20} height={20}
            className="overflow-visible">
            <div className="flex items-center justify-center w-5 h-5">
              <RefreshCw className="h-4 w-4 animate-spin text-foreground/60"
                style={{ animationDuration: "5s" }} />
            </div>
          </foreignObject>
        );
      })()}
    </g>
  );
});

/* ─── Group boundary ───────────────────────────────────────── */

const WorkflowGroup = React.memo(function WorkflowGroup({
  group, visible, isActive,
}: { group: WGroup; visible: boolean; isActive: boolean; }) {
  return (
    <g>
      {/* Filled background for the group */}
      <motion.rect
        x={group.x} y={group.y} width={group.w} height={group.h}
        rx={16} ry={16}
        initial={{ opacity: 0 }}
        animate={visible
          ? { opacity: 1, fill: isActive ? "rgba(0,0,0,0.028)" : "rgba(0,0,0,0.015)" }
          : { opacity: 0 }
        }
        transition={{ duration: 0.5, delay: 0.3 }}
      />
      {/* Border */}
      <motion.rect
        x={group.x} y={group.y} width={group.w} height={group.h}
        rx={16} ry={16} fill="none"
        initial={{ opacity: 0 }}
        animate={visible
          ? { opacity: 1, stroke: isActive ? "rgba(0,0,0,0.18)" : "rgba(0,0,0,0.09)" }
          : { opacity: 0 }
        }
        transition={{ duration: 0.5, delay: 0.35 }}
        strokeWidth={1.2} strokeDasharray="6 5"
        className="workflow-group"
      />
    </g>
  );
});

/* ─── Main component ───────────────────────────────────────── */

export function WorkflowVisualization() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [activeId, setActiveId] = useState(HIGHLIGHT_ORDER[0]);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const cycleRef = useRef<ReturnType<typeof setInterval>>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setVisible(true); obs.disconnect(); } },
      { threshold: 0.1 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (!visible) return;
    let idx = 0;
    cycleRef.current = setInterval(() => {
      idx = (idx + 1) % HIGHLIGHT_ORDER.length;
      setActiveId(HIGHLIGHT_ORDER[idx]);
    }, 2000);
    return () => { if (cycleRef.current) clearInterval(cycleRef.current); };
  }, [visible]);

  const handleHover = useCallback((id: string | null) => {
    setHoveredId(id);
    if (id) {
      if (cycleRef.current) clearInterval(cycleRef.current);
      setActiveId(id);
    } else {
      let idx = HIGHLIGHT_ORDER.indexOf(activeId);
      cycleRef.current = setInterval(() => {
        idx = (idx + 1) % HIGHLIGHT_ORDER.length;
        setActiveId(HIGHLIGHT_ORDER[idx]);
      }, 2000);
    }
  }, [activeId]);

  const activeEdges = useMemo(() => {
    const s = new Set<string>();
    EDGES.forEach((e) => {
      if (e.from === activeId || e.to === activeId) s.add(`${e.from}-${e.to}`);
    });
    return s;
  }, [activeId]);

  const activeGroup = useMemo(() => {
    if (ROW1_NODES.find((n) => n.id === activeId)) return "g-pre";
    if (ROW2_NODES.find((n) => n.id === activeId)) return "g-layers";
    if (PHASE_NODES.find((n) => n.id === activeId)) return "g-phases";
    if (ROW4_NODES.find((n) => n.id === activeId)) return "g-output";
    return null;
  }, [activeId]);

  return (
    <div ref={containerRef} className="relative w-full" style={{ aspectRatio: `${VB_W} / ${VB_H}` }}>
      <svg className="absolute inset-0 w-full h-full pointer-events-none"
        viewBox={`0 0 ${VB_W} ${VB_H}`} preserveAspectRatio="xMidYMid meet">
        <defs>
          <filter id="edge-glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {GROUPS.map((g) => (
          <WorkflowGroup key={g.id} group={g} visible={visible} isActive={activeGroup === g.id} />
        ))}
        {EDGES.map((e, i) => (
          <WorkflowEdge key={`${e.from}-${e.to}`} edge={e} index={i}
            visible={visible} isActive={activeEdges.has(`${e.from}-${e.to}`)} />
        ))}
      </svg>

      {ALL_NODES.map((node, i) => (
        <WorkflowNode key={node.id} node={node} index={i}
          isActive={activeId === node.id} isHovered={hoveredId === node.id}
          onHover={handleHover} visible={visible} />
      ))}

      {/* Group labels */}
      {GROUPS.map((g) => (
        <motion.div
          key={`label-${g.id}`}
          className="absolute pointer-events-none flex items-center gap-2"
          style={{
            left: `${((g.x + 12) / VB_W) * 100}%`,
            top: `${((g.y + 5) / VB_H) * 100}%`,
          }}
          initial={{ opacity: 0 }}
          animate={visible ? { opacity: 1 } : { opacity: 0 }}
          transition={{ delay: 0.5 }}
        >
          <span className="font-mono text-[10px] font-semibold tracking-wider uppercase"
            style={{
              color: activeGroup === g.id ? "rgba(0,0,0,0.55)" : "rgba(0,0,0,0.30)",
              transition: "color 0.3s",
            }}>
            {g.id === "g-pre" ? "01" : g.id === "g-layers" ? "02" : g.id === "g-phases" ? "03" : "04"}
          </span>
          <span className="text-[10px] font-medium tracking-wide"
            style={{
              color: activeGroup === g.id ? "rgba(0,0,0,0.42)" : "rgba(0,0,0,0.20)",
              transition: "color 0.3s",
            }}>
            {g.label}
          </span>
        </motion.div>
      ))}
    </div>
  );
}
