"use client";

import { useEffect, useRef, useState } from "react";

import type { DocumentOut } from "@/types";

interface DocumentFilterProps {
  documents: DocumentOut[];
  selected: string[];
  onChange: (ids: string[]) => void;
}

/** Multi-select to scope questions to specific documents. Empty selection = all documents. */
export function DocumentFilter({ documents, selected, onChange }: DocumentFilterProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const label =
    selected.length === 0
      ? "All documents"
      : selected.length === 1
        ? (documents.find((d) => d.id === selected[0])?.filename ?? "1 document")
        : `${selected.length} documents`;

  function toggle(id: string) {
    onChange(selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id]);
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="true"
        className="flex max-w-64 items-center gap-2 rounded-md border border-line bg-surface px-3 py-1.5 text-sm hover:border-muted"
      >
        <span className="text-muted">Search in</span>
        <span className="truncate font-medium">{label}</span>
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 w-80 max-w-[calc(100vw-2rem)] rounded-md border border-line bg-surface py-1 shadow-lg">
          {documents.length === 0 ? (
            <p className="px-3 py-2 text-sm text-muted">No ready documents yet.</p>
          ) : (
            <>
              <button
                type="button"
                onClick={() => onChange([])}
                className="w-full px-3 py-1.5 text-left text-sm text-action hover:bg-paper disabled:text-muted"
                disabled={selected.length === 0}
              >
                Search all documents
              </button>
              <ul className="max-h-72 overflow-y-auto">
                {documents.map((d) => (
                  <li key={d.id}>
                    <label className="flex cursor-pointer items-center gap-2.5 px-3 py-1.5 text-sm hover:bg-paper">
                      <input
                        type="checkbox"
                        checked={selected.includes(d.id)}
                        onChange={() => toggle(d.id)}
                        className="accent-action"
                      />
                      <span className="truncate">{d.filename}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}
