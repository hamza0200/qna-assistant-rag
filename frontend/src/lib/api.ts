// Typed fetch wrapper: attaches the JWT, logs out on 401, and normalizes every
// failure into an ApiError so components have exactly one error type to handle.

import { clearToken, getToken } from "@/lib/auth";
import type {
  ChunkOut,
  ConversationDetail,
  ConversationSummary,
  DocumentOut,
  TokenResponse,
  User,
} from "@/types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Build request headers, adding the bearer token when we have one. */
export function authHeaders(extra: HeadersInit = {}): Headers {
  const headers = new Headers(extra);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

/** Convert a non-OK response into an ApiError (and log out on 401). */
export async function toApiError(res: Response): Promise<ApiError> {
  let code = "HTTP_ERROR";
  let message = `Request failed (${res.status})`;
  try {
    const body = await res.json();
    if (body?.error) {
      code = body.error.code;
      message = body.error.message;
    }
  } catch {
    /* non-JSON error body */
  }
  if (res.status === 401 && getToken()) {
    // Expired/invalid session: drop the token; route guards redirect to /login.
    clearToken();
  }
  return new ApiError(res.status, code, message);
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = authHeaders(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "Can't reach the server. Check your connection and try again.");
  }
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// --- Endpoint helpers ----------------------------------------------------

export const api = {
  register: (email: string, password: string) =>
    apiFetch<User>("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),
  login: (email: string, password: string) =>
    apiFetch<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => apiFetch<User>("/auth/me"),

  listDocuments: () => apiFetch<DocumentOut[]>("/documents"),
  getDocument: (id: string) => apiFetch<DocumentOut>(`/documents/${id}`),
  deleteDocument: (id: string) => apiFetch<void>(`/documents/${id}`, { method: "DELETE" }),
  getChunk: (id: string) => apiFetch<ChunkOut>(`/chunks/${id}`),

  listConversations: () => apiFetch<ConversationSummary[]>("/conversations"),
  getConversation: (id: string) => apiFetch<ConversationDetail>(`/conversations/${id}`),
  deleteConversation: (id: string) => apiFetch<void>(`/conversations/${id}`, { method: "DELETE" }),
};

/**
 * Upload PDFs with progress. fetch() can't report upload progress, so this one
 * call uses XMLHttpRequest.
 */
export function uploadDocuments(
  files: File[],
  onProgress: (fraction: number) => void,
): Promise<DocumentOut[]> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/api/documents`);
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as DocumentOut[]);
        return;
      }
      if (xhr.status === 401) clearToken();
      const err = (body as { error?: { code: string; message: string } } | null)?.error;
      reject(
        new ApiError(xhr.status, err?.code ?? "HTTP_ERROR", err?.message ?? `Upload failed (${xhr.status})`),
      );
    };
    xhr.onerror = () => reject(new ApiError(0, "NETWORK_ERROR", "Upload failed: can't reach the server."));
    xhr.send(form);
  });
}
