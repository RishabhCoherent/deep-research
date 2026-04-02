"use client";

import { useMemo, useEffect, useRef } from "react";
import {
  ReactFlow,
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  NodeProps,
  BackgroundVariant,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  CheckCircle2,
  Loader2,
  XCircle,
  Circle,
  GitBranch,
  X,
} from "lucide-react";
import type { ResearchNodeData, ResearchTreeData } from "@/lib/types";
import { cn } from "@/lib/utils";

// ── Depth colour palette ──────────────────────────────────────────────────────

const DEPTH_STYLES = {
  0: {
    bg: "bg-blue-50",
    border: "border-blue-400",
    text: "text-blue-700",
    badge: "bg-blue-100 text-blue-600",
    barColor: "#3B82F6",
    edgeColor: "#93C5FD",
    glow: "0 0 14px rgba(59,130,246,0.35)",
    label: "Root",
  },
  1: {
    bg: "bg-purple-50",
    border: "border-purple-400",
    text: "text-purple-700",
    badge: "bg-purple-100 text-purple-600",
    barColor: "#7C3AED",
    edgeColor: "#C4B5FD",
    glow: "0 0 14px rgba(124,58,237,0.35)",
    label: "Depth 1",
  },
  2: {
    bg: "bg-amber-50",
    border: "border-amber-400",
    text: "text-amber-700",
    badge: "bg-amber-100 text-amber-600",
    barColor: "#F59E0B",
    edgeColor: "#FCD34D",
    glow: "0 0 14px rgba(245,158,11,0.35)",
    label: "Depth 2",
  },
};

const DEAD_END_STYLE = {
  bg: "bg-gray-50",
  border: "border-gray-300",
  text: "text-gray-500",
  badge: "bg-gray-100 text-gray-400",
  barColor: "#9CA3AF",
  edgeColor: "#D1D5DB",
  glow: "none",
  label: "Dead end",
};

function getStyle(depth: number, status: string) {
  if (status === "dead-end") return DEAD_END_STYLE;
  return DEPTH_STYLES[depth as keyof typeof DEPTH_STYLES] ?? DEPTH_STYLES[2];
}

const WHY_LABELS: Record<string, string> = {
  root: "Root",
  vague_finding: "Vague",
  contradiction: "Contradiction",
  thin_data: "Thin data",
  surprising_data: "Surprising",
  missing_entity: "Missing entity",
};

// ── Custom node ───────────────────────────────────────────────────────────────

function ResearchNodeCard({ data, selected }: NodeProps) {
  const d = data as unknown as ResearchNodeData & { onSelect?: () => void };
  const s = getStyle(d.depth, d.status);
  const isActive = d.status === "exploring";

  return (
    <div
      onClick={d.onSelect}
      className={cn(
        "w-52 rounded-xl border-2 p-3 cursor-pointer transition-all duration-300 select-none",
        s.bg,
        s.border,
        selected && "ring-2 ring-offset-1 ring-blue-400",
        isActive && "animate-pulse-slow"
      )}
      style={{ boxShadow: isActive ? s.glow : selected ? s.glow : undefined }}
    >
      <Handle
        type="target"
        position={Position.Top}
        style={{ background: s.barColor, width: 8, height: 8 }}
      />

      {/* Header row */}
      <div className="flex items-center gap-1.5 mb-2">
        {d.status === "complete" ? (
          <CheckCircle2 className={cn("h-3.5 w-3.5 shrink-0", s.text)} />
        ) : d.status === "exploring" ? (
          <Loader2 className={cn("h-3.5 w-3.5 shrink-0 animate-spin", s.text)} />
        ) : d.status === "dead-end" ? (
          <XCircle className={cn("h-3.5 w-3.5 shrink-0", s.text)} />
        ) : (
          <Circle className={cn("h-3.5 w-3.5 shrink-0", s.text)} />
        )}
        <span className={cn("text-[9px] font-mono font-semibold px-1.5 py-0.5 rounded-full", s.badge)}>
          D{d.depth} · {WHY_LABELS[d.why_created] ?? d.why_created}
        </span>
      </div>

      {/* Query text */}
      <p className={cn("text-[11px] font-medium leading-snug line-clamp-3", s.text)}>
        {d.query}
      </p>

      {/* Confidence bar */}
      {d.confidence > 0 && (
        <div className="mt-2">
          <div className="flex justify-between items-center mb-0.5">
            <span className={cn("text-[9px] font-mono", s.text)}>confidence</span>
            <span className={cn("text-[9px] font-mono font-bold", s.text)}>
              {Math.round(d.confidence * 100)}%
            </span>
          </div>
          <div className="h-1 w-full rounded-full bg-black/10">
            <div
              className="h-1 rounded-full transition-all duration-500"
              style={{ width: `${d.confidence * 100}%`, background: s.barColor }}
            />
          </div>
        </div>
      )}

      {/* Evidence count */}
      {(d.evidence_ids?.length ?? 0) > 0 && (
        <p className={cn("text-[9px] font-mono mt-1.5", s.text)}>
          {d.evidence_ids.length} evidence piece{d.evidence_ids.length !== 1 ? "s" : ""}
        </p>
      )}

      <Handle
        type="source"
        position={Position.Bottom}
        style={{ background: s.barColor, width: 8, height: 8 }}
      />
    </div>
  );
}

const nodeTypes = { researchNode: ResearchNodeCard };

// ── Layout algorithm ──────────────────────────────────────────────────────────

const NODE_W = 220;
const NODE_H = 140;
const H_GAP = 48;
const V_GAP = 80;

/**
 * Bottom-up tree layout: compute subtree widths first, then position top-down.
 * This prevents overlapping when a root has many children.
 */
function layoutTree(nodes: Record<string, ResearchNodeData>): Record<string, { x: number; y: number }> {
  const positions: Record<string, { x: number; y: number }> = {};
  const ids = Object.keys(nodes);
  if (ids.length === 0) return positions;

  // Build parent → children map
  const childrenOf: Record<string, string[]> = {};
  const roots: string[] = [];
  for (const id of ids) {
    const pid = nodes[id].parent_id;
    if (!pid || !nodes[pid]) {
      roots.push(id);
    } else {
      if (!childrenOf[pid]) childrenOf[pid] = [];
      childrenOf[pid].push(id);
    }
  }

  // Compute subtree width bottom-up (how much horizontal space a node + descendants need)
  const subtreeW: Record<string, number> = {};
  function computeWidth(id: string): number {
    const kids = childrenOf[id] ?? [];
    if (kids.length === 0) {
      subtreeW[id] = NODE_W;
      return NODE_W;
    }
    const total = kids.reduce((sum, kid) => sum + computeWidth(kid), 0) + (kids.length - 1) * H_GAP;
    subtreeW[id] = Math.max(NODE_W, total);
    return subtreeW[id];
  }
  roots.forEach(computeWidth);

  // Position top-down: each node is centred within its allocated width
  function positionNode(id: string, left: number, y: number) {
    const w = subtreeW[id] ?? NODE_W;
    positions[id] = { x: left + w / 2 - NODE_W / 2, y };

    const kids = childrenOf[id] ?? [];
    if (kids.length === 0) return;

    let cursor = left;
    for (const kid of kids) {
      const kidW = subtreeW[kid] ?? NODE_W;
      positionNode(kid, cursor, y + NODE_H + V_GAP);
      cursor += kidW + H_GAP;
    }
  }

  // Lay out roots left to right
  let cursor = 0;
  for (const rootId of roots) {
    positionNode(rootId, cursor, 0);
    cursor += (subtreeW[rootId] ?? NODE_W) + H_GAP * 1.5;
  }

  return positions;
}

// ── Convert tree data → React Flow nodes + edges ──────────────────────────────

function buildFlow(
  nodes: Record<string, ResearchNodeData>,
  onSelect: (id: string) => void,
  selectedId: string | null
): { rfNodes: Node[]; rfEdges: Edge[] } {
  // Filter out dead-end nodes (budget exhausted before research — no useful data)
  const liveNodes: Record<string, ResearchNodeData> = {};
  for (const [id, node] of Object.entries(nodes)) {
    if (node.status !== "dead-end") {
      liveNodes[id] = node;
    }
  }

  const positions = layoutTree(liveNodes);
  const rfNodes: Node[] = [];
  const rfEdges: Edge[] = [];

  for (const [id, node] of Object.entries(liveNodes)) {
    const pos = positions[id] ?? { x: 0, y: 0 };
    rfNodes.push({
      id,
      type: "researchNode",
      position: pos,
      selected: id === selectedId,
      data: {
        ...node,
        onSelect: () => onSelect(id),
      },
    });
  }

  for (const [id, node] of Object.entries(liveNodes)) {
    if (!node.parent_id || !liveNodes[node.parent_id]) continue;
    const s = getStyle(node.depth, node.status);
    rfEdges.push({
      id: `e-${node.parent_id}-${id}`,
      source: node.parent_id,
      target: id,
      type: "smoothstep",
      animated: node.status === "exploring",
      style: { stroke: s.edgeColor, strokeWidth: 2 },
    });
  }

  return { rfNodes, rfEdges };
}

// ── Node detail side panel ────────────────────────────────────────────────────

function NodeDetailPanel({
  node,
  onClose,
}: {
  node: ResearchNodeData;
  onClose: () => void;
}) {
  const s = getStyle(node.depth, node.status);

  return (
    <div className="fixed top-24 right-6 w-96 max-h-[calc(100vh-7rem)] z-50 rounded-2xl border bg-background shadow-2xl flex flex-col overflow-hidden">
      {/* Header */}
      <div className={cn("flex items-center justify-between px-4 py-3 border-b", s.bg)}>
        <div className="flex items-center gap-2">
          <GitBranch className={cn("h-4 w-4", s.text)} />
          <span className={cn("text-xs font-mono font-semibold", s.text)}>
            {s.label} · {WHY_LABELS[node.why_created] ?? node.why_created}
          </span>
        </div>
        <button
          onClick={onClose}
          className="rounded-full p-1 hover:bg-black/10 transition-colors"
        >
          <X className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
      </div>

      <div className="p-4 space-y-3 flex-1 overflow-y-auto text-xs">
        {/* Query */}
        <div>
          <p className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
            Question
          </p>
          <p className="font-medium leading-snug text-foreground">{node.query}</p>
        </div>

        {/* Trigger */}
        {node.trigger_finding && (
          <div>
            <p className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
              Why spawned
            </p>
            <p className="text-muted-foreground leading-snug">{node.trigger_finding}</p>
          </div>
        )}

        {/* Hypothesis */}
        {node.hypothesis && (
          <div>
            <p className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
              Hypothesis
            </p>
            <p className="text-muted-foreground leading-snug italic">"{node.hypothesis}"</p>
          </div>
        )}

        {/* Answer */}
        {node.answer && (
          <div>
            <p className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
              Finding
            </p>
            <p className="text-foreground leading-snug">{node.answer}</p>
          </div>
        )}

        {/* Status + Confidence */}
        <div className="flex items-center gap-3 pt-1 border-t">
          <span
            className={cn(
              "text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full",
              s.badge
            )}
          >
            {node.status}
          </span>
          {node.confidence > 0 && (
            <span className="text-[10px] font-mono text-muted-foreground">
              {Math.round(node.confidence * 100)}% confidence
            </span>
          )}
          {(node.evidence_ids?.length ?? 0) > 0 && (
            <span className="text-[10px] font-mono text-muted-foreground">
              {node.evidence_ids.length} evidence
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Legend ────────────────────────────────────────────────────────────────────

function GraphLegend() {
  return (
    <div className="absolute bottom-3 left-3 z-10 flex items-center gap-3 rounded-xl border bg-background/90 backdrop-blur px-3 py-2">
      {[
        { color: "bg-blue-400", label: "Root question" },
        { color: "bg-purple-400", label: "Drill-down" },
        { color: "bg-amber-400", label: "Deep verify" },
        { color: "bg-gray-300", label: "Dead end" },
      ].map(({ color, label }) => (
        <div key={label} className="flex items-center gap-1.5">
          <div className={cn("h-2.5 w-2.5 rounded-full", color)} />
          <span className="text-[10px] font-mono text-muted-foreground">{label}</span>
        </div>
      ))}
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function GraphEmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-foreground/5">
        <GitBranch className="h-7 w-7 text-muted-foreground" />
      </div>
      <div>
        <p className="font-display text-base text-foreground">Research tree</p>
        <p className="text-xs text-muted-foreground mt-1 max-w-48">
          Nodes appear here when the agent starts going deeper on uncertain findings
        </p>
      </div>
    </div>
  );
}

// ── Inner graph (needs ReactFlowProvider wrapper) ─────────────────────────────

function GraphInner({
  nodes,
  selectedNodeId,
  onSelectNode,
}: {
  nodes: Record<string, ResearchNodeData>;
  selectedNodeId: string | null;
  onSelectNode: (id: string | null) => void;
}) {
  const { rfNodes, rfEdges } = useMemo(
    () => buildFlow(nodes, onSelectNode, selectedNodeId),
    [nodes, selectedNodeId, onSelectNode]
  );

  const { fitView } = useReactFlow();
  const nodeCountRef = useRef(rfNodes.length);

  // Re-fit the viewport whenever nodes are added
  useEffect(() => {
    if (rfNodes.length !== nodeCountRef.current) {
      nodeCountRef.current = rfNodes.length;
      // Small delay so React Flow has time to render the new nodes
      const t = setTimeout(() => fitView({ padding: 0.2, maxZoom: 1, duration: 300 }), 50);
      return () => clearTimeout(t);
    }
  }, [rfNodes.length, fitView]);

  const selectedNode = selectedNodeId ? nodes[selectedNodeId] : null;

  if (Object.keys(nodes).length === 0) return <GraphEmptyState />;

  return (
    <div className="relative w-full h-full">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
        minZoom={0.2}
        maxZoom={2}
        onNodeClick={(_, node) => onSelectNode(node.id)}
        onPaneClick={() => onSelectNode(null)}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#e5e7eb" />
        <Controls showInteractive={false} className="shadow-none! border! border-foreground/10! rounded-xl!" />
        {Object.keys(nodes).length > 12 && (
          <MiniMap
            nodeColor={(n) => {
              const nd = nodes[n.id];
              if (!nd) return "#e5e7eb";
              if (nd.status === "dead-end") return "#9ca3af";
              return nd.depth === 0 ? "#3b82f6" : nd.depth === 1 ? "#7c3aed" : "#f59e0b";
            }}
            className="rounded-xl! border! border-foreground/10!"
          />
        )}
      </ReactFlow>

      <GraphLegend />

      {selectedNode && (
        <NodeDetailPanel
          node={selectedNode}
          onClose={() => onSelectNode(null)}
        />
      )}
    </div>
  );
}

// ── Public component ──────────────────────────────────────────────────────────

interface ResearchGraphProps {
  /** Live node map from Zustand store (progress page) */
  liveNodes?: Record<string, ResearchNodeData>;
  /** Completed tree from result metadata (results page) */
  treeData?: ResearchTreeData;
  selectedNodeId?: string | null;
  onSelectNode?: (id: string | null) => void;
  className?: string;
}

export function ResearchGraph({
  liveNodes,
  treeData,
  selectedNodeId = null,
  onSelectNode = () => {},
  className,
}: ResearchGraphProps) {
  // Merge: prefer liveNodes when on progress page, treeData.nodes when on results page
  const nodes: Record<string, ResearchNodeData> = useMemo(() => {
    if (liveNodes && Object.keys(liveNodes).length > 0) return liveNodes;
    if (treeData?.nodes) return treeData.nodes;
    return {};
  }, [liveNodes, treeData]);

  const nodeCount = Object.values(nodes).filter(n => n.status !== "dead-end").length;

  return (
    <div className={cn("relative rounded-2xl border bg-background overflow-hidden", className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b bg-background/80">
        <div className="flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-muted-foreground" />
          <span className="text-xs font-mono font-semibold text-foreground">
            Research Tree
          </span>
        </div>
        {nodeCount > 0 && (
          <div className="flex items-center gap-3">
            <span className="text-[10px] font-mono text-muted-foreground">
              {nodeCount} node{nodeCount !== 1 ? "s" : ""}
            </span>
            {treeData && (
              <span className="text-[10px] font-mono text-muted-foreground">
                max depth {treeData.max_depth}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Graph canvas */}
      <div className="h-full w-full" style={{ minHeight: 380 }}>
        <ReactFlowProvider>
          <GraphInner
            nodes={nodes}
            selectedNodeId={selectedNodeId}
            onSelectNode={onSelectNode}
          />
        </ReactFlowProvider>
      </div>
    </div>
  );
}
