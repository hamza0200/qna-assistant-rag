# API reference

Base path: `/api`. JSON unless noted. Interactive docs (Swagger UI) are served at `http://localhost:<BACKEND_PORT>/docs` outside production.

**Authentication:** send `Authorization: Bearer <access_token>` (from `POST /auth/login`) on every route marked *auth*. Tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default 60).

**Errors** always have this shape, with an HTTP status to match:

```json
{ "error": { "code": "NOT_FOUND", "message": "Document not found" } }
```

| Status | Codes |
|---|---|
| 400 | `BAD_REQUEST`, `NO_FILES`, `TOO_MANY_FILES`, `EMPTY_FILE` |
| 401 | `UNAUTHORIZED`, `INVALID_CREDENTIALS` |
| 404 | `NOT_FOUND` (also returned for resources owned by another user) |
| 409 | `EMAIL_TAKEN` |
| 413 | `FILE_TOO_LARGE` |
| 415 | `UNSUPPORTED_FILE_TYPE` |
| 422 | `VALIDATION_ERROR` |
| 429 | `RATE_LIMITED` (with `Retry-After`) |
| 500 | `INTERNAL_ERROR` (no internal details) |

Every response carries an `X-Request-ID` header; include it when reporting a problem so it can be matched to server logs.

---

## Health

### `GET /health`
No auth. `200` when the database answers, `503` otherwise.
```json
{ "status": "ok", "app": "DocMind AI", "database": "ok" }
```

## Auth

### `POST /auth/register`
```json
{ "email": "demo@docmind.dev", "password": "at least 8 characters" }
```
`201` → `{"id", "email", "created_at"}`. Emails are case-insensitive and unique (`409 EMAIL_TAKEN`). Passwords: 8–128 characters, ≤ 72 bytes.

### `POST /auth/login`
Same body. Rate-limited to 5/min per IP. `200`:
```json
{ "access_token": "eyJ…", "token_type": "bearer" }
```
`401 INVALID_CREDENTIALS` for an unknown email or a wrong password (same message and timing for both).

### `GET /auth/me` — *auth*
`200` → the current user.

## Documents

Document object:
```json
{
  "id": "2c288ccf-…",
  "filename": "Orbitra_Vault_Product_Guide.pdf",
  "page_count": 3,
  "chunk_count": 8,
  "status": "ready",
  "error_message": null,
  "created_at": "<ISO-8601 timestamp>"
}
```
`status` is `processing`, `ready` or `failed` (with `error_message`).

### `POST /documents` — *auth*
`multipart/form-data` with one or more `files` fields (PDF, ≤ `MAX_UPLOAD_MB` each, ≤ 10 per request). Rate-limited to 10/min per user. `202 Accepted` → array of document objects with `status: "processing"`. Ingestion runs in the background; poll `GET /documents/{id}`.

```bash
curl -X POST $API/documents -H "Authorization: Bearer $TOKEN" \
  -F "files=@sample-docs/Orbitra_Vault_Product_Guide.pdf;type=application/pdf"
```

### `GET /documents` — *auth*
`200` → the user's documents, newest first.

### `GET /documents/{id}` — *auth*
`200` → one document (used for status polling). `404` if missing or not yours.

### `DELETE /documents/{id}` — *auth*
`204`. Deletes the row, all its chunks (cascade) and the stored file.

### `GET /chunks/{id}` — *auth*
Full text of a cited chunk for the source viewer. Ownership is enforced through the parent document.
```json
{ "id": "…", "document_id": "…", "filename": "Orbitra_Vault_Product_Guide.pdf",
  "page_number": 1, "chunk_index": 1, "content": "Feature\nStarter\nTeam\n…" }
```

## Chat

### `POST /chat` — *auth* — `text/event-stream`
```json
{ "conversation_id": null, "message": "What is the monthly price of the Vault Business plan?", "document_ids": null }
```
- `conversation_id` — omit or `null` to start a new conversation; an ID you don't own → `404` (before streaming).
- `message` — 1–4,000 characters.
- `document_ids` — optional list to restrict retrieval to those documents.

Rate-limited to 20/min per user. Validation and ownership errors are normal JSON errors; once the stream has started, failures arrive as an `error` event.

Events, in order:

```
event: meta
data: {"conversation_id": "046e5ac3-…", "message_id": "becff0fe-…"}

event: token                     (repeated)
data: {"text": "The Business plan costs USD 29 per user per month "}

event: citations
data: [{"index": 1, "chunk_id": "…", "document_id": "…", "filename": "Orbitra_Vault_Product_Guide.pdf",
        "page": 1, "score": 0.74, "snippet": "Orbitra Vault Product Guide Plans, features…"}]

event: done
data: {}
```

On failure, instead of `citations`/`done`:
```
event: error
data: {"code": "LLM_TIMEOUT", "message": "The AI provider took too long to respond. Please try again."}
```
Error codes: `LLM_TIMEOUT`, `LLM_RATE_LIMITED`, `LLM_UNAVAILABLE`, `LLM_BAD_REQUEST`, `LLM_BILLING`, `LLM_REFUSED`, `LLM_NOT_CONFIGURED`.

`citations` lists only the sources the answer actually cites (`[n]` markers keep their numbers). When nothing relevant is retrieved, the answer is a fixed "couldn't find it in your uploaded documents" message, `citations` is `[]`, and no LLM call is made.

Consume it with `fetch` and a stream reader (EventSource can't POST or send headers):
```bash
curl -N -X POST $API/chat -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message": "What are the core collaboration hours?"}'
```

### `GET /conversations` — *auth*
`200` → `[{"id", "title", "created_at", "updated_at"}]`, most recently active first.

### `GET /conversations/{id}` — *auth*
`200` → the conversation plus `messages: [{"id", "role", "content", "citations", "created_at"}]` in order.

### `DELETE /conversations/{id}` — *auth*
`204`. Deletes the conversation and its messages.
