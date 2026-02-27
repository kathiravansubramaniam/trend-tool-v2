"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import SourceCard from "./SourceCard";

interface Source {
  gcs_name: string;
  name: string;
  industry: string;
  topics: string[];
  url?: string | null;
}

interface MessageProps {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  isFollowUpActive?: boolean;
  onFollowUp?: (sources: Source[]) => void;
}

export default function Message({ role, content, sources, isFollowUpActive, onFollowUp }: MessageProps) {
  const isUser = role === "user";
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className={`flex flex-col gap-3 ${isUser ? "items-end" : "items-start"} mb-6`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? "bg-[#6366f1] text-white rounded-br-sm"
            : "bg-[#1a1a1a] text-[#e8e8e8] border border-[#2e2e2e] rounded-bl-sm"
        }`}
      >
        {isUser ? (
          <span className="whitespace-pre-wrap">{content}</span>
        ) : (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: ({ children }) => <h1 className="text-base font-bold mt-4 mb-2 first:mt-0">{children}</h1>,
              h2: ({ children }) => <h2 className="text-sm font-bold mt-4 mb-1.5 first:mt-0">{children}</h2>,
              h3: ({ children }) => <h3 className="text-sm font-semibold mt-3 mb-1 first:mt-0">{children}</h3>,
              p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
              ul: ({ children }) => <ul className="list-disc pl-5 mb-3 space-y-1">{children}</ul>,
              ol: ({ children }) => <ol className="list-decimal pl-5 mb-3 space-y-1">{children}</ol>,
              li: ({ children }) => <li className="leading-relaxed">{children}</li>,
              strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
              em: ({ children }) => <em className="italic text-[#c8c8c8]">{children}</em>,
              code: ({ children }) => <code className="bg-[#2a2a2a] px-1.5 py-0.5 rounded text-xs font-mono text-[#e8c880]">{children}</code>,
              blockquote: ({ children }) => <blockquote className="border-l-2 border-[#6366f1] pl-3 my-3 text-[#aaa] italic">{children}</blockquote>,
              hr: () => <hr className="border-[#2e2e2e] my-3" />,
              table: ({ children }) => <div className="overflow-x-auto mb-3"><table className="text-xs border-collapse w-full">{children}</table></div>,
              th: ({ children }) => <th className="border border-[#2e2e2e] px-3 py-1.5 bg-[#222] font-semibold text-left">{children}</th>,
              td: ({ children }) => <td className="border border-[#2e2e2e] px-3 py-1.5">{children}</td>,
            }}
          >
            {content}
          </ReactMarkdown>
        )}
      </div>

      {!isUser && (
        <div className="flex items-center gap-2">
          {/* Copy button */}
          <button
            onClick={handleCopy}
            title="Copy answer"
            className="flex items-center gap-1.5 text-xs text-[#666] hover:text-[#aaa] transition-colors px-2 py-1 rounded-lg hover:bg-[#1a1a1a]"
          >
            {copied ? (
              <>
                <svg className="w-3.5 h-3.5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
                <span className="text-green-500">Copied</span>
              </>
            ) : (
              <>
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                </svg>
                <span>Copy</span>
              </>
            )}
          </button>

          {/* Follow-up toggle — only when sources are present */}
          {sources && sources.length > 0 && onFollowUp && (
            <button
              onClick={() => onFollowUp(isFollowUpActive ? [] : sources)}
              title={isFollowUpActive ? "Stop following up on these docs" : "Ask follow-up questions using these docs"}
              className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded-lg transition-colors ${
                isFollowUpActive
                  ? "bg-[#6366f1]/20 text-[#818cf8] hover:bg-[#6366f1]/30"
                  : "text-[#666] hover:text-[#aaa] hover:bg-[#1a1a1a]"
              }`}
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
              </svg>
              <span>{isFollowUpActive ? "Following up" : "Follow up"}</span>
            </button>
          )}
        </div>
      )}

      {sources && sources.length > 0 && (
        <div className="w-full max-w-[80%]">
          <p className="text-xs text-[#888] mb-2">
            Sources ({sources.length} document{sources.length !== 1 ? "s" : ""})
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {sources.map((s, i) => (
              <SourceCard key={i} source={s} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
