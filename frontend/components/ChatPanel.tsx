"use client";

import { useState, useRef, useEffect } from "react";
import { chat, clearSession, Source } from "@/lib/api";
import { Send, Loader2, FileText, Trash2 } from "lucide-react";

interface Message {
  role: "human" | "assistant";
  content: string;
  sources?: Source[];
  tools?: string[];
  error?: boolean;
}

export default function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const msg = input.trim();
    if (!msg || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "human", content: msg }]);
    setLoading(true);

    try {
      const res = await chat({ message: msg, session_id: sessionId });
      setSessionId(res.session_id);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.answer,
          sources: res.sources,
          tools: res.tools_used,
        },
      ]);
    } catch (err: unknown) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: err instanceof Error ? err.message : "Something went wrong.",
          error: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function handleClear() {
    if (sessionId) {
      await clearSession(sessionId).catch(() => {});
    }
    setSessionId(undefined);
    setMessages([]);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex justify-end p-2 border-b border-gray-100">
        <button
          onClick={handleClear}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-red-500 transition px-2 py-1 rounded hover:bg-red-50"
        >
          <Trash2 className="w-3.5 h-3.5" />
          Clear conversation
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 text-sm mt-16">
            Ask a question about your uploaded documents.
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex ${m.role === "human" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[75%] space-y-1.5 ${
                m.role === "human" ? "items-end" : "items-start"
              } flex flex-col`}
            >
              <div
                className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
                  m.role === "human"
                    ? "bg-indigo-600 text-white rounded-br-sm"
                    : m.error
                    ? "bg-red-50 text-red-700 border border-red-200 rounded-bl-sm"
                    : "bg-gray-100 text-gray-800 rounded-bl-sm"
                }`}
              >
                {m.content}
              </div>

              {m.sources && m.sources.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {m.sources.map((s, j) => (
                    <span
                      key={j}
                      className="inline-flex items-center gap-1 text-xs bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-full px-2 py-0.5"
                    >
                      <FileText className="w-3 h-3" />
                      {s.file}
                      {s.page != null && ` p.${s.page}`}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-2xl rounded-bl-sm px-4 py-2.5">
              <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form
        onSubmit={handleSend}
        className="border-t border-gray-200 p-4 flex gap-2"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask me anything…"
          disabled={loading}
          className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="bg-indigo-600 text-white rounded-lg px-4 py-2 hover:bg-indigo-700 transition disabled:opacity-40"
        >
          <Send className="w-4 h-4" />
        </button>
      </form>
    </div>
  );
}
