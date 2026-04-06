"use client";

import { useCallback, useEffect } from "react";
import {
  ReactFlow,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import QuestionNode from "./nodes/QuestionNode";
import SourceNode   from "./nodes/SourceNode";
import FollowUpNode from "./nodes/FollowUpNode";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ClusterSource {
  name: string;
  industry: string;
  topics: string[];
  url?: string | null;
  gcs_name: string;
  insights: string[];
}

export interface ClusterData {
  id: string;
  question: string;
  parentClusterId?: string;
  sources: ClusterSource[];
}

// ─── Layout constants ─────────────────────────────────────────────────────────
const CLUSTER_COLS = 2;
const CLUSTER_W    = 1400;
const CLUSTER_H    = 1100;
const NODE_STYLE   = { background: "transparent", border: "none", padding: 0 };

function buildCluster(
  clusterIdx: number,
  cluster: ClusterData
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  const col = clusterIdx % CLUSTER_COLS;
  const row = Math.floor(clusterIdx / CLUSTER_COLS);
  const cx  = col * CLUSTER_W + 700;
  const cy  = row * CLUSTER_H + 540;

  // ── Question + insights combined node (center) ────────────────────────────
  const qId = `q-${cluster.id}`;
  nodes.push({
    id: qId,
    type: "questionNode",
    position: { x: cx - 132, y: cy - 90 },   // centered (~265px wide, variable height)
    data: { label: cluster.question },
    style: NODE_STYLE,
    draggable: true,
  });

  // ── Source nodes — arc around the center ─────────────────────────────────
  const sources  = cluster.sources.filter(s => s.insights.length > 0).slice(0, 8);
  const sourceR  = 370;
  const arcStart = Math.PI * 0.1;    // ~18° — right side, just below top
  const arcEnd   = Math.PI * 1.9;    // ~342° — almost full circle
  sources.forEach((src, i) => {
    const total = Math.max(sources.length, 1);
    const angle =
      sources.length === 1
        ? Math.PI / 2
        : arcStart + (i / (total - 1)) * (arcEnd - arcStart);

    const sx = cx + sourceR * Math.cos(angle);
    const sy = cy + sourceR * Math.sin(angle);
    const srcId = `src-${cluster.id}-${i}`;

    nodes.push({
      id: srcId,
      type: "sourceNode",
      position: { x: sx - 107, y: sy - 55 },
      data: {
        name:     src.name,
        industry: src.industry,
        topics:   src.topics,
        url:      src.url ?? null,
        gcs_name: src.gcs_name,
        insights: src.insights,
      },
      style: NODE_STYLE,
      draggable: true,
    });
    edges.push({
      id: `e-q-src-${cluster.id}-${i}`,
      source: qId,
      sourceHandle: "bottom",
      target: srcId,
      type: "default",
      style: { stroke: "#2A4A5A", strokeWidth: 1.5, opacity: 0.8 },
    });
  });

  return { nodes, edges };
}

// ─── Storage keys ─────────────────────────────────────────────────────────────
const POS_KEY = "trend-mindmap-positions-v1";

// ─── Node types registry ──────────────────────────────────────────────────────
const nodeTypes = {
  questionNode: QuestionNode,
  sourceNode:   SourceNode,
  followUpNode: FollowUpNode,
};

// ─── Component ────────────────────────────────────────────────────────────────

interface MindMapProps {
  clusters: ClusterData[];
  onClear: () => void;
}

export default function MindMap({ clusters, onClear }: MindMapProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  // Rebuild graph whenever clusters change, restoring saved drag positions
  useEffect(() => {
    const saved: Record<string, { x: number; y: number }> = JSON.parse(
      localStorage.getItem(POS_KEY) ?? "{}"
    );
    const allNodes: Node[] = [];
    const allEdges: Edge[] = [];
    clusters.forEach((cluster, idx) => {
      const { nodes: cn, edges: ce } = buildCluster(idx, cluster);
      cn.forEach((n) => {
        if (saved[n.id]) n.position = saved[n.id];
      });
      allNodes.push(...cn);
      allEdges.push(...ce);
    });

    // Add cross-cluster edges: parent question → child question
    clusters.forEach((cluster) => {
      if (cluster.parentClusterId) {
        allEdges.push({
          id: `e-cross-${cluster.parentClusterId}-${cluster.id}`,
          source: `q-${cluster.parentClusterId}`,
          target: `q-${cluster.id}`,
          type: "default",
          style: { stroke: "#D9FF00", strokeWidth: 1, opacity: 0.35, strokeDasharray: "6 3" },
        });
      }
    });

    setNodes(allNodes);
    setEdges(allEdges);
  }, [clusters, setNodes, setEdges]);

  // Persist drag positions on node drag stop
  const handleNodeDragStop = useCallback((_: React.MouseEvent, node: Node) => {
    const saved: Record<string, { x: number; y: number }> = JSON.parse(
      localStorage.getItem(POS_KEY) ?? "{}"
    );
    saved[node.id] = node.position;
    localStorage.setItem(POS_KEY, JSON.stringify(saved));
  }, []);

  const handleNodesChange = useCallback(
    (changes: NodeChange<Node>[]) => onNodesChange(changes),
    [onNodesChange]
  );

  const handleResetLayout = () => {
    localStorage.removeItem(POS_KEY);
    const allNodes: Node[] = [];
    const allEdges: Edge[] = [];
    clusters.forEach((cluster, idx) => {
      const { nodes: cn, edges: ce } = buildCluster(idx, cluster);
      allNodes.push(...cn);
      allEdges.push(...ce);
    });
    clusters.forEach((cluster) => {
      if (cluster.parentClusterId) {
        allEdges.push({
          id: `e-cross-${cluster.parentClusterId}-${cluster.id}`,
          source: `q-${cluster.parentClusterId}`,
          target: `q-${cluster.id}`,
          type: "default",
          style: { stroke: "#D9FF00", strokeWidth: 1, opacity: 0.35, strokeDasharray: "6 3" },
        });
      }
    });
    setNodes(allNodes);
    setEdges(allEdges);
  };

  // ── Empty state ─────────────────────────────────────────────────────────────
  if (clusters.length === 0) {
    return (
      <div className="w-full h-full bg-[#0D1820] flex flex-col items-center justify-center gap-4 text-center px-6">
        <div className="w-14 h-14 rounded-2xl bg-[#D9FF00]/10 border border-[#D9FF00]/20 flex items-center justify-center">
          <svg className="w-7 h-7 text-[#D9FF00]/50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <circle cx="12" cy="12" r="3" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2m0 14v2M3 12h2m14 0h2m-3.22-6.78-1.42 1.42M6.64 17.36l-1.42 1.42M17.36 17.36l-1.42-1.42M6.64 6.64 5.22 5.22" />
          </svg>
        </div>
        <div>
          <p className="text-[#e8e8e8] font-medium text-sm">No map yet</p>
          <p className="text-[#4A6070] text-xs mt-1 max-w-xs leading-relaxed">
            Ask a question in Chat and your trend insights will appear here as an interactive mind map.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full h-full relative bg-[#0D1820]">
      {/* Toolbar */}
      <div className="absolute top-3 right-3 z-10 flex items-center gap-2">
        <button
          onClick={handleResetLayout}
          className="flex items-center gap-1.5 text-[11px] text-[#7B92A5] hover:text-[#e8e8e8] bg-[#1C2B36] border border-[#243340] hover:border-[#3A5568] px-2.5 py-1.5 rounded-lg transition-colors"
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Reset layout
        </button>
        <button
          onClick={onClear}
          className="flex items-center gap-1.5 text-[11px] text-[#7B92A5] hover:text-red-400 bg-[#1C2B36] border border-[#243340] hover:border-red-900 px-2.5 py-1.5 rounded-lg transition-colors"
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
          Clear map
        </button>
      </div>

      {/* Legend */}
      <div className="absolute bottom-16 left-3 z-10 flex flex-col gap-1.5 bg-[#1C2B36]/80 backdrop-blur-sm border border-[#243340] rounded-xl px-3 py-2.5">
        {[
          { color: "#D9FF00", label: "Query" },
          { color: "#3A5568", label: "Source" },
          { color: "#D9FF00", label: "Follow-up (via +)", border: true },
        ].map(({ color, label, border }) => (
          <div key={label} className="flex items-center gap-2">
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{
                background: border ? "transparent" : color,
                border: border ? `1.5px solid ${color}` : undefined,
              }}
            />
            <span className="text-[10px] text-[#7B92A5]">{label}</span>
          </div>
        ))}
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={handleNodeDragStop}
        nodeTypes={nodeTypes}
        nodesConnectable={false}
        proOptions={{ hideAttribution: true }}
        fitView
        fitViewOptions={{ padding: 0.12, maxZoom: 0.85 }}
        minZoom={0.05}
        maxZoom={2.5}
        defaultEdgeOptions={{ type: "default" }}
        style={{ background: "#0D1820" }}
      >
        <Background color="#162230" gap={28} size={1} style={{ backgroundColor: "#0D1820" }} />
        <MiniMap
          style={{ background: "#0D1820", border: "1px solid #243340", borderRadius: 8 }}
          nodeColor={(n) => {
            if (n.type === "questionNode") return "#D9FF00";
            if (n.type === "sourceNode")   return "#2A3D4A";
            if (n.type === "followUpNode") return "#162230";
            return "#151F2A";
          }}
          maskColor="rgba(0,0,0,0.35)"
        />
      </ReactFlow>
    </div>
  );
}
