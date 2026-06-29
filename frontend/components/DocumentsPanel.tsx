"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { listDocuments, replaceDocument, deleteDocument, DocumentInfo } from "@/lib/api";
import UploadZone from "./UploadZone";
import { RefreshCw, Trash2, Upload, AlertCircle } from "lucide-react";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function DocumentsPanel() {
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const replaceInputRef = useRef<HTMLInputElement>(null);
  const [replaceTarget, setReplaceTarget] = useState<string | null>(null);

  const fetchDocs = useCallback(async () => {
    try {
      const res = await listDocuments();
      setDocs(res.documents);
      setError("");
      // Stop polling if all indexed
      const anyPending = res.documents.some((d) => d.chunk_count === null);
      if (!anyPending && pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load documents.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Initial load on mount. fetchDocs is async — its setState calls run after
    // the awaited request resolves, not synchronously in the effect body.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchDocs();
  }, [fetchDocs]);

  function startPolling() {
    if (pollRef.current) return;
    pollRef.current = setInterval(fetchDocs, 3000);
  }

  function handleUploaded() {
    fetchDocs();
    startPolling();
  }

  async function handleDelete(filename: string) {
    setActionLoading(filename);
    try {
      await deleteDocument(filename);
      await fetchDocs();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    } finally {
      setActionLoading(null);
      setDeleteTarget(null);
    }
  }

  function handleReplaceClick(filename: string) {
    setReplaceTarget(filename);
    replaceInputRef.current?.click();
  }

  async function handleReplaceFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !replaceTarget) return;
    setActionLoading(replaceTarget);
    try {
      await replaceDocument(replaceTarget, file);
      await fetchDocs();
      startPolling();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Replace failed.");
    } finally {
      setActionLoading(null);
      setReplaceTarget(null);
      e.target.value = "";
    }
  }

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  return (
    <div className="space-y-6">
      <UploadZone onUploaded={handleUploaded} />

      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">
          Documents ({docs.length})
        </h2>
        <button
          onClick={fetchDocs}
          className="text-gray-400 hover:text-gray-600 transition"
          title="Refresh"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-red-600 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      <input
        ref={replaceInputRef}
        type="file"
        accept=".pdf,.txt,.docx,.md"
        onChange={handleReplaceFile}
        className="hidden"
      />

      {loading ? (
        <p className="text-sm text-gray-400">Loading…</p>
      ) : docs.length === 0 ? (
        <p className="text-sm text-gray-400 text-center py-8">
          No documents yet. Upload one above.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left text-xs text-gray-500 uppercase tracking-wide">
                <th className="px-4 py-3 font-medium">Filename</th>
                <th className="px-4 py-3 font-medium">Size</th>
                <th className="px-4 py-3 font-medium">Uploaded</th>
                <th className="px-4 py-3 font-medium">Chunks</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {docs.map((doc) => (
                <tr key={doc.filename} className="hover:bg-gray-50 transition">
                  <td className="px-4 py-3 font-medium text-gray-800 max-w-[200px] truncate">
                    {doc.filename}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {formatBytes(doc.size_bytes)}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {formatDate(doc.uploaded_at)}
                  </td>
                  <td className="px-4 py-3">
                    {doc.chunk_count === null ? (
                      <span className="text-amber-600 text-xs font-medium">
                        indexing…
                      </span>
                    ) : (
                      <span className="text-gray-600">{doc.chunk_count}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => handleReplaceClick(doc.filename)}
                        disabled={!!actionLoading}
                        className="p-1.5 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 rounded transition disabled:opacity-40"
                        title="Replace"
                      >
                        <Upload className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => setDeleteTarget(doc.filename)}
                        disabled={!!actionLoading}
                        className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition disabled:opacity-40"
                        title="Delete"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Delete confirm modal */}
      {deleteTarget && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 max-w-sm w-full space-y-4">
            <h3 className="font-semibold text-gray-900">Delete document?</h3>
            <p className="text-sm text-gray-600">
              <span className="font-medium">{deleteTarget}</span> will be permanently deleted and removed from the knowledge base.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setDeleteTarget(null)}
                className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 transition"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deleteTarget)}
                disabled={!!actionLoading}
                className="px-4 py-2 text-sm text-white bg-red-600 rounded-lg hover:bg-red-700 transition disabled:opacity-50"
              >
                {actionLoading ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
