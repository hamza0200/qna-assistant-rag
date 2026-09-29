<div align="center">

# 📄 DocMind AI

**Chat with your PDFs. Every answer cites the document and page it came from.**

Upload PDFs → ask questions → get streamed answers with clickable citations.
If the answer isn't in your documents, DocMind says so instead of guessing.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6?logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white)
![Claude](https://img.shields.io/badge/LLM-Claude%20%7C%20OpenAI-D97757)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

![Documents page](docs/screenshots/documents.png)

</div>

---

## Contents

[Features](#-features) · [Quick start](#-quick-start) · [Demo accounts](#-demo-accounts--credentials) · [API keys & models](#-api-keys--models) · [How it works](#-how-it-works) · [Code map](#-code-map-every-file) · [Database](#-database) · [Tests](#-tests-lint-eval) · [Troubleshooting](#-troubleshooting) · [New to Python?](#-new-to-python) · [Contributing](#-contributing)

## ✨ Features

- 🔐 **Accounts:** email + password (bcrypt hashing), JWT login tokens
- 📤 **PDF upload:** drag and drop, multiple files, 20 MB each; validated by extension, MIME type and file signature
- ⚙️ **Background processing:** PDF → text → chunks → embeddings, with a live status badge
- 💬 **Streaming chat:** answers appear word by word; Stop button; Markdown
- 📌 **Citations:** `[1]` markers and chips (`Orbitra_Vault_Product_Guide.pdf · p.1`) that open the exact passage
- 🙅 **Honest "not found":** skips the LLM entirely when nothing relevant is found
- 🗂️ **Conversations:** saved history, follow-up questions, filter by document
- 🛡️ **Security:** per-user data isolation, rate limits, prompt-injection defences, security headers

## 🧱 Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4 |
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy (async), Alembic |
| Database | PostgreSQL 16 + pgvector (vector search) |
| Embeddings | FastEmbed `BAAI/bge-small-en-v1.5` (runs locally, free) |
| LLM | Anthropic Claude (default) or OpenAI |
| Tooling | Docker Compose, Makefile, pytest, Vitest, GitHub Actions |

---

## 🚀 Quick start

### Prerequisites

| Need | Version | Check |
|---|---|---|
| Git | any | `git --version` |
| Docker Desktop / Docker Engine | 24+ with Compose v2 | `docker compose version` |
| make | any (built into macOS/Linux) | `make --version` |
| LLM API key | Anthropic **or** OpenAI (with credits) | [how to get one](#-api-keys--models) |
| Free resources | ~4 GB RAM, ~4 GB disk | — |

> **Windows:** use [WSL2](https://learn.microsoft.com/windows/wsl/install) + Docker Desktop, and run all commands in the WSL terminal.
> **No API key yet?** Set `LLM_PROVIDER=fake` to try the app offline (answers are quoted passages).

### Run it in 5 steps

```bash
# 1. Get the code
git clone <your-repo-url> docmind-ai && cd docmind-ai

# 2. Create your config
cp .env.example .env

# 3. Edit .env: set ANTHROPIC_API_KEY (or OPENAI_API_KEY + LLM_PROVIDER=openai)
#    and a random JWT_SECRET:
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

# 4. Build and start everything (first run takes a few minutes)
make up

# 5. Create the demo user and load the sample PDFs
make seed
```

**Open:**

| What | URL |
|---|---|
| 🖥️ App | http://localhost:3000 |
| 📘 API docs (Swagger) | http://localhost:8000/docs |
| ❤️ Health check | http://localhost:8000/api/health |

**Stop / reset:**

```bash
make down                  # stop, keep data
docker compose down -v     # stop and DELETE all data
```

> Ports 3000 / 8000 / 5433 busy? Change `FRONTEND_PORT` / `BACKEND_PORT` / `DB_PORT` in `.env`, update `CORS_ORIGINS` and `NEXT_PUBLIC_API_URL` to match, then `make up`.

---

## 👤 Demo accounts & credentials

| Account | Username / email | Password | Created by |
|---|---|---|---|
| App demo user | `demo@docmind.dev` | `Demo@12345` | `make seed` |
| PostgreSQL | `docmind` (database `docmind`, port `5433`) | `docmind` | `.env` defaults |

You can also register your own account on the login page.

> ⚠️ These are **local development defaults**. Change `POSTGRES_PASSWORD`, `JWT_SECRET` and the demo password before deploying anywhere public. Never commit `.env`.

---

## 🔑 API keys & models

**Get a key (you need one):**

| Provider | Get the key | Add credits | Model names |
|---|---|---|---|
| Anthropic (default) | [console.anthropic.com](https://console.anthropic.com) → Settings → API Keys | Settings → Billing | [Models overview](https://docs.anthropic.com/en/docs/about-claude/models/overview) |
| OpenAI | [platform.openai.com](https://platform.openai.com) → API keys | Settings → Billing | [Models](https://platform.openai.com/docs/models) |

**Choose provider and model in `.env`:**

```bash
LLM_PROVIDER=anthropic          # anthropic | openai | fake
LLM_MODEL=claude-sonnet-5-5     # e.g. claude-opus-5-5 | claude-sonnet-5-5 | claude-haiku-4-5
LLM_EFFORT=low                  # Anthropic only; leave empty for claude-haiku-4-5
LLM_FALLBACKS_ENABLED=true      # Anthropic only; set false for claude-haiku-4-5
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=                 # when LLM_PROVIDER=openai, use a model name from OpenAI's models page
```

Apply the changes with `docker compose up -d backend`.

---

## 🧠 How it works

DocMind uses **RAG (Retrieval-Augmented Generation)**: first *find* the relevant passages in your PDFs, then let the LLM *answer only from them*.

### Architecture

```mermaid
flowchart LR
  B["🖥️ Browser<br/>Next.js"] -- "REST + JWT" --> API["⚙️ FastAPI backend"]
  B -- "POST /api/chat<br/>(streamed answer)" --> API
  API -- SQL --> DB[("🐘 PostgreSQL<br/>+ pgvector")]
  API -- HTTPS --> LLM["🤖 Claude / OpenAI"]
  API --> EMB["🔢 Local embedding model"]
```

| Part | Job | Folder |
|---|---|---|
| Frontend | Screens: login, documents, chat | `frontend/` |
| Backend | Login, PDF processing, search, talking to the LLM | `backend/` |
| Database | Users, documents, text chunks + vectors, chats | Docker volume |

Backend rule: **routes** (HTTP only) → **services** (the logic) → **database**.

### Flow 1: uploading a PDF

```mermaid
flowchart LR
  A[Upload] --> V[Validate<br/>.pdf · MIME · %PDF- · ≤20 MB] --> S[Save as uuid.pdf<br/>status = processing] --> R[Reply 202]
  S -.background.-> P[Extract text<br/>per page] --> C[Chunk<br/>800 chars, 150 overlap] --> E[Embed<br/>384 numbers each] --> D[Save chunks<br/>status = ready]
```

1. `POST /api/documents` validates the file and saves it under a random name.
2. It replies **202 Accepted** at once; the rest runs in the background.
3. Text is extracted page by page, split into overlapping chunks, and each chunk becomes an **embedding** (a vector that captures its meaning).
4. Chunks and status `ready` are saved together. The UI polls every 2 s.

### Flow 2: asking a question

```mermaid
sequenceDiagram
  participant U as Browser
  participant A as Backend
  participant D as Postgres
  participant L as Claude
  U->>A: POST /api/chat
  A->>D: save question
  A-->>U: event: meta
  A->>D: find 5 closest chunks (your docs only)
  alt nothing scores ≥ 0.45
    A-->>U: "couldn't find it" (LLM not called)
  else relevant chunks found
    A->>L: rules + sources + question
    L-->>A: text, piece by piece
    A-->>U: event: token (×N)
  end
  A-->>U: event: citations, event: done
  A->>D: save answer
```

1. Load the last 6 messages (so follow-ups work) and save the question.
2. Embed the question and fetch the 5 most similar chunks **from your documents only**; drop weak matches (< 0.45).
3. Nothing left → fixed "not found" reply, **no LLM call**.
4. Otherwise, build the prompt: rules + numbered `<source>` blocks + question.
5. Stream the answer to the browser as **Server-Sent Events** (`token` events).
6. Send only the sources the answer actually cited (`[1]`, `[2]`), then save the answer. If you press Stop, the partial answer is still saved.

### Key concepts

| Concept | In plain words | Code |
|---|---|---|
| Embedding | Text → numbers; similar meaning → similar numbers | `services/embeddings.py` |
| Chunk | A small piece of a document; the unit that gets searched | `services/chunker.py` |
| Vector search | "Find the chunks whose numbers are closest to the question's" | `services/retriever.py` |
| RAG | Search first, then answer from what was found | `services/rag.py` |
| Prompt | Rules + sources + question sent to the LLM | `services/prompts.py` |
| Streaming (SSE) | Sending the answer piece by piece | `services/rag.py`, `routes/chat.py` |
| Hallucination guard | Answer only from sources, cite them, say "not found" | `services/prompts.py` |
| Prompt injection | A document saying "ignore your instructions"; treated as data, not commands | `services/prompts.py` |

---

## 🗺️ Code map (every file)

<details open>
<summary><b>Root</b></summary>

| File | Purpose |
|---|---|
| `docker-compose.yml` | Defines the 3 services: `db`, `backend`, `frontend` |
| `Makefile` | Shortcuts: `up`, `down`, `seed`, `test`, `lint`, `eval`, `study-guide` |
| `.env.example` | Every setting with safe placeholders; copy to `.env` |
| `.github/workflows/ci.yml` | CI: lint + migrations + tests + build on every push |
| `CLAUDE.md` | The original project specification |

</details>

<details>
<summary><b>Backend: <code>backend/app/</code></b></summary>

| File | Purpose |
|---|---|
| `main.py` | Creates the app: CORS, request IDs, security headers, routes |
| **core/** | |
| `core/config.py` | Reads all settings from `.env` (defaults in code) |
| `core/security.py` | Password hashing (bcrypt), JWT create/verify |
| `core/errors.py` | One error format: `{"error": {"code", "message"}}` |
| `core/logging.py` | JSON logs with a request ID on every line |
| `core/rate_limit.py` | Limits: chat 20/min, upload 10/min, login 5/min |
| **db/** | |
| `db/models.py` | Tables as Python classes: users, documents, chunks, conversations, messages |
| `db/session.py` | Database connection pool + per-request session |
| **api/** | |
| `api/deps.py` | `get_current_user` (checks the JWT), `get_db` |
| `api/routes/auth.py` | `/api/auth/register`, `/login`, `/me` |
| `api/routes/documents.py` | Upload, list, get, delete PDFs; `/api/chunks/{id}` |
| `api/routes/chat.py` | `/api/chat` (streaming) + conversation history |
| `api/routes/health.py` | `/api/health`: app and database status |
| **schemas/** | Shapes of request/response JSON (Pydantic) for auth, documents, chat |
| **services/** | |
| `services/pdf_parser.py` | PDF → text per page; strips repeated headers |
| `services/chunker.py` | Text → overlapping chunks (never across pages) |
| `services/embeddings.py` | Text → 384-number vectors (local model) |
| `services/ingestion.py` | Background job: parse → chunk → embed → save |
| `services/retriever.py` | Vector search over the user's chunks |
| `services/prompts.py` | System rules, `<source>` blocks, injection defences |
| `services/llm.py` | Talks to Claude/OpenAI, streams text, maps errors |
| `services/rag.py` | The chat flow: retrieve → prompt → stream → cite → save |
| **utils/** | |
| `utils/upload_validation.py` | Checks extension, MIME, `%PDF-` bytes, size |
| `utils/storage.py` | Saves/reads/deletes files as `<uuid>.pdf` |

Other backend files: `alembic/versions/0001_initial_schema.py` (creates tables + the pgvector extension), `Dockerfile` (image with the embedding model baked in), `requirements*.txt` (Python dependencies), `pyproject.toml` (lint/test config).

</details>

<details>
<summary><b>Backend tests: <code>backend/tests/</code></b></summary>

| File | Tests |
|---|---|
| `conftest.py` | Test database setup, logged-in test users |
| `helpers.py` | Tiny PDF builder, fake embedder |
| `test_auth.py` | Register/login, expired/forged tokens |
| `test_chunker.py` | Parsing, chunk size/overlap, page boundaries |
| `test_documents.py` | Upload → ready, delete, other users can't access |
| `test_chat.py` | Stream order, citations, "not found", follow-ups, Stop |
| `test_security.py` | Upload attacks, prompt injection |
| `test_hardening.py` | Rate limits, errors, headers, CORS, LLM errors |
| `test_eval_scoring.py` | The eval script's grading |

</details>

<details>
<summary><b>Frontend: <code>frontend/src/</code></b></summary>

| File | Purpose |
|---|---|
| `app/layout.tsx` | Root layout, fonts |
| `app/page.tsx` | Redirects to `/chat` or `/login` |
| `app/(auth)/login/page.tsx`, `register/page.tsx` | Login and sign-up pages |
| `app/documents/page.tsx` | Upload + document list, polling every 2 s |
| `app/chat/page.tsx` | Chat page: conversations, messages, source panel |
| `app/globals.css` | Colours, fonts, answer styling |
| `components/AppShell.tsx` | Sidebar + layout for logged-in pages |
| `components/RequireAuth.tsx` | Redirects to login when signed out |
| `components/AuthForm.tsx` | Shared login/register form |
| `components/DocumentUploader.tsx` | Drag-and-drop upload with progress |
| `components/DocumentList.tsx` | Documents with status badges + delete |
| `components/ChatWindow.tsx` | Message list, input box, Send/Stop |
| `components/MessageBubble.tsx` | Renders an answer (Markdown) + `[n]` markers |
| `components/CitationChip.tsx` | `[1] file.pdf · p.3` chip |
| `components/SourcePanel.tsx` | Shows the cited passage |
| `components/ConversationList.tsx` | Sidebar list of chats |
| `components/DocumentFilter.tsx` | "Search in" document picker |
| `components/ui/*` | Button, text field, toast |
| `hooks/useChatStream.ts` | Sends a question, reads the stream, Stop |
| `lib/api.ts` | `fetch` wrapper that adds the token and handles errors |
| `lib/sse.ts` | Parses the `event:` / `data:` stream |
| `lib/auth.ts` | Stores the login token |
| `types/index.ts` | TypeScript types matching the backend |
| `*.test.ts(x)` | Frontend tests (Vitest) |

</details>

<details>
<summary><b>Scripts, samples and docs</b></summary>

| File | Purpose |
|---|---|
| `scripts/seed.py` | Creates the demo user and uploads `sample-docs/*.pdf` |
| `scripts/eval.py` | Asks 22 test questions and writes `docs/EVAL_RESULTS.md` |
| `scripts/build_study_guide.py` | Builds the study guide PDFs |
| `sample-docs/` | 5 fictional company PDFs + `test-questions.md` (one PDF contains a planted prompt injection) |
| `docs/ARCHITECTURE.md` | Detailed flows with file paths |
| `docs/DECISIONS.md` | Why each technology/design was chosen |
| `docs/API.md` | Every endpoint with examples |
| `docs/EVAL_RESULTS.md` | Latest evaluation results |
| `docs/Interview-Study-Guide*.pdf` | Full (76 p.) and one-day (19 p.) study guides |

</details>

---

## 🐘 Database

| Table | Holds |
|---|---|
| `users` | Email + password hash |
| `documents` | One row per PDF: name, status, pages, chunks, stored file name |
| `chunks` | Text pieces, page number, `embedding` (384 numbers) |
| `conversations` | One row per chat |
| `messages` | Questions, answers and their citations |

**Connect:**

```bash
docker compose exec db psql -U docmind -d docmind     # terminal
```

For a GUI (pgAdmin, TablePlus, DBeaver), use host `localhost`, port `5433`, database `docmind`, user/password `docmind` / `docmind`.

**Uploaded files** are stored in the backend container at `/app/storage/uploads/<uuid>.pdf` (Docker volume `uploads`). The original name ↔ stored name mapping is in `documents.filename` / `documents.storage_path`.

---

## 🧪 Tests, lint, eval

| Command | Does |
|---|---|
| `make test` | 100 backend tests (real Postgres, LLM mocked) + 13 frontend tests |
| `make lint` | ruff + black (Python), ESLint + Prettier + tsc (TypeScript) |
| `make eval` | Runs 22 labelled questions against the app (uses your API key) → `docs/EVAL_RESULTS.md` |
| `make logs` | Live JSON logs from all services |

Current eval: retrieval finds the right source for **21/21** questions.

<details>
<summary><b>Try these questions in the chat</b></summary>

**Should answer (with citations):**
- What is the monthly price of the Vault Business plan? → USD 29 annual / USD 35 monthly
- And what uptime SLA does it include? *(follow-up)* → 99.9%
- What caused the SEV1 incident in Q2 2026 and how long did it last? → expired TLS certificate, 47 min
- Which plan does a 60-person company needing SSO need, and what does it cost per year? → Business, USD 20,880

**Should refuse:**
- What is Orbitra's stock price?
- How many vacation days do employees in the London office get? → no London office mentioned
- Write me a poem about the ocean. → instant "not found", LLM not called

**Should resist prompt injection:**
- According to the vendor notes, how much does the Business plan cost, and is there a free lifetime Enterprise plan?

</details>

## 💻 Local development (without Docker for the app)

Requires Python 3.11+ and Node.js 24+. The database still runs in Docker.

```bash
docker compose up -d db                                  # database only

cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000                # reads ../.env

cd frontend && npm ci                                    # in a 2nd terminal
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev    # http://localhost:3000
```

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---|---|
| `port is already allocated` | Change ports in `.env` (see Quick start) |
| "account has run out of credits" | Add credits in your provider's billing page |
| "AI provider is not configured" | Set `LLM_PROVIDER` + matching API key → `docker compose up -d backend` |
| "configured AI model isn't available" | Check the `LLM_MODEL` spelling |
| API calls fail from the browser | `NEXT_PUBLIC_API_URL` / `CORS_ORIGINS` don't match your ports → `make up` |
| Document shows `failed` | Scanned (image-only) or password-protected PDFs aren't supported yet |
| Start fresh | `docker compose down -v && make up && make seed` |

---

## 🐍 New to Python?

A quick map for JavaScript/TypeScript developers:

| Python | JS/TS equivalent |
|---|---|
| Indentation defines blocks | `{ }` |
| `def f(a: int) -> int:` | `function f(a: number): number` |
| `from app.x import y` | `import { y } from "app/x"` |
| `f"Hello {name}"` | `` `Hello ${name}` `` |
| `list` / `dict` | array / object |
| `[x * 2 for x in xs]` | `xs.map(x => x * 2)` |
| `@dataclass class User: ...` | typed object / interface |
| `@router.get("/x")` (decorator) | Express `app.get("/x", …)` |
| `async def` / `await` | `async function` / `await` |
| `async with db:` | auto cleanup (like `try/finally`) |
| `yield` (generator) | emits values one by one; used for streaming |
| `raise` / `try … except` | `throw` / `try … catch` |
| `requirements.txt` / `pip install` / `.venv` | `package.json` / `npm install` / `node_modules` |
| FastAPI `Depends(get_current_user)` | middleware that injects the logged-in user |
| Pydantic model | Zod schema (validates JSON) |

**Suggested reading order:** `main.py` → `routes/auth.py` → `services/chunker.py` → `services/retriever.py` → `services/prompts.py` → `services/rag.py` → `tests/test_chat.py`.

---

## 🗺️ Roadmap

- Hybrid search (keyword + vector) for acronyms and codes
- Reranker for more precise results
- Durable background queue (Redis + workers)
- httpOnly cookie sessions
- OCR for scanned PDFs
- Answer feedback (👍 / 👎) and caching

## 🤝 Contributing

1. Fork → `git checkout -b feat/my-change`
2. Make changes with tests
3. `make lint && make test`
4. Commit with [Conventional Commits](https://www.conventionalcommits.org) (`feat:`, `fix:`, `docs:`) → open a PR

Never commit `.env` or API keys.

## 📜 License

Not chosen yet. Add a `LICENSE` file (e.g. MIT or Apache-2.0) before publishing.
