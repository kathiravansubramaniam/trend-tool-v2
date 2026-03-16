"use client";

import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";

export default function TopicNode({ data }: NodeProps) {
  const label = data.label as string;
  return (
    <div className="bg-[#151F2A] border border-[#1E3040] rounded-full px-3 py-1.5 shadow-sm">
      <p className="text-[#6B8FA5] text-[10px] leading-none whitespace-nowrap max-w-[150px] truncate">
        {label}
      </p>
      <Handle type="target" position={Position.Left}  style={{ width: 4, height: 4, background: "#1E3040", border: "none" }} />
      <Handle type="source" position={Position.Right} style={{ width: 4, height: 4, background: "#1E3040", border: "none" }} />
    </div>
  );
}
