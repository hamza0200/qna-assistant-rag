"use client";

import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { ChunkOut, Citation } from "@/types";

interface SourcePanelProps {
  citation: Citation;
  onClose: () => void;
}

/** Shows the full cited passage, highlighted like a marked-up page. */
export function SourcePanel({ citation, onClose }: SourcePanelProps) {
  const [loaded, setLoaded] = useState<{ id: string; chunk?: ChunkOut; error?: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getChunk(citation.chunk_id)
      .then((chunk) => !cancelled && setLoaded({ id: citation.chunk_id, chunk }))
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError && err.status === 404
            ? "This passage is no longer available. The document may have been deleted."
            : "Couldn't load the passage.";
        setLoaded({ id: citation.chunk_id, error: message });
      });
    return () => {
      cancelled = true;
    };
  }, [citation.chunk_id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const current = loaded?.id === citation.chunk_id ? loaded : null;

  return (
    <aside
      aria-label="Source passage"
      className="fixed inset-0 z-30 flex flex-col bg-surface lg:static lg:inset-auto lg:z-auto lg:w-[26rem] lg:shrink-0 lg:border-l lg:border-line"
    >
      <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
        <div className="min-w-0">
          <p className="text-xs text-muted">Source {citation.index}</p>
          <h2 className="truncate font-medium" title={citation.filename}>
            {citation.filename}
          </h2>
          <p className="text-sm text-muted">
            Page {citation.page}
            <span className="mx-1.5 text-line">|</span>
            {Math.round(citation.score * 100)}% match
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 rounded-md px-2 py-1 text-sm text-muted hover:bg-line/50 hover:text-ink"
        >
          Close
        </button>
      </header>
      <div className="flex-1 overflow-y-auto px-5 py-5">
        {!current ? (
          <p className="text-sm text-muted">Loading passage…</p>
        ) : current.error ? (
          <p className="text-sm text-bad">{current.error}</p>
        ) : (
          <p className="font-serif text-[15px] leading-7 whitespace-pre-line">
            <mark className="box-decoration-clone bg-marker-soft px-0.5 text-ink">
              {current.chunk?.content}
            </mark>
          </p>
        )}
      </div>
    </aside>
  );
}
