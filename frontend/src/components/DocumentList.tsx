"use client";

import { useState } from "react";

import type { DocumentOut, DocumentStatus } from "@/types";

const STATUS: Record<DocumentStatus, { label: string; className: string }> = {
  processing: { label: "Processing", className: "bg-wait/10 text-wait" },
  ready: { label: "Ready", className: "bg-ok/10 text-ok" },
  failed: { label: "Failed", className: "bg-bad/10 text-bad" },
};

function StatusBadge({ status }: { status: DocumentStatus }) {
  const s = STATUS[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${s.className}`}
    >
      {status === "processing" && (
        <span className="size-1.5 animate-pulse rounded-full bg-current" aria-hidden="true" />
      )}
      {s.label}
    </span>
  );
}

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

interface DocumentListProps {
  documents: DocumentOut[];
  onDelete: (id: string) => Promise<void>;
}

export function DocumentList({ documents, onDelete }: DocumentListProps) {
  const [confirming, setConfirming] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  if (documents.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-muted">
        No documents yet. Upload a PDF above to start asking questions about it.
      </p>
    );
  }

  async function confirmDelete(id: string) {
    setDeleting(id);
    try {
      await onDelete(id);
    } finally {
      setDeleting(null);
      setConfirming(null);
    }
  }

  return (
    <ul className="divide-y divide-line border-y border-line">
      {documents.map((doc) => (
        <li key={doc.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium" title={doc.filename}>
              {doc.filename}
            </p>
            <p className="text-xs text-muted">
              {doc.status === "ready"
                ? `${doc.page_count} ${doc.page_count === 1 ? "page" : "pages"}, ${doc.chunk_count} chunks`
                : doc.status === "failed"
                  ? doc.error_message
                  : "Reading and indexing…"}
              <span className="mx-1.5 text-line">|</span>
              {dateFormat.format(new Date(doc.created_at))}
            </p>
          </div>
          <StatusBadge status={doc.status} />
          {confirming === doc.id ? (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted">Delete this document?</span>
              <button
                type="button"
                disabled={deleting === doc.id}
                onClick={() => void confirmDelete(doc.id)}
                className="rounded-md bg-bad px-2.5 py-1 font-medium text-white hover:bg-bad/90 disabled:opacity-60"
              >
                {deleting === doc.id ? "Deleting…" : "Delete"}
              </button>
              <button
                type="button"
                onClick={() => setConfirming(null)}
                className="rounded-md px-2.5 py-1 text-muted hover:bg-line/50"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirming(doc.id)}
              className="rounded-md px-2.5 py-1 text-sm text-muted hover:bg-line/50 hover:text-bad"
              aria-label={`Delete ${doc.filename}`}
            >
              Delete
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}
