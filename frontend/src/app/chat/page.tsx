"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { ChatWindow } from "@/components/ChatWindow";
import { ConversationList } from "@/components/ConversationList";
import { SourcePanel } from "@/components/SourcePanel";
import { Toast } from "@/components/ui/Toast";
import { fromStored, useChatStream } from "@/hooks/useChatStream";
import { api, ApiError } from "@/lib/api";
import type { Citation, ConversationSummary, DocumentOut } from "@/types";

export default function ChatPage() {
  // useSearchParams must sit under a Suspense boundary in the App Router.
  return (
    <Suspense fallback={<div className="grid min-h-dvh place-items-center text-sm text-muted">Loading…</div>}>
      <ChatPageInner />
    </Suspense>
  );
}

function ChatPageInner() {
  const router = useRouter();
  const conversationId = useSearchParams().get("c");

  const [conversations, setConversations] = useState<ConversationSummary[] | null>(null);
  const [documents, setDocuments] = useState<DocumentOut[]>([]);
  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [citation, setCitation] = useState<Citation | null>(null);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  // The conversation a stream just created: its URL change must not reload (and wipe) the live messages.
  const createdByStream = useRef<string | null>(null);

  const refreshConversations = useCallback(() => {
    api
      .listConversations()
      .then(setConversations)
      .catch(() => setConversations((c) => c ?? []));
  }, []);

  const onConversation = useCallback(
    (id: string) => {
      if (id !== conversationId) {
        createdByStream.current = id;
        router.replace(`/chat?c=${id}`, { scroll: false });
      }
    },
    [conversationId, router],
  );

  const { messages, setMessages, send, stop, isStreaming, error, clearError } = useChatStream({
    onConversation,
    onSettled: refreshConversations,
  });

  useEffect(() => {
    refreshConversations();
    api
      .listDocuments()
      .then((docs) => setDocuments(docs.filter((d) => d.status === "ready")))
      .catch(() => setDocuments([]));
  }, [refreshConversations]);

  // Load the selected conversation whenever the URL changes.
  useEffect(() => {
    if (conversationId && conversationId === createdByStream.current) return;
    let cancelled = false;
    // Deferred so state isn't set synchronously inside the effect body.
    queueMicrotask(() => {
      if (cancelled) return;
      setCitation(null);
      if (!conversationId) {
        setMessages([]);
        return;
      }
      setLoadingConversation(true);
      api
        .getConversation(conversationId)
        .then((conv) => !cancelled && setMessages(conv.messages.map(fromStored)))
        .catch((err: unknown) => {
          if (cancelled) return;
          setMessages([]);
          setPageError(
            err instanceof ApiError && err.status === 404
              ? "That conversation doesn't exist or was deleted."
              : "Couldn't load the conversation.",
          );
        })
        .finally(() => !cancelled && setLoadingConversation(false));
    });
    return () => {
      cancelled = true;
    };
  }, [conversationId, setMessages]);

  function selectConversation(id: string | null) {
    if (isStreaming) stop();
    createdByStream.current = null;
    router.push(id ? `/chat?c=${id}` : "/chat", { scroll: false });
  }

  async function deleteConversation(id: string) {
    try {
      await api.deleteConversation(id);
      setConversations((cs) => cs?.filter((c) => c.id !== id) ?? null);
      if (id === conversationId) selectConversation(null);
    } catch {
      setPageError("Couldn't delete the conversation.");
    }
  }

  const handleSend = useCallback(
    (message: string) => {
      setCitation(null);
      void send({
        message,
        conversation_id: conversationId,
        document_ids: selectedDocs.length ? selectedDocs : null,
      });
    },
    [send, conversationId, selectedDocs],
  );

  const openCitation = useCallback((c: Citation) => setCitation(c), []);
  const closeCitation = useCallback(() => setCitation(null), []);
  const dismissError = useCallback(() => {
    clearError();
    setPageError(null);
  }, [clearError]);

  return (
    <AppShell
      sidebar={
        <ConversationList
          conversations={conversations}
          activeId={conversationId}
          onSelect={selectConversation}
          onDelete={(id) => void deleteConversation(id)}
        />
      }
    >
      <div className="flex h-full">
        <ChatWindow
          messages={messages}
          loading={loadingConversation}
          isStreaming={isStreaming}
          documents={documents}
          selectedDocs={selectedDocs}
          onSelectDocs={setSelectedDocs}
          activeChunkId={citation?.chunk_id ?? null}
          onOpenCitation={openCitation}
          onSend={handleSend}
          onStop={stop}
        />
        {citation && <SourcePanel citation={citation} onClose={closeCitation} />}
      </div>
      <Toast message={error ?? pageError} onDismiss={dismissError} />
    </AppShell>
  );
}
