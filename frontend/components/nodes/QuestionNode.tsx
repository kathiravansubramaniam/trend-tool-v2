"use client";

import { Handle, Position, useReactFlow, type NodeProps } from "@xyflow/react";
import { PlusIcon } from "@radix-ui/react-icons";

const NODE_STYLE = { background: "transparent", border: "none", padding: 0 };

function PlusButton({ onClick }: { onClick: (e: React.MouseEvent) => void }) {
  return (
    <div className="absolute -right-3.5 top-1/2 -translate-y-1/2 z-20 pointer-events-none">
      <button
        onClick={onClick}
        title="Ask a follow-up"
        className="nodrag nopan pointer-events-auto w-7 h-7 rounded-full bg-[#D9FF00] scale-[0.2] hover:scale-100 transition-transform duration-200 ease-out flex items-center justify-center hover:shadow-[0_0_10px_rgba(217,255,0,0.35)] group"
      >
        <PlusIcon className="w-4 h-4 text-[#0C1E2C] opacity-0 group-hover:opacity-100 transition-opacity duration-100 delay-75 shrink-0" />
      </button>
    </div>
  );
}

export default function QuestionNode({ id, data }: NodeProps) {
  const label = data.label as string;

  const { addNodes, addEdges, getNode } = useReactFlow();

  const handlePlus = (e: React.MouseEvent) => {
    e.stopPropagation();
    const thisNode = getNode(id);
    if (!thisNode) return;
    const newId = `followup-${Date.now()}`;
    addNodes([{
      id: newId,
      type: "followUpNode",
      position: { x: thisNode.position.x + 310, y: thisNode.position.y },
      data: { gcs_name: "", docName: label.slice(0, 60), state: "idle" },
      style: NODE_STYLE,
      draggable: true,
    }]);
    addEdges([{
      id: `e-${id}-${newId}`,
      source: id,
      target: newId,
      type: "default",
      style: { stroke: "#D9FF00", strokeWidth: 1.5, opacity: 0.5 },
    }]);
  };

  return (
    <div
      style={{ width: 265 }}
      className="relative bg-[#0F1A22] border-2 border-[#D9FF00] rounded-2xl px-4 py-3.5 shadow-xl shadow-black/50"
    >
      <div className="text-[9px] font-bold text-[#D9FF00] uppercase tracking-[0.15em] mb-1.5 flex items-center gap-1.5">
        <svg className="w-2.5 h-2.5 shrink-0" fill="currentColor" viewBox="0 0 20 20">
          <circle cx="10" cy="10" r="4" />
        </svg>
        Query
      </div>
      <p className="text-[#e8e8e8] text-[11px] leading-snug font-semibold">{label}</p>

      <PlusButton onClick={handlePlus} />

      <Handle type="source" position={Position.Top}    style={{ width: 6, height: 6, background: "#D9FF00", border: "none" }} />
      <Handle type="source" position={Position.Right}  style={{ width: 6, height: 6, background: "#D9FF00", border: "none" }} />
      <Handle id="bottom" type="source" position={Position.Bottom} style={{ width: 6, height: 6, background: "#D9FF00", border: "none" }} />
      <Handle type="source" position={Position.Left}   style={{ width: 6, height: 6, background: "#D9FF00", border: "none" }} />
    </div>
  );
}
