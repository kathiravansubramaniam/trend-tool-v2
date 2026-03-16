"use client";

import { useEffect, useRef, useState } from "react";
import { Handle, Position, useReactFlow, type NodeProps } from "@xyflow/react";
import { PlusIcon } from "@radix-ui/react-icons";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const NODE_STYLE = { background: "transparent", border: "none", padding: 0 };

type NodeState = "idle" | "loading" | "answered";

function PlusButton({ onClick }: { onClick: (e: React.MouseEvent) => void }) {
  return (
    <div className="absolute -right-3.5 top-1/2 -translate-y-1/2 z-10">
      <button
        onClick={onClick}
        title="Chain another question"
        className="nodrag nopan w-7 h-7 rounded-full bg-[#D9FF00] scale-[0.2] hover:scale-100 transition-transform duration-200 ease-out flex items-center justify-center overflow-hidden hover:shadow-[0_0_10px_rgba(217,255,0,0.35)] group"
      >
        <PlusIcon className="w-4 h-4 text-[#0C1E2C] opacity-0 group-hover:opacity-100 transition-opacity duration-100 delay-75 shrink-0" />
      </button>
    </div>
  );
}

export default function FollowUpNode({ id, data }: NodeProps) {
  const gcs_name = (data.gcs_name as string | undefined) ?? "";
  const docName  = (data.docName  as string | undefined) ?? "this document";

  const [nodeState, setNodeState] = useState<NodeState>((data.state as NodeState | undefined) ?? "idle");
  const [question,  setQuestion]  = useState((data.question as string | undefined) ?? "");
  const [answer,    setAnswer]    = useState((data.answer   as string | undefined) ?? "");
  const [expanded,  setExpanded]  = useState(false);

  const cardRef = useRef<HTMLDivElement>(null);
  const { addNodes, addEdges, getNode, updateNodeData } = useReactFlow();

  // Collapse on outside click when expanded
  useEffect(() => {
    if (!expanded) return;
    const handler = (e: MouseEvent) => {
      if (cardRef.current && !cardRef.current.contains(e.target as Node)) {
        setExpanded(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [expanded]);

  const handleSubmit = async () => {
    const q = question.trim();
    if (!q || nodeState === "loading") return;
    setNodeState("loading");

    try {
      const body: Record<string, unknown> = { question: q, max_docs: 1 };
      if (gcs_name) body.pinned_gcs_names = [gcs_name];

      const res = await fetch(`${API}/api/query-stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error("API error");

      const reader  = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer    = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const event = JSON.parse(line.slice(6));
          if (event.type === "answer") {
            const ans = event.answer as string;
            setAnswer(ans);
            setNodeState("answered");
            updateNodeData(id, { gcs_name, docName, state: "answered", question: q, answer: ans });
          }
        }
      }
    } catch {
      setAnswer("Something went wrong. Make sure the API is running.");
      setNodeState("answered");
    }
  };

  const handlePlus = (e: React.MouseEvent) => {
    e.stopPropagation();
    const thisNode = getNode(id);
    if (!thisNode) return;
    const newId = `followup-${Date.now()}`;
    addNodes([{
      id: newId,
      type: "followUpNode",
      position: { x: thisNode.position.x + 340, y: thisNode.position.y },
      data: { gcs_name, docName, state: "idle" },
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

  // Truncate threshold: approx 400 chars before we show See more
  const TRUNCATE_AT = 400;
  const isLong = answer.length > TRUNCATE_AT;

  return (
    <div
      ref={cardRef}
      style={{ width: 290 }}
      className="relative bg-[#0C1E2C] border border-[#D9FF00]/25 rounded-xl px-4 py-3.5 shadow-xl shadow-black/60"
    >
      <Handle type="target" position={Position.Left} style={{ width: 5, height: 5, background: "#D9FF00", border: "none" }} />

      {/* Header */}
      <div className="text-[9px] font-bold text-[#D9FF00] uppercase tracking-[0.15em] mb-0.5">
        Ask about
      </div>
      <p className="text-[#4A6878] text-[10px] font-medium mb-3 truncate" title={docName}>
        {docName}
      </p>

      {/* ── Idle ── */}
      {nodeState === "idle" && (
        <>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(); }
            }}
            placeholder="Ask a question about this document…"
            rows={2}
            className="nodrag nopan w-full bg-[#152230] border border-[#243340] focus:border-[#D9FF00]/40 text-[#e8e8e8] text-[11px] rounded-lg px-2.5 py-2 resize-none focus:outline-none placeholder-[#2A4050] transition-colors"
          />
          <button
            onClick={handleSubmit}
            disabled={!question.trim()}
            className="nodrag nopan mt-2 w-full bg-[#D9FF00] hover:bg-[#E8FF4D] disabled:opacity-25 disabled:cursor-not-allowed text-[#0C1E2C] text-[11px] font-bold py-1.5 rounded-lg transition-colors active:scale-[0.98]"
          >
            Ask
          </button>
        </>
      )}

      {/* ── Loading ── */}
      {nodeState === "loading" && (
        <div className="flex items-start gap-2 py-1">
          <svg className="w-3.5 h-3.5 text-[#D9FF00] animate-spin shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
            <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
          <p className="text-[#7B92A5] text-[10px] leading-relaxed italic">"{question}"</p>
        </div>
      )}

      {/* ── Answered ── */}
      {nodeState === "answered" && (
        <>
          <p className="text-[#3A5568] text-[9px] font-semibold uppercase tracking-wide mb-1">Q</p>
          <p className="text-[#7B92A5] text-[10px] italic mb-2.5 leading-snug">"{question}"</p>

          <p className={`text-[#b8d0e0] text-[11px] leading-relaxed ${expanded ? "" : "line-clamp-6"}`}>
            {answer}
          </p>

          {isLong && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="nodrag nopan mt-1.5 text-[10px] text-[#D9FF00]/60 hover:text-[#D9FF00] transition-colors"
            >
              {expanded ? "See less ↑" : "See more ↓"}
            </button>
          )}

          <PlusButton onClick={handlePlus} />
        </>
      )}

      <Handle type="source" position={Position.Right} style={{ width: 5, height: 5, background: "#D9FF00", border: "none" }} />
    </div>
  );
}
