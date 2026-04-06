"use client";

import { useState } from "react";
import { Handle, Position, useReactFlow, type NodeProps } from "@xyflow/react";
import { PlusIcon } from "@radix-ui/react-icons";

function PlusButton({ onClick }: { onClick: (e: React.MouseEvent) => void }) {
  return (
    <div className="absolute -right-3.5 top-1/2 -translate-y-1/2 z-20 pointer-events-none">
      <button
        onClick={onClick}
        title="Ask a follow-up about this document"
        className="nodrag nopan pointer-events-auto w-7 h-7 rounded-full bg-[#D9FF00] scale-[0.2] hover:scale-100 transition-transform duration-200 ease-out flex items-center justify-center hover:shadow-[0_0_10px_rgba(217,255,0,0.35)] group"
      >
        <PlusIcon className="w-4 h-4 text-[#0C1E2C] opacity-0 group-hover:opacity-100 transition-opacity duration-100 delay-75 shrink-0" />
      </button>
    </div>
  );
}

const PREVIEW_COUNT = 3;

export default function SourceNode({ id, data }: NodeProps) {
  const name     = data.name     as string;
  // Accept either `insights` (array) or legacy `insight` (single string)
  const insights: string[] =
    Array.isArray(data.insights)
      ? (data.insights as string[])
      : typeof data.insight === "string" && data.insight
      ? [data.insight as string]
      : [];
  const topics   = (data.topics  as string[] | undefined) ?? [];
  const url      = data.url      as string | null | undefined;
  const gcs_name = (data.gcs_name as string | undefined) ?? "";

  const [expanded, setExpanded] = useState(false);
  const [copied,   setCopied]   = useState(false);
  const { addNodes, addEdges, getNode } = useReactFlow();

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    const lines = [`Source: ${name}`];
    if (insights.length > 0) {
      lines.push("", "Insights:");
      insights.forEach((ins) => lines.push(`• ${ins}`));
    }
    if (topics.length > 0) {
      lines.push("", `Topics: ${topics.join(", ")}`);
    }
    navigator.clipboard.writeText(lines.join("\n")).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const showReadMore = insights.length > PREVIEW_COUNT;
  const visibleInsights = expanded ? insights : insights.slice(0, PREVIEW_COUNT);

  const handlePlus = (e: React.MouseEvent) => {
    e.stopPropagation();
    const thisNode = getNode(id);
    if (!thisNode) return;
    const nodeWidth = (thisNode.measured?.width as number | undefined) ?? 220;
    const newId = `followup-${Date.now()}`;
    addNodes([{
      id: newId,
      type: "followUpNode",
      position: { x: thisNode.position.x + nodeWidth + 40, y: thisNode.position.y },
      data: { gcs_name, docName: name, state: "idle" },
      style: { background: "transparent", border: "none", padding: 0 },
      draggable: true,
    }]);
    addEdges([{
      id: `e-${id}-${newId}`,
      source: id,
      sourceHandle: "right",
      target: newId,
      type: "default",
      style: { stroke: "#D9FF00", strokeWidth: 1.5, opacity: 0.5 },
    }]);
  };

  return (
    // Outer wrapper: overflow-visible so PlusButton is not clipped
    <div className="relative" style={{ width: 220 }}>

      {/* Card — no overflow-hidden so button can escape the boundary */}
      <div className="bg-[#1A2B38] border border-[#243340] rounded-xl shadow-lg shadow-black/40">

        {/* ── Source label + name ── */}
        <div className="px-3.5 pt-3 pb-2.5">
          <div className="text-[9px] font-bold text-[#4A6070] uppercase tracking-[0.12em] mb-1.5">
            Source
          </div>
          <p className="text-[#e0eaf0] text-[11px] font-semibold leading-snug line-clamp-2">
            {name}
          </p>
        </div>

        {/* ── Insights list ── */}
        {insights.length > 0 && (
          <div className="px-3.5 py-2.5 border-t border-[#1E3040]">
            <div className="text-[9px] font-bold text-[#3A6A82] uppercase tracking-[0.12em] mb-1.5">
              Insights
            </div>
            <ul className="space-y-1.5">
              {visibleInsights.map((insight, i) => (
                <li key={i} className="flex gap-1.5 items-start">
                  <span className="text-[#3A6A82] text-[9px] mt-[2px] shrink-0">•</span>
                  <span className="text-[#7AAFC0] text-[10px] leading-snug">{insight}</span>
                </li>
              ))}
            </ul>
            {showReadMore && (
              <button
                onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }}
                className="nodrag nopan mt-2 text-[9px] font-medium text-[#D9FF00]/60 hover:text-[#D9FF00] transition-colors"
              >
                {expanded ? "Show less ↑" : `Read more  +${insights.length - PREVIEW_COUNT}`}
              </button>
            )}
          </div>
        )}

        {/* ── Topic tags ── */}
        {topics.length > 0 && (
          <div className="px-3.5 py-2.5 border-t border-[#1E3040]">
            <div className="flex flex-wrap gap-1">
              {topics.map((t, i) => (
                <span
                  key={i}
                  className="text-[9px] text-[#3D6070] bg-[#111E28] border border-[#1A2D3A] px-2 py-0.5 rounded-full leading-none"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* ── Copy button ── */}
        <div className="px-3.5 py-2 border-t border-[#1E3040]">
          <button
            onClick={handleCopy}
            className="nodrag nopan w-full flex items-center justify-center gap-1.5 text-[9px] text-[#324550] hover:text-[#7B92A5] border border-[#1A2D3A] hover:border-[#243340] rounded-lg py-1.5 transition-colors"
          >
            {copied ? (
              <>
                <svg className="w-2.5 h-2.5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
                <span className="text-green-500">Copied</span>
              </>
            ) : (
              <>
                <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                </svg>
                <span>Copy insights</span>
              </>
            )}
          </button>
        </div>

        {/* ── PDF link ── */}
        <div className="px-3.5 py-2.5 border-t border-[#1E3040]">
          {url ? (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="nodrag nopan inline-flex items-center gap-1 bg-[#D9FF00]/10 hover:bg-[#D9FF00]/20 border border-[#D9FF00]/30 text-[#D9FF00] text-[9px] font-semibold px-2 py-0.5 rounded-full transition-colors leading-none"
            >
              <svg className="w-2.5 h-2.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
              View PDF
            </a>
          ) : (
            <span className="text-[9px] text-[#324550] border border-[#243340] px-2 py-0.5 rounded-full leading-none">
              No link
            </span>
          )}
        </div>
      </div>

      {/* + button — outside the card, overlays on the right edge */}
      <PlusButton onClick={handlePlus} />

      <Handle type="target" position={Position.Top}    style={{ width: 5, height: 5, background: "#4A6070", border: "none" }} />
      <Handle type="target" position={Position.Left}   style={{ width: 5, height: 5, background: "#4A6070", border: "none" }} />
      <Handle type="source" position={Position.Bottom} style={{ width: 5, height: 5, background: "#4A6070", border: "none" }} />
      <Handle type="source" id="right" position={Position.Right} style={{ width: 5, height: 5, background: "#4A6070", border: "none" }} />
    </div>
  );
}
