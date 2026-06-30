"use client";

import { useState, useRef, DragEvent } from "react";
import { ingestDocument } from "@/lib/api";
import { Upload, FileText, AlertCircle, CheckCircle } from "lucide-react";

const ACCEPTED = [".pdf", ".txt", ".docx", ".md"];

interface Props {
  onUploaded: () => void;
}

export default function UploadZone({ onUploaded }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  function validate(f: File): string {
    const ext = "." + f.name.split(".").pop()?.toLowerCase();
    if (!ACCEPTED.includes(ext)) {
      return `Unsupported type. Accepted: ${ACCEPTED.join(", ")}`;
    }
    if (f.size > 2 * 1024 * 1024) {
      return "File exceeds the 2 MB limit.";
    }
    return "";
  }

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const err = validate(f);
    if (err) { setError(err); return; }
    setError("");
    setSuccess("");
    setFile(f);
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (!f) return;
    const err = validate(f);
    if (err) { setError(err); return; }
    setError("");
    setSuccess("");
    setFile(f);
  }

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setError("");
    setSuccess("");
    try {
      const res = await ingestDocument(file);
      setSuccess(`"${res.filename}" queued for indexing.`);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      onUploaded();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition ${
          dragging
            ? "border-indigo-400 bg-indigo-50"
            : "border-gray-300 hover:border-indigo-400 hover:bg-gray-50"
        }`}
      >
        <Upload className="w-8 h-8 text-gray-400 mx-auto mb-2" />
        <p className="text-sm text-gray-600 font-medium">
          Drag & drop or <span className="text-indigo-600">browse</span>
        </p>
        <p className="text-xs text-gray-400 mt-1">
          {ACCEPTED.join(", ")} · max 2 MB per file · 10 MB total
        </p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED.join(",")}
          onChange={onFileChange}
          className="hidden"
        />
      </div>

      {file && (
        <div className="flex items-center justify-between bg-gray-50 border border-gray-200 rounded-lg px-4 py-2.5">
          <div className="flex items-center gap-2 text-sm text-gray-700">
            <FileText className="w-4 h-4 text-gray-400" />
            <span className="truncate max-w-xs">{file.name}</span>
          </div>
          <button
            onClick={handleUpload}
            disabled={uploading}
            className="text-sm bg-indigo-600 text-white rounded-lg px-4 py-1.5 hover:bg-indigo-700 transition disabled:opacity-50"
          >
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 text-red-600 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {success && (
        <div className="flex items-center gap-2 text-green-600 text-sm">
          <CheckCircle className="w-4 h-4 shrink-0" />
          {success}
        </div>
      )}
    </div>
  );
}
