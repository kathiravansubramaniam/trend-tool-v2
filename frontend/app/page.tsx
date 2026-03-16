"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import Message from "../components/Message";
import { type ClusterData, type ClusterSource } from "../components/MindMap";

// Dynamically import MindMap to avoid SSR issues with React Flow
const MindMap = dynamic(() => import("../components/MindMap"), { ssr: false });

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const MAP_CLUSTERS_KEY = "trend-mindmap-clusters-v1";

interface Source {
  gcs_name: string;
  name: string;
  industry: string;
  topics: string[];
  url?: string | null;
}

interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  context_id?: string | null;
  elapsed?: number;
}

interface Industry {
  name: string;
  count: number;
}

let msgIdCounter = 0;

export default function Home() {
  // ── View ──────────────────────────────────────────────────────────────────
  const [activeView, setActiveView] = useState<"chat" | "map">("chat");

  // ── Chat state ────────────────────────────────────────────────────────────
  const [messages, setMessages]             = useState<ChatMessage[]>([]);
  const [input, setInput]                   = useState("");
  const [loading, setLoading]               = useState(false);
  const [elapsed, setElapsed]               = useState(0);
  const timerRef                            = useRef<ReturnType<typeof setInterval> | null>(null);
  const elapsedRef                          = useRef(0);
  const [industries, setIndustries]         = useState<Industry[]>([]);
  const [selectedIndustries, setSelectedIndustries] = useState<string[]>([]);
  const [showPicker, setShowPicker]         = useState(false);
  const [followUpMsgId, setFollowUpMsgId]   = useState<number | null>(null);
  const [followUpSources, setFollowUpSources]       = useState<Source[]>([]);
  const [followUpContextId, setFollowUpContextId]   = useState<string | null>(null);
  const [loadingPhase, setLoadingPhase]     = useState<"searching" | "loading" | "answering" | null>(null);
  const [loadingDocs, setLoadingDocs]       = useState<{ name: string; industry: string; done: boolean }[]>([]);
  const [loadingTotal, setLoadingTotal]     = useState(0);
  const bottomRef                           = useRef<HTMLDivElement>(null);
  const textareaRef                         = useRef<HTMLTextAreaElement>(null);
  const pickerRef                           = useRef<HTMLDivElement>(null);

  // ── Map state ─────────────────────────────────────────────────────────────
  const [mapClusters, setMapClusters] = useState<ClusterData[]>([]);

  // ── Bootstrap ─────────────────────────────────────────────────────────────
  useEffect(() => {
    fetch(`${API}/api/industries`).then((r) => r.json()).then(setIndustries).catch(() => {});
    // Restore saved map clusters
    try {
      const saved = localStorage.getItem(MAP_CLUSTERS_KEY);
      if (saved) setMapClusters(JSON.parse(saved));
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) setShowPicker(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // ── Helpers ───────────────────────────────────────────────────────────────
  const toggleIndustry = (name: string) =>
    setSelectedIndustries((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]
    );

  const filterLabel =
    selectedIndustries.length === 0
      ? "All Industries"
      : selectedIndustries.length === 1
      ? selectedIndustries[0]
      : `${selectedIndustries.length} industries`;

  const handleFollowUp = (msgId: number, sources: Source[], contextId: string | null) => {
    if (sources.length === 0) {
      setFollowUpMsgId(null); setFollowUpSources([]); setFollowUpContextId(null);
    } else {
      setFollowUpMsgId(msgId); setFollowUpSources(sources); setFollowUpContextId(contextId ?? null);
      textareaRef.current?.focus();
    }
  };

  const addCluster = useCallback(
    (question: string, sources: Source[], sourceInsights: Record<string, string[]>) => {
      const cluster: ClusterData = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        question,
        sources: sources.map((s): ClusterSource => ({
          name: s.name,
          industry: s.industry,
          topics: s.topics,
          url: s.url ?? null,
          gcs_name: s.gcs_name,
          insights: sourceInsights[s.name] ?? [],
        })),
      };
      setMapClusters((prev) => {
        const updated = [...prev, cluster];
        localStorage.setItem(MAP_CLUSTERS_KEY, JSON.stringify(updated));
        return updated;
      });
    },
    []
  );

  const handleClearMap = () => {
    setMapClusters([]);
    localStorage.removeItem(MAP_CLUSTERS_KEY);
    localStorage.removeItem("trend-mindmap-positions-v1");
  };

  // ── Send message ──────────────────────────────────────────────────────────
  const handleSend = async () => {
    const q = input.trim();
    if (!q || loading) return;

    setMessages((prev) => [...prev, { id: ++msgIdCounter, role: "user", content: q }]);
    setInput("");
    setLoading(true); setLoadingPhase("searching"); setLoadingDocs([]); setLoadingTotal(0);

    // ── Validate query with LLM before running full search ──────────────────
    try {
      const vRes = await fetch(`${API}/api/validate-query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });
      if (vRes.ok) {
        const v = await vRes.json();
        if (!v.valid) {
          setMessages((prev) => [
            ...prev,
            {
              id: ++msgIdCounter,
              role: "assistant",
              content: v.message
                ? `${v.message} Try asking something like *"What are the biggest consumer trends for 2026?"*`
                : "That doesn't look like a trend research question. Try asking something like *\"What are the biggest consumer trends for 2026?\"*",
            },
          ]);
          setLoading(false); setLoadingPhase(null);
          return;
        }
      }
    } catch { /* fail open — proceed with query */ }

    setElapsed(0); elapsedRef.current = 0;
    timerRef.current = setInterval(() => setElapsed((s) => { elapsedRef.current = s + 1; return s + 1; }), 1000);

    try {
      const body: Record<string, unknown> = { question: q };
      if (followUpSources.length > 0 && followUpContextId) {
        body.context_id = followUpContextId;
      } else if (followUpSources.length > 0) {
        body.pinned_gcs_names = followUpSources.map((s) => s.gcs_name);
      } else {
        body.industry_filter = selectedIndustries.length > 0 ? selectedIndustries : null;
      }

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
          if (event.type === "searching") {
            setLoadingPhase("searching");
          } else if (event.type === "found") {
            setLoadingTotal(event.total); setLoadingPhase("loading");
          } else if (event.type === "loading") {
            setLoadingDocs((prev) => [
              ...prev.map((d, i) => i === prev.length - 1 ? { ...d, done: true } : d),
              { ...event.doc, done: false },
            ]);
          } else if (event.type === "answering") {
            setLoadingPhase("answering");
            setLoadingDocs((prev) => prev.map((d) => ({ ...d, done: true })));
          } else if (event.type === "answer") {
            setMessages((prev) => [
              ...prev,
              {
                id: ++msgIdCounter,
                role: "assistant",
                content: event.answer,
                sources: event.sources,
                context_id: event.context_id,
                elapsed: elapsedRef.current,
              },
            ]);
            // ── Add cluster to mind map ──────────────────────────────────
            if (event.sources?.length > 0) {
              addCluster(q, event.sources, event.source_insights ?? {});
            }
          } else if (event.type === "error") {
            throw new Error(event.message);
          }
        }
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { id: ++msgIdCounter, role: "assistant", content: "Something went wrong. Make sure the API is running (`make api`)." },
      ]);
    } finally {
      if (timerRef.current) clearInterval(timerRef.current);
      setLoading(false); setLoadingPhase(null); setLoadingDocs([]); setLoadingTotal(0);
      textareaRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-screen bg-[#151F27]">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <header className="px-6 py-4 border-b border-[#243340] bg-[#151F27] shrink-0">
        <div className="flex items-center justify-between max-w-2xl mx-auto">
          {/* ASCII art title */}
          <div className="shrink-0 min-w-0 overflow-hidden">
            <pre
              className="font-mono text-[#D9FF00] leading-[1.15] select-none"
              style={{ fontSize: "clamp(2px, 0.45vw, 4px)" }}
            >{`████████╗██████╗ ███████╗███╗   ██╗██████╗ ███████╗\n   ██╔══╝██╔══██╗██╔════╝████╗  ██║██╔══██╗██╔════╝\n   ██║   ██████╔╝█████╗  ██╔██╗ ██║██║  ██║███████╗\n   ██║   ██╔══██╗██╔══╝  ██║╚██╗██║██║  ██║╚════██║\n   ██║   ██║  ██║███████╗██║ ╚████║██████╔╝███████║\n   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝╚═════╝╚══════╝`}</pre>
          </div>

          {/* Tab switcher */}
          <div className="flex items-center bg-[#1C2B36] border border-[#243340] rounded-xl p-1 gap-0.5">
            <button
              onClick={() => setActiveView("chat")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                activeView === "chat"
                  ? "bg-[#243340] text-[#e8e8e8]"
                  : "text-[#7B92A5] hover:text-[#e8e8e8]"
              }`}
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              Chat
            </button>
            <button
              onClick={() => setActiveView("map")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                activeView === "map"
                  ? "bg-[#243340] text-[#e8e8e8]"
                  : "text-[#7B92A5] hover:text-[#e8e8e8]"
              }`}
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <circle cx="6" cy="12" r="2" />
                <circle cx="18" cy="6" r="2" />
                <circle cx="18" cy="18" r="2" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h8M8 12L16 6M8 12l8 6" />
              </svg>
              Map
              {mapClusters.length > 0 && (
                <span className="bg-[#D9FF00]/20 text-[#D9FF00] text-[10px] font-bold px-1.5 py-0.5 rounded-full leading-none">
                  {mapClusters.length}
                </span>
              )}
            </button>
          </div>

        </div>
      </header>

      {/* ── Map view ─────────────────────────────────────────────────────── */}
      {activeView === "map" && (
        <div className="flex-1 overflow-hidden">
          <MindMap clusters={mapClusters} onClear={handleClearMap} />
        </div>
      )}

      {/* ── Chat view ────────────────────────────────────────────────────── */}
      {activeView === "chat" && (
        <>
          <main className="flex-1 overflow-y-auto px-6 py-6 scrollbar-thin">
            <div className="max-w-2xl mx-auto h-full flex flex-col">
              {messages.length === 0 && (
                <div className="flex flex-col items-center justify-center h-full text-center gap-4">
                  <pre
                    className="font-mono text-[#1C2B36] leading-[1.15] select-none"
                    style={{ fontSize: "clamp(6px, 2vw, 14px)" }}
                  >{`████████╗██████╗ ███████╗███╗   ██╗██████╗ ███████╗\n   ██╔══╝██╔══██╗██╔════╝████╗  ██║██╔══██╗██╔════╝\n   ██║   ██████╔╝█████╗  ██╔██╗ ██║██║  ██║███████╗\n   ██║   ██╔══██╗██╔══╝  ██║╚██╗██║██║  ██║╚════██║\n   ██║   ██║  ██║███████╗██║ ╚████║██████╔╝███████║\n   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝╚═════╝╚══════╝`}</pre>
                  <p className="text-[#1C2B36] text-sm max-w-xs leading-relaxed">
                    Ask anything about trends and get answers from the latest trend reports
                  </p>
                </div>
              )}

              {messages.map((msg) => (
                <Message
                  key={msg.id}
                  role={msg.role}
                  content={msg.content}
                  sources={msg.sources}
                  elapsed={msg.elapsed}
                />
              ))}

              {loading && (
                <div className="flex items-start mb-6">
                  <div className="bg-[#1C2B36] border border-[#243340] rounded-2xl rounded-bl-sm px-4 py-3 w-full max-w-[80%]">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="w-1.5 h-1.5 bg-[#D9FF00] rounded-full animate-pulse" />
                        <span className="text-xs text-[#7B92A5]">
                          {loadingPhase === "searching"  && "Searching reports…"}
                          {loadingPhase === "loading"    && `Loading documents… (${loadingDocs.length}/${loadingTotal})`}
                          {loadingPhase === "answering"  && "Synthesizing answer…"}
                          {!loadingPhase                 && "Working…"}
                        </span>
                      </div>
                      <span className="text-xs text-[#4A6070] tabular-nums">{elapsed}s</span>
                    </div>
                    {loadingPhase === "loading" && loadingTotal > 0 && (
                      <div className="h-1 w-full bg-[#243340] rounded-full mb-2 overflow-hidden">
                        <div
                          className="h-full bg-[#D9FF00] rounded-full transition-all duration-300"
                          style={{ width: `${Math.round((loadingDocs.length / loadingTotal) * 100)}%` }}
                        />
                      </div>
                    )}
                    {loadingDocs.length > 0 && (
                      <ul className="space-y-1.5 mt-1">
                        {loadingDocs.map((doc, i) => (
                          <li key={i} className={`flex items-center gap-1.5 text-xs ${doc.done ? "text-[#7B92A5]" : "text-[#e8e8e8]"}`}>
                            {doc.done ? (
                              <svg className="w-3 h-3 text-[#D9FF00] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                              </svg>
                            ) : (
                              <svg className="w-3 h-3 text-[#D9FF00] shrink-0 animate-spin" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                              </svg>
                            )}
                            <span className="truncate">{doc.name}</span>
                            {doc.industry && <span className={`shrink-0 ${doc.done ? "text-[#4A6070]" : "text-[#7B92A5]"}`}>· {doc.industry}</span>}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          </main>

          <footer className="px-6 py-4 bg-[#151F27] shrink-0">
            {/* Follow-up toggle */}
            {(() => {
              const lastSourcedMsg = [...messages].reverse().find(m => m.role === "assistant" && m.sources && m.sources.length > 0);
              if (!lastSourcedMsg) return null;
              const isActive = followUpMsgId === lastSourcedMsg.id;
              return (
                <div className="max-w-2xl mx-auto mb-3">
                  <button
                    onClick={() => handleFollowUp(lastSourcedMsg.id, isActive ? [] : lastSourcedMsg.sources!, lastSourcedMsg.context_id ?? null)}
                    className={`w-full flex items-center gap-2.5 px-4 py-2.5 rounded-xl border text-sm font-medium transition-all ${
                      isActive
                        ? "bg-[#D9FF00]/15 border-[#D9FF00]/60 text-[#D9FF00]"
                        : "bg-[#1C2B36] border-[#243340] text-[#7B92A5] hover:border-[#D9FF00]/40 hover:text-[#e8e8e8]"
                    }`}
                  >
                    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
                    </svg>
                    <span className="flex-1 text-left">
                      {isActive
                        ? `Following up on ${lastSourcedMsg.sources!.length} document${lastSourcedMsg.sources!.length !== 1 ? "s" : ""} from last response`
                        : `Follow up on last response (${lastSourcedMsg.sources!.length} document${lastSourcedMsg.sources!.length !== 1 ? "s" : ""})`}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded-full border ${isActive ? "border-[#D9FF00]/40 text-[#D9FF00]" : "border-[#243340] text-[#4A6070]"}`}>
                      {isActive ? "ON" : "OFF"}
                    </span>
                  </button>
                </div>
              );
            })()}

            {/* Suggestion pills — shown only when chat is empty */}
            {messages.length === 0 && followUpSources.length === 0 && (
              <div className="flex flex-wrap gap-2 mb-3 max-w-2xl mx-auto">
                {[
                  "What are the biggest consumer trends for 2026?",
                  "What do reports say about AI adoption in marketing?",
                  "Which industries are forecasting the most growth?",
                ].map((s) => (
                  <button
                    key={s}
                    onClick={() => { setInput(s); textareaRef.current?.focus(); }}
                    className="text-xs text-[#7B92A5] border border-[#243340] rounded-full px-3 py-1.5 hover:border-[#D9FF00]/60 hover:text-[#e8e8e8] transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            {/* Industry filter pills */}
            {followUpSources.length === 0 && selectedIndustries.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-2 max-w-2xl mx-auto">
                {selectedIndustries.map((name) => (
                  <span key={name} className="flex items-center gap-1 bg-[#D9FF00]/15 text-[#D9FF00] text-xs px-2 py-1 rounded-full">
                    {name}
                    <button onClick={() => toggleIndustry(name)} className="hover:text-[#151F27] leading-none">×</button>
                  </span>
                ))}
              </div>
            )}

            <div className="flex gap-2 items-center max-w-2xl mx-auto">
              {/* Industry filter inside input row */}
              <div className="relative shrink-0" ref={pickerRef}>
                <button
                  onClick={() => setShowPicker((v) => !v)}
                  title={filterLabel}
                  className={`relative flex items-center justify-center px-3 py-3 rounded-lg border transition-colors ${
                    selectedIndustries.length > 0
                      ? "bg-[#D9FF00]/10 border-[#D9FF00] text-[#D9FF00]"
                      : "bg-[#1C2B36] border-[#243340] text-[#7B92A5] hover:border-[#3A5568] hover:text-[#e8e8e8]"
                  }`}
                >
                  <svg className="w-4 h-4 block" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 4h18M7 8h10M11 12h2" />
                  </svg>
                  {selectedIndustries.length > 0 && (
                    <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-[#D9FF00] text-[#151F27] text-[9px] font-bold flex items-center justify-center leading-none">
                      {selectedIndustries.length}
                    </span>
                  )}
                </button>

                {showPicker && (
                  <div className="absolute left-0 bottom-full mb-2 w-64 bg-[#1C2B36] border border-[#243340] rounded-xl shadow-xl z-50 overflow-hidden">
                    <div className="px-3 py-2 border-b border-[#243340] flex items-center justify-between">
                      <span className="text-xs text-[#7B92A5]">
                        {selectedIndustries.length === 0 ? "Filter by industry" : `${selectedIndustries.length} selected`}
                      </span>
                      {selectedIndustries.length > 0 && (
                        <button onClick={() => setSelectedIndustries([])} className="text-xs text-[#D9FF00] hover:text-[#E8FF4D]">
                          Clear all
                        </button>
                      )}
                    </div>
                    <ul className="max-h-64 overflow-y-auto py-1">
                      {industries.map((ind) => {
                        const checked = selectedIndustries.includes(ind.name);
                        return (
                          <li key={ind.name}>
                            <button
                              onClick={() => toggleIndustry(ind.name)}
                              className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left transition-colors hover:bg-[#243340] ${checked ? "text-[#e8e8e8]" : "text-[#7B92A5]"}`}
                            >
                              <span className={`w-4 h-4 shrink-0 rounded border flex items-center justify-center transition-colors ${checked ? "bg-[#D9FF00] border-[#D9FF00]" : "border-[#2A3D4A]"}`}>
                                {checked && (
                                  <svg className="w-2.5 h-2.5 text-[#151F27]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                  </svg>
                                )}
                              </span>
                              <span className="flex-1 truncate">{ind.name}</span>
                              <span className="text-xs text-[#4A6070]">{ind.count}</span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
              </div>

              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={followUpSources.length > 0 ? "Ask a follow-up question..." : "Ask about a trend, industry, or forecast..."}
                rows={1}
                className="flex-1 bg-[#1C2B36] border border-[#243340] text-[#e8e8e8] text-sm rounded-lg px-4 py-3 resize-none focus:outline-none focus:border-[#D9FF00] placeholder-[#4A6070] overflow-y-auto"
                style={{ lineHeight: "1.5", maxHeight: "160px" }}
                onInput={(e) => {
                  const t = e.currentTarget;
                  t.style.height = "auto";
                  t.style.height = Math.min(t.scrollHeight, 160) + "px";
                }}
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || loading}
                className="bg-[#D9FF00] hover:bg-[#E8FF4D] disabled:opacity-40 disabled:cursor-not-allowed text-[#151F27] rounded-lg px-4 py-3 text-sm font-medium transition-colors shrink-0"
              >
                Send
              </button>
            </div>
            <p className={`text-center text-xs text-[#4A6070] transition-[margin] duration-500 ease-in-out ${messages.length > 0 ? "mt-5" : "mt-[100px]"}`}>
              Built by Kathir, on top of trend reports 2026 collection from{" "}
              <a href="https://www.linkedin.com/in/amydaroukakis" target="_blank" rel="noopener noreferrer" className="text-[#7B92A5] hover:text-[#e8e8e8] underline underline-offset-2 transition-colors">
                Amy Daroukakis
              </a>
            </p>
          </footer>
        </>
      )}
    </div>
  );
}
