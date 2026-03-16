"use client";

import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";

export default function InsightNode({ data }: NodeProps) {
  const label = data.label as string;
  return (
    <div
      style={{ width: 215 }}
      className="bg-[#162230] border border-[#2A4A62] rounded-xl px-3.5 py-3 shadow-lg shadow-black/40"
    >
      <div className="text-[9px] font-bold text-[#4E8FAD] uppercase tracking-[0.12em] mb-1.5">
        Insight
      </div>
      <p className="text-[#b8d0e0] text-[11px] leading-relaxed line-clamp-5">{label}</p>
      <Handle type="target" position={Position.Left}  style={{ width: 5, height: 5, background: "#2A4A62", border: "none" }} />
      <Handle type="source" position={Position.Right} style={{ width: 5, height: 5, background: "#2A4A62", border: "none" }} />
    </div>
  );
}
