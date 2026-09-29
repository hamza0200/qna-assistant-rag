"use client";

import { useCallback, useRef, useState } from "react";

import { API_URL, ApiError, authHeaders, toApiError } from "@/lib/api";
import { readSSE } from "@/lib/sse";
import type { ChatRequest, ChatStreamEvent, Citation, MessageOut } from "@/types";

export type ChatMessageStatus = "streaming" | "done" | "stopped" | "error";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  status: ChatMessageStatus;
}

interface UseChatStreamOptions {
  /** Called once the server has assigned (or confirmed) the conversation. */
  onConversation?: (conversationId: string) => void;
  /** Called after each turn finishes, however it ended. */
  onSettled?: () => void;
}

export function fromStored(m: MessageOut): ChatMessage {
  return {
    id: m.id,
    role: m.role,
    content: m.content,
    citations: (m.citations as Citation[] | null) ?? [],
    status: "done",
  };
}

/**
 * Sends a chat message and streams the answer into local state.
 * Uses fetch + ReadableStream (not EventSource) so it can POST with a bearer token,
 * and an AbortController to support the Stop button.
 */
export function useChatStream({ onConversation, onSettled }: UseChatStreamOptions = {}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const updateAssistant = useCallback((id: string, patch: (m: ChatMessage) => Partial<ChatMessage>) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch(m) } : m)));
  }, []);

  const send = useCallback(
    async (request: ChatRequest) => {
      if (abortRef.current) return; // one turn at a time
      const controller = new AbortController();
      abortRef.current = controller;
      setError(null);
      setIsStreaming(true);

      // Optimistic UI: show the question and an empty answer immediately.
      const tempId = `local-${crypto.randomUUID()}`;
      let assistantId = tempId;
      setMessages((prev) => [
        ...prev,
        { id: `${tempId}-q`, role: "user", content: request.message, citations: [], status: "done" },
        { id: tempId, role: "assistant", content: "", citations: [], status: "streaming" },
      ]);

      try {
        const res = await fetch(`${API_URL}/api/chat`, {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json", Accept: "text/event-stream" }),
          body: JSON.stringify(request),
          signal: controller.signal,
        });
        if (!res.ok || !res.body) throw await toApiError(res);

        for await (const raw of readSSE(res.body)) {
          const evt = { event: raw.event, data: JSON.parse(raw.data) } as ChatStreamEvent;
          switch (evt.event) {
            case "meta": {
              // Capture both IDs as constants: state updaters run later (at render time),
              // after `assistantId` has already been reassigned below.
              const localId = assistantId;
              const serverId = evt.data.message_id;
              setMessages((prev) => prev.map((m) => (m.id === localId ? { ...m, id: serverId } : m)));
              assistantId = serverId;
              onConversation?.(evt.data.conversation_id);
              break;
            }
            case "token": {
              const text = evt.data.text;
              updateAssistant(assistantId, (m) => ({ content: m.content + text }));
              break;
            }
            case "citations": {
              const citations = evt.data;
              updateAssistant(assistantId, () => ({ citations }));
              break;
            }
            case "error":
              updateAssistant(assistantId, () => ({ status: "error" }));
              setError(evt.data.message);
              break;
            case "done":
              updateAssistant(assistantId, () => ({ status: "done" }));
              break;
          }
        }
      } catch (err) {
        if (controller.signal.aborted) {
          updateAssistant(assistantId, () => ({ status: "stopped" }));
        } else {
          updateAssistant(assistantId, () => ({ status: "error" }));
          setError(err instanceof ApiError ? err.message : "The connection was interrupted. Try again.");
        }
      } finally {
        // A stream that ended without `done` or `error` was cut off.
        const finalId = assistantId;
        setMessages((prev) =>
          prev.map((m) => (m.id === finalId && m.status === "streaming" ? { ...m, status: "error" } : m)),
        );
        abortRef.current = null;
        setIsStreaming(false);
        onSettled?.();
      }
    },
    [onConversation, onSettled, updateAssistant],
  );

  /** Stop generating: aborting the fetch closes the connection, which cancels the LLM call server-side. */
  const stop = useCallback(() => abortRef.current?.abort(), []);

  return { messages, setMessages, send, stop, isStreaming, error, clearError: () => setError(null) };
}
