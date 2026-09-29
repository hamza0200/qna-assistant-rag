"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { DocumentFilter } from "@/components/DocumentFilter";
import { MessageBubble } from "@/components/MessageBubble";
import type { ChatMessage } from "@/hooks/useChatStream";
import type { Citation, DocumentOut } from "@/types";

interface ChatWindowProps {
  messages: ChatMessage[];
  loading: boolean;
  isStreaming: boolean;
  documents: DocumentOut[];
  selectedDocs: string[];
  onSelectDocs: (ids: string[]) => void;
  activeChunkId: string | null;
  onOpenCitation: (citation: Citation) => void;
  onSend: (message: string) => void;
  onStop: () => void;
}

export function ChatWindow({
  messages,
  loading,
  isStreaming,
  documents,
  selectedDocs,
  onSelectDocs,
  activeChunkId,
  onOpenCitation,
  onSend,
  onStop,
}: ChatWindowProps) {
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll while streaming, unless the user has scrolled up to read.
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  function onScroll() {
    const el = scrollRef.current;
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }

  function submit(e?: FormEvent) {
    e?.preventDefault();
    const text = draft.trim();
    if (!text || isStreaming) return;
    stickToBottom.current = true;
    onSend(text);
    setDraft("");
  }

  // Enter sends; Shift+Enter inserts a newline. isComposing guards IME input (e.g. Japanese).
  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  // Grow the textarea with its content, up to a limit.
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [draft]);

  const hasDocs = documents.length > 0;

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col">
      <div className="flex items-center justify-end gap-3 border-b border-line bg-surface px-4 py-2.5">
        <DocumentFilter documents={documents} selected={selectedDocs} onChange={onSelectDocs} />
      </div>

      <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-3xl flex-col gap-8 px-4 py-8 md:px-8">
          {loading ? (
            <p className="text-sm text-muted">Loading conversation…</p>
          ) : messages.length === 0 ? (
            <div className="pt-[12vh]">
              <h1 className="font-serif text-3xl">What do you want to find out?</h1>
              <p className="mt-3 max-w-prose text-muted">
                {hasDocs
                  ? `Ask anything about your ${documents.length} ${documents.length === 1 ? "document" : "documents"}. Every answer links to the page it came from, and if the documents don’t say, you’ll be told so.`
                  : "You don’t have any documents ready yet."}
              </p>
              {!hasDocs && (
                <Link
                  href="/documents"
                  className="mt-4 inline-block rounded-md bg-action px-3.5 py-2 text-sm font-medium text-white hover:bg-action-hover"
                >
                  Upload documents
                </Link>
              )}
            </div>
          ) : (
            messages.map((m) => (
              <MessageBubble
                key={m.id}
                message={m}
                activeChunkId={activeChunkId}
                onOpenCitation={onOpenCitation}
              />
            ))
          )}
        </div>
      </div>

      <form onSubmit={submit} className="border-t border-line bg-surface px-4 py-3">
        <div className="mx-auto flex max-w-3xl items-end gap-2">
          <label htmlFor="chat-input" className="sr-only">
            Your question
          </label>
          <textarea
            id="chat-input"
            ref={textareaRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            maxLength={4000}
            placeholder="Ask about your documents…"
            className="max-h-[200px] min-h-[42px] flex-1 resize-none rounded-md border border-line bg-paper px-3 py-2.5 text-[15px] outline-none focus:border-action"
          />
          {isStreaming ? (
            <button
              type="button"
              onClick={onStop}
              className="h-[42px] shrink-0 rounded-md border border-line px-4 text-sm font-medium hover:border-muted"
            >
              Stop
            </button>
          ) : (
            <button
              type="submit"
              disabled={!draft.trim()}
              className="h-[42px] shrink-0 rounded-md bg-action px-4 text-sm font-medium text-white hover:bg-action-hover disabled:bg-action/40"
            >
              Send
            </button>
          )}
        </div>
        <p className="mx-auto mt-1.5 max-w-3xl text-xs text-muted">
          Enter to send, Shift+Enter for a new line.
        </p>
      </form>
    </div>
  );
}
