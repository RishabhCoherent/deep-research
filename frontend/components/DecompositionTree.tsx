"use client";

import { useMemo, useState, useCallback, useRef } from "react";
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
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  CheckCircle2,
  XCircle,
  GitBranch,
  X,
  Sparkles,
  Search,
  Puzzle,
  Layers,
} from "lucide-react";
import type { ResearchNodeData, ResearchTreeData } from "@/lib/types";
import { cn } from "@/lib/utils";

/* ── Depth config — monochrome with subtle accent bars ─────── */

const DEPTH_CONFIG: Record<number, {
  accent: string; label: string; Icon: React.ElementType;
}> = {
  0: { accent: "rgba(0,0,0,0.40)", label: "T", Icon: Sparkles },
  1: { accent: "rgba(0,0,0,0.25)", label: "Q", Icon: Search },
  2: { accent: "rgba(0,0,0,0.15)", label: "P", Icon: Puzzle },
  3: { accent: "rgba(0,0,0,0.10)", label: "S", Icon: Layers },
};

const DEPTH_LABELS: Record<number, string> = {
  0: "Topic", 1: "Question", 2: "Part", 3: "Sub-part",
};

const EDGE_COLOR = "rgba(0,0,0,0.15)";
const EDGE_COLOR_ACTIVE = "rgba(0,0,0,0.30)";

/* ── Custom Node — matches WorkflowVisualization style ──────── */

function TreeNode({ data }: NodeProps) {
  const d = data as ResearchNodeData & { onSelect: () => void };
  const cfg = DEPTH_CONFIG[d.depth] || DEPTH_CONFIG[2];
  const evidenceCount = d.evidence_ids?.length || 0;
  const conf = Math.round(d.confidence * 100);
  const isTopicRoot = d.depth === 0;
  const isDead = d.status === "dead-end";

  return (
    <div
      onClick={d.onSelect}
      className="cursor-pointer group"
      style={{
        width: isTopicRoot ? 300 : d.depth === 1 ? 260 : 220,
      }}
    >
      <Handle type="target" position={Position.Top} className="bg-transparent! border-0!" />

      <div
        className="relative rounded-xl overflow-hidden transition-all duration-200"
        style={{
          background: isDead ? "rgba(245,245,245,0.95)" : "rgba(255,255,255,0.95)",
          border: `1.5px solid ${isDead ? "rgba(0,0,0,0.08)" : "rgba(0,0,0,0.14)"}`,
          boxShadow: "0 2px 8px rgba(0,0,0,0.05), 0 1px 2px rgba(0,0,0,0.03)",
        }}
      >
        {/* Left accent bar */}
        <div
          className="absolute left-0 top-2.5 bottom-2.5 w-1 rounded-r-full"
          style={{
            background: isDead ? "rgba(0,0,0,0.06)" : cfg.accent,
            transition: "opacity 0.3s",
          }}
        />

        <div className="px-3.5 py-3 pl-4">
          {/* Header row */}
          <div className="flex items-center gap-2 mb-1.5">
            <cfg.Icon
              className="h-3.5 w-3.5 shrink-0"
              style={{ opacity: isDead ? 0.3 : 0.55 }}
            />
            <span className="text-[9px] font-mono text-foreground/45 uppercase tracking-wider">
              {DEPTH_LABELS[d.depth] || "Node"}
            </span>
            {d.status === "complete" ? (
              <CheckCircle2 className="h-3 w-3 text-foreground/40 ml-auto" />
            ) : d.status === "dead-end" ? (
              <XCircle className="h-3 w-3 text-foreground/25 ml-auto" />
            ) : d.status === "exploring" ? (
              <span className="h-2 w-2 rounded-full bg-foreground/30 animate-pulse ml-auto" />
            ) : null}
          </div>

          {/* Query text */}
          <p className={cn(
            "font-medium leading-snug line-clamp-3",
            isTopicRoot ? "text-sm" : "text-xs",
            isDead ? "text-foreground/40" : "text-foreground/85",
          )}>
            {d.query}
          </p>

          {/* Stats */}
          {(conf > 0 || evidenceCount > 0) && (
            <div className="flex items-center gap-2 mt-2">
              {conf > 0 && (
                <span className="text-[9px] font-mono text-foreground/35">{conf}%</span>
              )}
              {evidenceCount > 0 && (
                <span className="text-[9px] font-mono text-foreground/35">{evidenceCount} ev</span>
              )}
              {(d.children_ids?.length ?? 0) > 0 && (
                <span className="text-[9px] font-mono text-foreground/35">{d.children_ids.length} parts</span>
              )}
            </div>
          )}
        </div>
      </div>

      <Handle type="source" position={Position.Bottom} className="bg-transparent! border-0!" />
    </div>
  );
}

const nodeTypes = { treeNode: TreeNode };

/* ── Hierarchical top-down layout ─────────────────────────────── */

function layoutNodes(
  nodes: Record<string, ResearchNodeData>,
  topicRootId?: string,
) {
  const positions: Record<string, { x: number; y: number }> = {};

  // Build children index (filter dead-end leaves)
  const childrenOf: Record<string, string[]> = {};
  const allIds = new Set<string>();

  for (const [id, node] of Object.entries(nodes)) {
    if (node.status === "dead-end" && !(node.children_ids?.length > 0)) continue;
    allIds.add(id);
    if (node.parent_id && nodes[node.parent_id]) {
      if (!childrenOf[node.parent_id]) childrenOf[node.parent_id] = [];
      childrenOf[node.parent_id].push(id);
    }
  }

  // Find root
  let rootId = topicRootId && allIds.has(topicRootId) ? topicRootId : "";
  if (!rootId) {
    const orphans = [...allIds].filter(id => {
      const n = nodes[id];
      return !n.parent_id || !nodes[n.parent_id];
    });
    if (orphans.length === 1) {
      rootId = orphans[0];
    } else if (orphans.length > 1) {
      // Backward compat: virtual root for old multi-root data
      rootId = "__virtual_root__";
      childrenOf[rootId] = orphans;
    }
  }

  if (!rootId) return positions;

  const Y_GAP = 180;
  const SIBLING_GAP = 20; // px gap between sibling nodes
  // Node widths per depth
  const NODE_W: Record<number, number> = { 0: 300, 1: 260, 2: 220, 3: 220 };
  const getW = (d: number) => NODE_W[d] ?? 220;

  // Step 1: Compute minimum width each subtree needs (bottom-up)
  const spanCache: Record<string, number> = {};
  function subtreeSpan(nodeId: string, depth: number): number {
    if (spanCache[nodeId] !== undefined) return spanCache[nodeId];
    const kids = childrenOf[nodeId] || [];
    if (kids.length === 0) {
      spanCache[nodeId] = getW(depth);
      return spanCache[nodeId];
    }
    let total = 0;
    for (let i = 0; i < kids.length; i++) {
      if (i > 0) total += SIBLING_GAP;
      total += subtreeSpan(kids[i], depth + 1);
    }
    // Parent span is at least its own width
    spanCache[nodeId] = Math.max(getW(depth), total);
    return spanCache[nodeId];
  }

  // Step 2: Assign positions top-down, centering parent over children
  function assign(nodeId: string, centerX: number, y: number, depth: number) {
    if (nodeId !== "__virtual_root__") {
      positions[nodeId] = { x: centerX - getW(depth) / 2, y };
    }

    const kids = childrenOf[nodeId] || [];
    if (kids.length === 0) return;

    // Total width of all children
    const kidSpans = kids.map(k => subtreeSpan(k, depth + 1));
    const totalKidsW = kidSpans.reduce((a, b) => a + b, 0) + SIBLING_GAP * (kids.length - 1);

    const nextY = nodeId === "__virtual_root__" ? y : y + Y_GAP;
    let cx = centerX - totalKidsW / 2;

    for (let i = 0; i < kids.length; i++) {
      const kidCenter = cx + kidSpans[i] / 2;
      assign(kids[i], kidCenter, nextY, depth + 1);
      cx += kidSpans[i] + SIBLING_GAP;
    }
  }

  const rootDepth = rootId === "__virtual_root__" ? -1 : 0;
  const rootSpan = subtreeSpan(rootId, rootDepth);
  assign(rootId, rootSpan / 2, 0, rootDepth);
  return positions;
}

/* ── Node Detail Panel ──────────────────────────────────────── */

function NodeDetail({
  node, allNodes, onClose,
}: {
  node: ResearchNodeData;
  allNodes: Record<string, ResearchNodeData>;
  onClose: () => void;
}) {
  const conf = Math.round(node.confidence * 100);
  const depthLabel = DEPTH_LABELS[node.depth] || "Node";
  const cfg = DEPTH_CONFIG[node.depth] || DEPTH_CONFIG[2];

  const parentNode = node.parent_id ? allNodes[node.parent_id] : null;
  const whyText =
    node.trigger_finding && !/^(Sub-p|P)art \d+$/i.test(node.trigger_finding)
      ? node.trigger_finding
      : parentNode && parentNode.depth >= 0
        ? `Part of: "${parentNode.query}"`
        : "";

  return (
    <div
      className="fixed top-24 right-6 w-96 z-50 rounded-2xl flex flex-col overflow-hidden"
      style={{
        maxHeight: "calc(100dvh - 7rem)",
        background: "rgba(255,255,255,0.98)",
        border: "1.5px solid rgba(0,0,0,0.14)",
        boxShadow: "0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06)",
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-foreground/8 shrink-0">
        <div className="flex items-center gap-2">
          <cfg.Icon className="h-4 w-4" style={{ opacity: 0.55 }} />
          <span className="text-xs font-mono text-foreground/50">
            {depthLabel} · {node.why_created === "topic_root" ? "root topic" : node.why_created || "decomposition"}
          </span>
        </div>
        <button onClick={onClose} className="rounded-full p-1 hover:bg-foreground/5 transition-colors">
          <X className="h-3.5 w-3.5 text-foreground/40" />
        </button>
      </div>

      {/* Content */}
      <div className="p-4 space-y-3 flex-1 overflow-y-auto text-xs min-h-0">
        <div>
          <p className="font-mono text-[9px] text-foreground/40 uppercase tracking-wider mb-1">
            {depthLabel}
          </p>
          <p className="font-medium leading-snug text-foreground/90">{node.query}</p>
        </div>

        {whyText && node.depth > 0 && (
          <div>
            <p className="font-mono text-[9px] text-foreground/40 uppercase tracking-wider mb-1">Why researched</p>
            <p className="text-foreground/60 leading-snug">{whyText}</p>
          </div>
        )}

        {node.hypothesis && (
          <div>
            <p className="font-mono text-[9px] text-foreground/40 uppercase tracking-wider mb-1">Hypothesis</p>
            <p className="text-foreground/60 leading-snug italic">&ldquo;{node.hypothesis}&rdquo;</p>
          </div>
        )}

        {node.answer && (
          <div>
            <p className="font-mono text-[9px] text-foreground/40 uppercase tracking-wider mb-1">Finding</p>
            <p className="text-foreground/80 leading-snug whitespace-pre-wrap">{node.answer}</p>
          </div>
        )}

        {/* Stats footer */}
        <div className="flex items-center gap-3 pt-2 border-t border-foreground/8">
          <span className="text-[9px] font-mono font-semibold px-2 py-0.5 rounded-full bg-foreground/5 text-foreground/50">
            {node.status}
          </span>
          {conf > 0 && (
            <span className="text-[9px] font-mono text-foreground/40">{conf}% confidence</span>
          )}
          {(node.evidence_ids?.length ?? 0) > 0 && (
            <span className="text-[9px] font-mono text-foreground/40">{node.evidence_ids.length} evidence</span>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Main Component ─────────────────────────────────────────── */

function TreeFlow({
  nodes, topicRootId, selectedNodeId, onSelectNode,
}: {
  nodes: Record<string, ResearchNodeData>;
  topicRootId?: string;
  selectedNodeId: string | null;
  onSelectNode: (id: string) => void;
}) {
  const { rfNodes, rfEdges, rootPos } = useMemo(() => {
    const positions = layoutNodes(nodes, topicRootId);
    const rfNodes: Node[] = [];
    const rfEdges: Edge[] = [];
    let rootPos: { x: number; y: number } | null = null;

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

      // Track root position for initial viewport
      if (node.depth === 0) {
        rootPos = { x: pos.x + 150, y: pos.y }; // center of root node (width 300)
      }
    }

    for (const [id, node] of Object.entries(nodes)) {
      if (!node.parent_id || !nodes[node.parent_id]) continue;
      if (node.status === "dead-end") continue;
      if (!positions[node.parent_id]) continue;

      const edgeWidth = node.depth <= 1 ? 2 : node.depth === 2 ? 1.5 : 1;
      rfEdges.push({
        id: `e-${node.parent_id}-${id}`,
        source: node.parent_id,
        target: id,
        type: "smoothstep",
        animated: node.status === "exploring",
        style: {
          stroke: node.status === "exploring" ? EDGE_COLOR_ACTIVE : EDGE_COLOR,
          strokeWidth: edgeWidth,
        },
      });
    }

    return { rfNodes, rfEdges, rootPos };
  }, [nodes, topicRootId, selectedNodeId, onSelectNode]);

  const containerRef = useRef<HTMLDivElement>(null);

  // Use onInit — guaranteed to fire when ReactFlow is ready
  const handleInit = useCallback((instance: ReactFlowInstance) => {
    // Delay to ensure nodes are measured before we position
    setTimeout(() => {
      if (rfNodes.length <= 12) {
        instance.fitView({ padding: 0.2, duration: 400 });
      } else if (rootPos) {
        const containerW = containerRef.current?.clientWidth ?? 800;
        const containerH = containerRef.current?.clientHeight ?? 600;
        // Zoom to show root + depth-1 nodes clearly
        const zoom = 0.65;
        instance.setViewport({
          x: containerW / 2 - rootPos.x * zoom,
          y: containerH * 0.1,
          zoom,
        }, { duration: 400 });
      } else {
        instance.fitView({ padding: 0.15, duration: 400 });
      }
    }, 50);
  }, [rfNodes.length, rootPos]);

  return (
    <div ref={containerRef} style={{ width: "100%", height: "100%" }}>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        onInit={handleInit}
        minZoom={0.05}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        onNodeClick={(_event, node) => onSelectNode(node.id)}
        panOnScroll
        zoomOnScroll
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="rgba(0,0,0,0.04)" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

/* ── Exported Component ─────────────────────────────────────── */

interface DecompositionTreeProps {
  treeData?: ResearchTreeData;
  className?: string;
}

export function DecompositionTree({ treeData, className }: DecompositionTreeProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // Normalize: ensure a single topic root exists, even for old data
  const { nodes, topicRootId } = useMemo(() => {
    if (!treeData?.nodes) return { nodes: {} as Record<string, ResearchNodeData>, topicRootId: undefined };

    const raw = treeData.nodes;
    let trid = treeData.topic_root_id;

    // Check if topic root exists
    if (trid && raw[trid]) {
      return { nodes: raw, topicRootId: trid };
    }

    // Old data: no topic root. Find all orphan nodes (no parent or parent missing).
    const orphans = Object.entries(raw).filter(([, n]) => !n.parent_id || !raw[n.parent_id]);

    if (orphans.length <= 1) {
      // Single root already — just use it
      return { nodes: raw, topicRootId: orphans[0]?.[0] };
    }

    // Synthesize a topic root node and re-parent all orphans under it
    const syntheticId = "__synthetic_topic__";
    const patched: Record<string, ResearchNodeData> = {};

    // Create synthetic topic root
    patched[syntheticId] = {
      id: syntheticId,
      parent_id: null,
      depth: 0,
      query: treeData.sq_to_root
        ? "Research Topic"
        : "Research Topic",
      why_created: "topic_root",
      trigger_finding: "",
      sq_id: null,
      hypothesis: "",
      answer: "",
      confidence: 0,
      status: "complete",
      children_ids: orphans.map(([id]) => id),
      evidence_ids: [],
    };

    // Copy all existing nodes, re-parenting orphans and shifting depths +1
    for (const [id, node] of Object.entries(raw)) {
      const isOrphan = !node.parent_id || !raw[node.parent_id];
      patched[id] = {
        ...node,
        parent_id: isOrphan ? syntheticId : node.parent_id,
        depth: node.depth + 1,
      };
    }

    return { nodes: patched, topicRootId: syntheticId };
  }, [treeData]);

  const liveNodes = Object.values(nodes).filter(n => n.status !== "dead-end");
  const questionCount = liveNodes.filter(n => n.depth === 1).length;
  const partCount = liveNodes.filter(n => n.depth >= 2).length;
  const selectedNode = selectedNodeId ? nodes[selectedNodeId] : null;

  // Fixed height — user pans/zooms to explore large trees
  const containerHeight = 600;

  if (liveNodes.length === 0) return null;

  return (
    <div className={cn("relative rounded-2xl border border-foreground/10 bg-background overflow-hidden", className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-foreground/8 bg-background">
        <div className="flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-foreground/40" />
          <span className="text-xs font-mono font-semibold text-foreground/70">
            Research Decomposition
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-mono text-foreground/40">
            {questionCount} questions · {partCount} parts
          </span>
        </div>
      </div>

      {/* Graph — fixed height, starts centered on root, user pans to explore */}
      <div style={{ height: `${containerHeight}px` }}>
        <ReactFlowProvider>
          <TreeFlow
            nodes={nodes}
            topicRootId={topicRootId}
            selectedNodeId={selectedNodeId}
            onSelectNode={setSelectedNodeId}
          />
        </ReactFlowProvider>
      </div>

      {/* Detail panel */}
      {selectedNode && (
        <NodeDetail node={selectedNode} allNodes={nodes} onClose={() => setSelectedNodeId(null)} />
      )}
    </div>
  );
}
