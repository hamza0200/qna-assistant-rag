"use client";

import { useRef, useState, type DragEvent } from "react";

import { ApiError, uploadDocuments } from "@/lib/api";
import type { DocumentOut } from "@/types";

const MAX_MB = 20;

interface DocumentUploaderProps {
  onUploaded: (docs: DocumentOut[]) => void;
}

/** Client-side checks mirror the server's for fast feedback; the server re-validates everything. */
function precheck(files: File[]): string | null {
  for (const f of files) {
    if (!f.name.toLowerCase().endsWith(".pdf"))
      return `${f.name} isn't a PDF. Only .pdf files can be uploaded.`;
    if (f.size > MAX_MB * 1024 * 1024) return `${f.name} is larger than ${MAX_MB} MB.`;
  }
  return null;
}

export function DocumentUploader({ onUploaded }: DocumentUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleFiles(list: FileList | null) {
    const files = Array.from(list ?? []);
    if (files.length === 0) return;
    const problem = precheck(files);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    setProgress(0);
    try {
      onUploaded(await uploadDocuments(files, setProgress));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed. Try again.");
    } finally {
      setProgress(null);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    if (progress === null) void handleFiles(e.dataTransfer.files);
  }

  const uploading = progress !== null;

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors ${
          dragging ? "border-action bg-action/5" : "border-line bg-surface"
        }`}
      >
        {uploading ? (
          <div className="w-full max-w-xs" aria-live="polite">
            <p className="mb-2 text-sm">Uploading… {Math.round(progress * 100)}%</p>
            <div
              className="h-1.5 overflow-hidden rounded-full bg-line"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(progress * 100)}
            >
              <div className="h-full bg-action transition-[width]" style={{ width: `${progress * 100}%` }} />
            </div>
          </div>
        ) : (
          <>
            <p className="text-[15px]">Drop PDFs here, or</p>
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="rounded-md bg-action px-3.5 py-2 text-sm font-medium text-white hover:bg-action-hover"
            >
              Choose files
            </button>
            <p className="text-xs text-muted">
              PDF only, up to {MAX_MB} MB each. Scanned PDFs without text can’t be read.
            </p>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          className="sr-only"
          aria-label="Choose PDF files to upload"
          onChange={(e) => void handleFiles(e.target.files)}
        />
      </div>
      {error && (
        <p role="alert" className="mt-3 rounded-md border border-bad/30 bg-bad/5 px-3 py-2 text-sm text-bad">
          {error}
        </p>
      )}
    </div>
  );
}
