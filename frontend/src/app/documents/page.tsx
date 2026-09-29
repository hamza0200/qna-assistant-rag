"use client";

import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { DocumentList } from "@/components/DocumentList";
import { DocumentUploader } from "@/components/DocumentUploader";
import { api, ApiError } from "@/lib/api";
import type { DocumentOut } from "@/types";

const POLL_MS = 2000;

export default function DocumentsPage() {
  return (
    <AppShell>
      <DocumentsView />
    </AppShell>
  );
}

function DocumentsView() {
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Returns a cancel function so a response arriving after unmount is ignored.
  const load = useCallback(() => {
    let cancelled = false;
    api
      .listDocuments()
      .then((docs) => {
        if (cancelled) return;
        setDocuments(docs);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Couldn't load documents.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(), [load]);

  // Poll only while something is still processing; stops automatically once all settle.
  const anyProcessing = documents?.some((d) => d.status === "processing") ?? false;
  useEffect(() => {
    if (!anyProcessing) return;
    let cancelLast = () => {};
    const timer = setInterval(() => {
      cancelLast = load();
    }, POLL_MS);
    return () => {
      clearInterval(timer);
      cancelLast();
    };
  }, [anyProcessing, load]);

  async function handleDelete(id: string) {
    try {
      await api.deleteDocument(id);
      setDocuments((docs) => docs?.filter((d) => d.id !== id) ?? null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't delete the document.");
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 py-8 md:px-8">
        <h1 className="text-xl font-semibold">Documents</h1>
        <p className="mt-1 mb-6 text-sm text-muted">
          Upload PDFs to make them searchable in chat. Answers cite the document and page they came from.
        </p>
        <DocumentUploader onUploaded={(created) => setDocuments((docs) => [...created, ...(docs ?? [])])} />
        {error && (
          <p role="alert" className="mt-4 text-sm text-bad">
            {error}
          </p>
        )}
        <div className="mt-8">
          {documents === null ? (
            <p className="py-10 text-center text-sm text-muted">Loading documents…</p>
          ) : (
            <DocumentList documents={documents} onDelete={handleDelete} />
          )}
        </div>
      </div>
    </div>
  );
}
