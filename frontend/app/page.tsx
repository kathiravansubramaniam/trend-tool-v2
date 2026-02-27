"use client";

import { useEffect, useRef, useState } from "react";
import Message from "../components/Message";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

interface Stats {
  indexed: number;
  industries: number;
  embeddings: number;
}

let msgIdCounter = 0;

export default function Home() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [industries, setIndustries] = useState<Industry[]>([]);
  const [selectedIndustries, setSelectedIndustries] = useState<string[]>([]);
  const [showPicker, setShowPicker] = useState(false);
  const [stats, setStats] = useState<Stats | null>(null);
  // Follow-up state: id of the message whose sources are pinned, plus sources and context_id
  const [followUpMsgId, setFollowUpMsgId] = useState<number | null>(null);
  const [followUpSources, setFollowUpSources] = useState<Source[]>([]);
  const [followUpContextId, setFollowUpContextId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pickerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`${API}/api/industries`)
      .then((r) => r.json())
      .then(setIndustries)
      .catch(() => {});
    fetch(`${API}/api/stats`)
      .then((r) => r.json())
      .then(setStats)
      .catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Close picker when clicking outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setShowPicker(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const toggleIndustry = (name: string) => {
    setSelectedIndustries((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]
    );
  };

  const filterLabel =
    selectedIndustries.length === 0
      ? "All Industries"
      : selectedIndustries.length === 1
      ? selectedIndustries[0]
      : `${selectedIndustries.length} industries`;

  const handleFollowUp = (msgId: number, sources: Source[], contextId: string | null) => {
    if (sources.length === 0) {
      // Toggle off
      setFollowUpMsgId(null);
      setFollowUpSources([]);
      setFollowUpContextId(null);
    } else {
      setFollowUpMsgId(msgId);
      setFollowUpSources(sources);
      setFollowUpContextId(contextId ?? null);
      textareaRef.current?.focus();
    }
  };

  const handleSend = async () => {
    const q = input.trim();
    if (!q || loading) return;

    setMessages((prev) => [...prev, { id: ++msgIdCounter, role: "user", content: q }]);
    setInput("");
    setElapsed(0);
    setLoading(true);
    timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);

    try {
      const body: Record<string, unknown> = { question: q };
      if (followUpSources.length > 0 && followUpContextId) {
        // Fast path: send context_id so the server reuses cached chunks
        body.context_id = followUpContextId;
      } else if (followUpSources.length > 0) {
        // Fallback: send gcs_names if context_id not available yet
        body.pinned_gcs_names = followUpSources.map((s) => s.gcs_name);
      } else {
        body.industry_filter = selectedIndustries.length > 0 ? selectedIndustries : null;
      }

      const res = await fetch(`${API}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error("API error");
      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        { id: ++msgIdCounter, role: "assistant", content: data.answer, sources: data.sources, context_id: data.context_id, elapsed },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { id: ++msgIdCounter, role: "assistant", content: "Something went wrong. Make sure the API is running (`make api`)." },
      ]);
    } finally {
      if (timerRef.current) clearInterval(timerRef.current);
      setLoading(false);
      textareaRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-screen bg-[#0f0f0f]">
      {/* Header */}
      <header className="px-6 py-4 border-b border-[#2e2e2e] bg-[#0f0f0f]">
        <div className="flex items-center justify-between max-w-2xl mx-auto">
        <div>
          <h1 className="text-lg font-semibold text-[#e8e8e8]">Trend Analysis Bot</h1>
          {stats && (
            <p className="text-xs text-[#888] mt-0.5">
              {stats.indexed} reports · {stats.industries} industries
            </p>
          )}
        </div>

        {/* Multi-select industry picker */}
        <div className="relative" ref={pickerRef}>
          <button
            onClick={() => setShowPicker((v) => !v)}
            className={`flex items-center gap-2 bg-[#1a1a1a] border text-sm rounded-lg px-3 py-2 focus:outline-none transition-colors cursor-pointer ${
              selectedIndustries.length > 0
                ? "border-[#6366f1] text-[#e8e8e8]"
                : "border-[#2e2e2e] text-[#e8e8e8]"
            }`}
          >
            <span className="max-w-[180px] truncate">{filterLabel}</span>
            {selectedIndustries.length > 0 && (
              <span
                onClick={(e) => { e.stopPropagation(); setSelectedIndustries([]); }}
                className="ml-1 text-[#888] hover:text-[#e8e8e8] leading-none"
                title="Clear filters"
              >
                ×
              </span>
            )}
            <svg
              className={`w-3.5 h-3.5 text-[#888] transition-transform ${showPicker ? "rotate-180" : ""}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {showPicker && (
            <div className="absolute right-0 mt-1 w-64 bg-[#1a1a1a] border border-[#2e2e2e] rounded-xl shadow-xl z-50 overflow-hidden">
              <div className="px-3 py-2 border-b border-[#2e2e2e] flex items-center justify-between">
                <span className="text-xs text-[#888]">
                  {selectedIndustries.length === 0
                    ? "Filter by industry"
                    : `${selectedIndustries.length} selected`}
                </span>
                {selectedIndustries.length > 0 && (
                  <button
                    onClick={() => setSelectedIndustries([])}
                    className="text-xs text-[#6366f1] hover:text-[#818cf8]"
                  >
                    Clear all
                  </button>
                )}
              </div>
              <ul className="max-h-72 overflow-y-auto py-1">
                {industries.map((ind) => {
                  const checked = selectedIndustries.includes(ind.name);
                  return (
                    <li key={ind.name}>
                      <button
                        onClick={() => toggleIndustry(ind.name)}
                        className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left transition-colors hover:bg-[#242424] ${
                          checked ? "text-[#e8e8e8]" : "text-[#aaa]"
                        }`}
                      >
                        <span
                          className={`w-4 h-4 shrink-0 rounded border flex items-center justify-center transition-colors ${
                            checked ? "bg-[#6366f1] border-[#6366f1]" : "border-[#444]"
                          }`}
                        >
                          {checked && (
                            <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                            </svg>
                          )}
                        </span>
                        <span className="flex-1 truncate">{ind.name}</span>
                        <span className="text-xs text-[#555]">{ind.count}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>
        </div>
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto px-6 py-6 scrollbar-thin">
        <div className="max-w-2xl mx-auto">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-4">
            <div className="w-12 h-12 rounded-2xl bg-[#6366f1]/20 flex items-center justify-center text-2xl">
              📊
            </div>
            <div>
              <p className="text-[#e8e8e8] font-medium">Ask anything about trends</p>
              <p className="text-[#888] text-sm mt-1">
                Search across {stats?.indexed ?? "—"} trend reports
              </p>
            </div>
            <div className="flex flex-col gap-2 mt-2 w-full max-w-md">
              {[
                "What are the biggest consumer trends for 2026?",
                "What do reports say about AI adoption in marketing?",
                "Which industries are forecasting the most growth?",
              ].map((s) => (
                <button
                  key={s}
                  onClick={() => { setInput(s); textareaRef.current?.focus(); }}
                  className="text-sm text-[#888] border border-[#2e2e2e] rounded-xl px-4 py-2.5 hover:border-[#6366f1] hover:text-[#e8e8e8] transition-colors text-left"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <Message
            key={msg.id}
            role={msg.role}
            content={msg.content}
            sources={msg.sources}
            elapsed={msg.elapsed}
            isFollowUpActive={followUpMsgId === msg.id}
            onFollowUp={(sources) => handleFollowUp(msg.id, sources, msg.context_id ?? null)}
          />
        ))}

        {loading && (
          <div className="flex items-start mb-6">
            <div className="bg-[#1a1a1a] border border-[#2e2e2e] rounded-2xl rounded-bl-sm px-4 py-3">
              <div className="flex gap-2 items-center h-4">
                <span className="w-1.5 h-1.5 bg-[#6366f1] rounded-full animate-bounce [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 bg-[#6366f1] rounded-full animate-bounce [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 bg-[#6366f1] rounded-full animate-bounce [animation-delay:300ms]" />
                <span className="text-xs text-[#555] tabular-nums ml-1">{elapsed}s</span>
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
        </div>
      </main>

      {/* Input */}
      <footer className="px-6 py-4 border-t border-[#2e2e2e] bg-[#0f0f0f]">
        {/* Follow-up banner */}
        {followUpSources.length > 0 && (
          <div className="flex items-center justify-between max-w-2xl mx-auto mb-2 px-3 py-1.5 rounded-lg bg-[#6366f1]/10 border border-[#6366f1]/30">
            <span className="text-xs text-[#818cf8]">
              Following up on {followUpSources.length} document{followUpSources.length !== 1 ? "s" : ""}
            </span>
            <button
              onClick={() => { setFollowUpMsgId(null); setFollowUpSources([]); setFollowUpContextId(null); }}
              className="text-xs text-[#6366f1] hover:text-[#818cf8]"
            >
              Clear
            </button>
          </div>
        )}

        {/* Industry filter pills */}
        {followUpSources.length === 0 && selectedIndustries.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-2 max-w-2xl mx-auto">
            {selectedIndustries.map((name) => (
              <span
                key={name}
                className="flex items-center gap-1 bg-[#6366f1]/15 text-[#818cf8] text-xs px-2 py-1 rounded-full"
              >
                {name}
                <button
                  onClick={() => toggleIndustry(name)}
                  className="hover:text-white leading-none"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}

        <div className="flex gap-3 items-end max-w-2xl mx-auto">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              followUpSources.length > 0
                ? "Ask a follow-up question..."
                : "Ask about a trend, industry, or forecast..."
            }
            rows={1}
            className="flex-1 bg-[#1a1a1a] border border-[#2e2e2e] text-[#e8e8e8] text-sm rounded-2xl px-4 py-3 resize-none focus:outline-none focus:border-[#6366f1] placeholder-[#555] overflow-y-auto"
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
            className="bg-[#6366f1] hover:bg-[#818cf8] disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-2xl px-4 py-3 text-sm font-medium transition-colors shrink-0"
          >
            Send
          </button>
        </div>
        <p className="text-center text-xs text-[#555] mt-2">
          Enter to send · Shift+Enter for new line · Built on top of trends reports 2026 collection from{" "}
          <a href="https://www.linkedin.com/in/amydaroukakis?miniProfileUrn=urn%3Ali%3Afsd_profile%3AACoAAACPM3sBgbBCsfMgRQUgsgql8F7kaU2jM0Q" target="_blank" rel="noopener noreferrer" className="text-[#6366f1] hover:text-[#818cf8] transition-colors">Amy Daroukakis</a>
        </p>
      </footer>
    </div>
  );
}
