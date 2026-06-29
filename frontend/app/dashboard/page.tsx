"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getTenant, getApiKey } from "@/lib/api";
import ChatPanel from "@/components/ChatPanel";
import DocumentsPanel from "@/components/DocumentsPanel";
import { Copy, CheckCircle, LogOut, MessageSquare, FileText } from "lucide-react";

type Tab = "chat" | "documents";

export default function DashboardPage() {
  const router = useRouter();
  const [tenantName, setTenantName] = useState("");
  const [tab, setTab] = useState<Tab>("chat");
  const [copied, setCopied] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.push("/login");
      return;
    }
    getTenant()
      .then((t) => {
        setTenantName(t.name);
        setReady(true);
      })
      .catch(() => {
        localStorage.removeItem("access_token");
        localStorage.removeItem("api_key");
        router.push("/login");
      });
  }, [router]);

  function copyKey() {
    const key = getApiKey();
    if (!key) return;
    navigator.clipboard.writeText(key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("api_key");
    localStorage.removeItem("tenant_name");
    router.push("/login");
  }

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-400 text-sm">
        Loading…
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold text-sm">
            {tenantName[0]?.toUpperCase() ?? "?"}
          </div>
          <span className="font-semibold text-gray-800">{tenantName}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={copyKey}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-indigo-600 border border-gray-200 rounded-lg px-3 py-1.5 hover:border-indigo-300 transition"
          >
            {copied ? (
              <CheckCircle className="w-3.5 h-3.5 text-green-500" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
            {copied ? "Copied!" : "Copy API Key"}
          </button>
          <button
            onClick={logout}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-red-500 border border-gray-200 rounded-lg px-3 py-1.5 hover:border-red-200 transition"
          >
            <LogOut className="w-3.5 h-3.5" />
            Logout
          </button>
        </div>
      </header>

      {/* Tabs */}
      <div className="bg-white border-b border-gray-200 px-6">
        <nav className="flex gap-1">
          {(["chat", "documents"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex items-center gap-1.5 px-4 py-3 text-sm font-medium border-b-2 transition ${
                tab === t
                  ? "border-indigo-600 text-indigo-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {t === "chat" ? (
                <MessageSquare className="w-4 h-4" />
              ) : (
                <FileText className="w-4 h-4" />
              )}
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </nav>
      </div>

      {/* Content */}
      <main className="flex-1 overflow-hidden">
        {tab === "chat" ? (
          <div className="h-full max-w-3xl mx-auto flex flex-col" style={{ height: "calc(100vh - 112px)" }}>
            <ChatPanel />
          </div>
        ) : (
          <div className="max-w-4xl mx-auto p-6">
            <DocumentsPanel />
          </div>
        )}
      </main>
    </div>
  );
}
