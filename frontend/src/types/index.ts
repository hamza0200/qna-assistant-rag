// Shared types mirroring the backend's Pydantic schemas (backend/app/schemas).

export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
}

export type DocumentStatus = "processing" | "ready" | "failed";

export interface DocumentOut {
  id: string;
  filename: string;
  page_count: number;
  chunk_count: number;
  status: DocumentStatus;
  error_message: string | null;
  created_at: string;
}

export interface Citation {
  index: number;
  chunk_id: string;
  document_id: string;
  filename: string;
  page: number;
  score: number;
  snippet: string;
}

export interface ChunkOut {
  id: string;
  document_id: string;
  filename: string;
  page_number: number;
  chunk_index: number;
  content: string;
}

export type MessageRole = "user" | "assistant";

export interface MessageOut {
  id: string;
  role: MessageRole;
  content: string;
  citations: Citation[] | null;
  created_at: string;
}

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: MessageOut[];
}

export interface ChatRequest {
  conversation_id?: string | null;
  message: string;
  document_ids?: string[] | null;
}

/** Discriminated union of the SSE events emitted by POST /api/chat. */
export type ChatStreamEvent =
  | { event: "meta"; data: { conversation_id: string; message_id: string } }
  | { event: "token"; data: { text: string } }
  | { event: "citations"; data: Citation[] }
  | { event: "error"; data: { code: string; message: string } }
  | { event: "done"; data: Record<string, never> };

export interface ApiErrorBody {
  error: { code: string; message: string };
}
