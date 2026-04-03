"use client";

import { useMemo, useState, useCallback, useEffect, useRef } from "react";
import {
  ReactFlow,
  Node,
  Edge,
  Background,
  Controls,
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
  XCircle,
  GitBranch,
  Search,
  FileDown,
  X,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import type { ResearchNodeData, ResearchTreeData } from "@/lib/types";
import { cn } from "@/lib/utils";

/* ── Styling ────────────────────────────────────────────────── */

const ROOT_STYLE = {
  bg: "bg-indigo-50",
  border: "border-indigo-400",
  text: "text-indigo-700",
  badge: "bg-indigo-100 text-indigo-600",
  edge: "#818CF8",
};

const PART_STYLE = {
  bg: "bg-purple-50",
  border: "border-purple-400",
  text: "text-purple-700",
  badge: "bg-purple-100 text-purple-600",
  edge: "#C4B5FD",
};

const DEAD_STYLE = {
  bg: "bg-gray-50",
  border: "border-gray-300",
  text: "text-gray-500",
  badge: "bg-gray-100 text-gray-400",
  edge: "#D1D5DB",
};

function getNodeStyle(depth: number, status: string) {
  if (status === "dead-end") return DEAD_STYLE;
  return depth === 0 ? ROOT_STYLE : PART_STYLE;
}

/* ── Custom Node ────────────────────────────────────────────── */

function TreeNode({ data }: NodeProps) {
  const d = data as ResearchNodeData & { onSelect: () => void };
  const s = getNodeStyle(d.depth, d.status);
  const evidenceCount = d.evidence_ids?.length || 0;
  const conf = Math.round(d.confidence * 100);

  return (
    <div
      onClick={d.onSelect}
      className={cn(
        "cursor-pointer rounded-xl border-2 px-4 py-3 shadow-sm transition-all hover:shadow-md",
        "min-w-[200px] max-w-[280px]",
        s.bg, s.border,
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-transparent !border-0" />

      {/* Header */}
      <div className="flex items-center gap-2 mb-1.5">
        <span className={cn("text-[10px] font-mono font-bold px-1.5 py-0.5 rounded", s.badge)}>
          {d.depth === 0 ? "Q" : `P${(d.children_ids?.indexOf?.(d.id) ?? 0) + 1}`}
          {d.depth === 0 ? "" : ""}
        </span>
        {d.status === "complete" ? (
          <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
        ) : d.status === "dead-end" ? (
          <XCircle className="h-3.5 w-3.5 text-gray-400" />
        ) : null}
      </div>

      {/* Question */}
      <p className={cn("text-xs font-medium leading-snug line-clamp-3", s.text)}>
        {d.query}
      </p>

      {/* Stats */}
      <div className="flex items-center gap-2 mt-2">
        {conf > 0 && (
          <span className="text-[10px] font-mono text-muted-foreground">{conf}%</span>
        )}
        {evidenceCount > 0 && (
          <span className="text-[10px] font-mono text-muted-foreground">{evidenceCount} evidence</span>
        )}
      </div>

      <Handle type="source" position={Position.Bottom} className="!bg-transparent !border-0" />
    </div>
  );
}

const nodeTypes = { treeNode: TreeNode };

/* ── Layout ─────────────────────────────────────────────────── */

function layoutNodes(nodes: Record<string, ResearchNodeData>) {
  const positions: Record<string, { x: number; y: number }> = {};

  // Group by parent
  const roots: string[] = [];
  const childrenOf: Record<string, string[]> = {};

  for (const [id, node] of Object.entries(nodes)) {
    if (node.status === "dead-end" && !(node.children_ids?.length > 0)) continue;
    if (!node.parent_id || !nodes[node.parent_id]) {
      roots.push(id);
    } else {
      if (!childrenOf[node.parent_id]) childrenOf[node.parent_id] = [];
      childrenOf[node.parent_id].push(id);
    }
  }

  const X_GAP = 300;
  const Y_GAP = 160;

  // Position roots horizontally
  let rootX = 0;
  for (const rootId of roots) {
    const children = childrenOf[rootId] || [];
    const totalWidth = Math.max(1, children.length) * X_GAP;
    positions[rootId] = { x: rootX + totalWidth / 2 - X_GAP / 2, y: 0 };

    // Position children below
    for (let i = 0; i < children.length; i++) {
      positions[children[i]] = { x: rootX + i * X_GAP, y: Y_GAP };
    }

    rootX += totalWidth + 60; // gap between root groups
  }

  return positions;
}

/* ── Node Detail Panel ──────────────────────────────────────── */

function NodeDetail({ node, onClose }: { node: ResearchNodeData; onClose: () => void }) {
  const s = getNodeStyle(node.depth, node.status);
  const conf = Math.round(node.confidence * 100);

  return (
    <div className="fixed top-24 right-6 w-96 max-h-[calc(100vh-7rem)] z-50 rounded-2xl border bg-background shadow-2xl flex flex-col overflow-hidden">
      {/* Header */}
      <div className={cn("flex items-center justify-between px-4 py-3 border-b", s.bg)}>
        <div className="flex items-center gap-2">
          <GitBranch className={cn("h-4 w-4", s.text)} />
          <span className={cn("text-xs font-mono font-semibold", s.text)}>
            {node.depth === 0 ? "Question" : "Part"} · {node.why_created || "decomposition"}
          </span>
        </div>
        <button onClick={onClose} className="rounded-full p-1 hover:bg-black/10 transition-colors">
          <X className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
      </div>

      {/* Content */}
      <div className="p-4 space-y-3 flex-1 overflow-y-auto text-xs">
        <div>
          <p className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Question</p>
          <p className="font-medium leading-snug text-foreground">{node.query}</p>
        </div>

        {node.trigger_finding && (
          <div>
            <p className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Why researched</p>
            <p className="text-muted-foreground leading-snug">{node.trigger_finding}</p>
          </div>
        )}

        {node.hypothesis && (
          <div>
            <p className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Hypothesis</p>
            <p className="text-muted-foreground leading-snug italic">"{node.hypothesis}"</p>
          </div>
        )}

        {node.answer && (
          <div>
            <p className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Finding</p>
            <p className="text-foreground leading-snug">{node.answer}</p>
          </div>
        )}

        <div className="flex items-center gap-3 pt-1 border-t">
          <span className={cn("text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full", s.badge)}>
            {node.status}
          </span>
          {conf > 0 && (
            <span className="text-[10px] font-mono text-muted-foreground">{conf}% confidence</span>
          )}
          {(node.evidence_ids?.length ?? 0) > 0 && (
            <span className="text-[10px] font-mono text-muted-foreground">{node.evidence_ids.length} evidence</span>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Main Component ─────────────────────────────────────────── */

function TreeFlow({
  nodes,
  selectedNodeId,
  onSelectNode,
}: {
  nodes: Record<string, ResearchNodeData>;
  selectedNodeId: string | null;
  onSelectNode: (id: string) => void;
}) {
  const { rfNodes, rfEdges } = useMemo(() => {
    const positions = layoutNodes(nodes);
    const rfNodes: Node[] = [];
    const rfEdges: Edge[] = [];

    for (const [id, node] of Object.entries(nodes)) {
      if (node.status === "dead-end" && !(node.children_ids?.length > 0)) continue;
      const pos = positions[id];
      if (!pos) continue;

      rfNodes.push({
        id,
        type: "treeNode",
        position: pos,
        selected: id === selectedNodeId,
        data: { ...node, onSelect: () => onSelectNode(id) },
      });
    }

    for (const [id, node] of Object.entries(nodes)) {
      if (!node.parent_id || !nodes[node.parent_id]) continue;
      if (node.status === "dead-end") continue;
      const s = getNodeStyle(node.depth, node.status);
      rfEdges.push({
        id: `e-${node.parent_id}-${id}`,
        source: node.parent_id,
        target: id,
        type: "smoothstep",
        style: { stroke: s.edge, strokeWidth: 2 },
      });
    }

    return { rfNodes, rfEdges };
  }, [nodes, selectedNodeId, onSelectNode]);

  const { fitView } = useReactFlow();
  const prevCount = useRef(rfNodes.length);
  useEffect(() => {
    if (rfNodes.length !== prevCount.current) {
      prevCount.current = rfNodes.length;
      setTimeout(() => fitView({ padding: 0.3, duration: 400 }), 100);
    }
  }, [rfNodes.length, fitView]);

  return (
    <ReactFlow
      nodes={rfNodes}
      edges={rfEdges}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: 0.3 }}
      minZoom={0.3}
      maxZoom={1.5}
      proOptions={{ hideAttribution: true }}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable
      onNodeClick={(_event, node) => onSelectNode(node.id)}
      panOnScroll
      zoomOnScroll
    >
      <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="rgba(0,0,0,0.05)" />
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}

/* ── Exported Component ─────────────────────────────────────── */

interface DecompositionTreeProps {
  treeData?: ResearchTreeData;
  className?: string;
}

export function DecompositionTree({ treeData, className }: DecompositionTreeProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const nodes = useMemo(() => {
    if (treeData?.nodes) return treeData.nodes;
    return {};
  }, [treeData]);

  const nodeCount = Object.values(nodes).filter(n => n.status !== "dead-end").length;
  const rootCount = Object.values(nodes).filter(n => n.depth === 0 && n.status !== "dead-end").length;
  const partCount = Object.values(nodes).filter(n => n.depth > 0 && n.status !== "dead-end").length;
  const selectedNode = selectedNodeId ? nodes[selectedNodeId] : null;

  if (nodeCount === 0) return null;

  return (
    <div className={cn("relative rounded-2xl border bg-background overflow-hidden", className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b bg-background/80">
        <div className="flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-muted-foreground" />
          <span className="text-xs font-mono font-semibold text-foreground">
            Research Decomposition
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-mono text-muted-foreground">
            {rootCount} questions → {partCount} parts
          </span>
        </div>
      </div>

      {/* Graph */}
      <div className="h-full min-h-[300px]">
        <ReactFlowProvider>
          <TreeFlow
            nodes={nodes}
            selectedNodeId={selectedNodeId}
            onSelectNode={setSelectedNodeId}
          />
        </ReactFlowProvider>
      </div>

      {/* Detail panel */}
      {selectedNode && (
        <NodeDetail node={selectedNode} onClose={() => setSelectedNodeId(null)} />
      )}
    </div>
  );
}
