"use client";

import { memo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { CitationChip } from "@/components/CitationChip";
import type { ChatMessage } from "@/hooks/useChatStream";
import type { Citation } from "@/types";

const CITE_PREFIX = "#cite-";

/** Turn inline `[2]` markers into links the Markdown renderer lets us intercept. */
export function linkCitations(markdown: string): string {
  return markdown.replace(/\[(\d{1,2})\](?![(:])/g, `[$1](${CITE_PREFIX}$1)`);
}

interface MessageBubbleProps {
  message: ChatMessage;
  activeChunkId: string | null;
  onOpenCitation: (citation: Citation) => void;
}

function MessageBubbleImpl({ message, activeChunkId, onOpenCitation }: MessageBubbleProps) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-lg bg-line/50 px-4 py-2.5 text-[15px] whitespace-pre-wrap">
          {message.content}
        </p>
      </div>
    );
  }

  const byIndex = new Map(message.citations.map((c) => [c.index, c]));

  const components: Components = {
    a({ href, children }) {
      if (href?.startsWith(CITE_PREFIX)) {
        const citation = byIndex.get(Number(href.slice(CITE_PREFIX.length)));
        if (!citation) {
          // Citation metadata arrives after the text; until then show a plain marker.
          return <span className="rounded-sm bg-marker/50 px-0.5 font-sans text-[0.8em]">{children}</span>;
        }
        return (
          <button
            type="button"
            onClick={() => onOpenCitation(citation)}
            className="rounded-sm bg-marker px-1 align-baseline font-sans text-[0.8em] font-semibold hover:bg-marker/70"
            aria-label={`Source ${citation.index}: ${citation.filename}, page ${citation.page}`}
          >
            {children}
          </button>
        );
      }
      // Model output is untrusted: external links open safely in a new tab.
      return (
        <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="text-action underline">
          {children}
        </a>
      );
    },
  };

  const streaming = message.status === "streaming";

  return (
    <div>
      {message.content ? (
        <div className="answer">
          {/* react-markdown renders to React elements (no dangerouslySetInnerHTML), so
              HTML in model output is shown as text, not executed: no XSS via the LLM. */}
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
            {linkCitations(message.content)}
          </ReactMarkdown>
          {streaming && (
            <span
              className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-ink/60 align-middle"
              aria-hidden
            />
          )}
        </div>
      ) : streaming ? (
        <p className="text-sm text-muted" aria-live="polite">
          Searching your documents…
        </p>
      ) : null}

      {message.status === "stopped" && <p className="mt-2 text-xs text-muted">Stopped.</p>}
      {message.status === "error" && (
        <p className="mt-2 text-xs text-bad">This answer didn’t finish. Ask again to retry.</p>
      )}

      {message.citations.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Sources">
          {message.citations.map((c) => (
            <CitationChip
              key={c.index}
              citation={c}
              active={activeChunkId === c.chunk_id}
              onOpen={onOpenCitation}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// Memoized: while one answer streams, earlier messages don't re-render per token.
export const MessageBubble = memo(MessageBubbleImpl);
