"use client";

import type { ConversationSummary } from "@/types";

interface ConversationListProps {
  conversations: ConversationSummary[] | null;
  activeId: string | null;
  onSelect: (id: string | null) => void;
  onDelete: (id: string) => void;
}

export function ConversationList({ conversations, activeId, onSelect, onDelete }: ConversationListProps) {
  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={() => onSelect(null)}
        className="rounded-md border border-line px-3 py-1.5 text-left text-sm font-medium hover:border-muted"
      >
        New chat
      </button>
      {conversations === null ? (
        <p className="px-3 py-2 text-xs text-muted">Loading conversations…</p>
      ) : conversations.length === 0 ? (
        <p className="px-3 py-2 text-xs text-muted">Your conversations will appear here.</p>
      ) : (
        <ul className="flex flex-col gap-0.5" aria-label="Conversations">
          {conversations.map((c) => {
            const active = c.id === activeId;
            return (
              <li key={c.id} className="group relative">
                <button
                  type="button"
                  onClick={() => onSelect(c.id)}
                  aria-current={active ? "true" : undefined}
                  className={`w-full truncate rounded-md py-1.5 pr-8 pl-3 text-left text-sm ${
                    active ? "bg-line/60 text-ink" : "text-muted hover:bg-line/40 hover:text-ink"
                  }`}
                  title={c.title}
                >
                  {c.title}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm(`Delete “${c.title}”?`)) onDelete(c.id);
                  }}
                  aria-label={`Delete conversation ${c.title}`}
                  className="absolute top-1/2 right-1 -translate-y-1/2 rounded px-1.5 text-muted opacity-0 group-hover:opacity-100 hover:text-bad focus:opacity-100"
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
