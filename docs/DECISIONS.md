# Architecture Decision Log

Each entry: **Context / Decision / Alternatives considered / Trade-offs**. Entries are appended as the project is built.

---

## ADR-001 — Repository root is the project root

**Context.** The spec's folder tree is rooted at `docmind-ai/`, but the repository was created as `qa-assistant/` with `CLAUDE.md` already at its root.
**Decision.** Treat the repository root as `docmind-ai/`; every path in the spec maps 1:1 onto the repo root.
**Alternatives considered.** Nesting everything under a `docmind-ai/` subfolder.
**Trade-offs.** Nesting would add a pointless level to every command (`cd docmind-ai && make up`) and split `CLAUDE.md` from the code it describes.

## ADR-002 — Configurable host ports

**Context.** Ports 5432, 8000 and 3000 are commonly in use on developer machines (they were on the build machine).
**Decision.** `docker-compose.yml` maps host ports from `DB_PORT`, `BACKEND_PORT`, `FRONTEND_PORT` (defaults 5433/8000/3000). Postgres defaults to 5433 on the host to avoid clashing with a local Postgres.
**Alternatives considered.** Hard-coded ports.
**Trade-offs.** Three more env vars, and `CORS_ORIGINS` / `NEXT_PUBLIC_API_URL` must be kept in sync with the chosen ports (documented in `.env.example`).

## ADR-003 — `bcrypt` directly instead of `passlib`

**Context.** The spec allows `passlib`/`bcrypt`. `passlib` is unmaintained (last release 2020) and emits errors against `bcrypt>=4.1`.
**Decision.** Call the `bcrypt` library directly in `backend/app/core/security.py`.
**Alternatives considered.** `passlib[bcrypt]` with a pinned old `bcrypt`; `argon2-cffi` (Argon2id, the current OWASP first choice).
**Trade-offs.** No algorithm-agility helpers from passlib (we would have to add rehash-on-login ourselves if we migrate to Argon2). bcrypt truncates passwords at 72 bytes, so we reject longer passwords explicitly.

## ADR-004 — Implied driver/adapter dependencies

**Context.** The fixed stack implies a few packages it doesn't name.
**Decision.** Added `asyncpg` (the async Postgres driver SQLAlchemy async needs), `pgvector` (Python adapter giving SQLAlchemy a `Vector` column type), `email-validator` (backs Pydantic's `EmailStr`). SSE is written by hand on `StreamingResponse` rather than adding `sse-starlette`.
**Alternatives considered.** `psycopg` 3 async; raw SQL for vector columns.
**Trade-offs.** asyncpg is the fastest and most common async driver; the SSE wire format is ~5 lines so a library adds little.

## ADR-005 — Tailwind CSS v4 (CSS-first config)

**Context.** The spec lists `tailwind.config.ts`, but the current `create-next-app` installs Tailwind v4, which configures themes in CSS (`@theme`) and no longer needs a JS config file.
**Decision.** Use Tailwind v4 with its CSS-first configuration in `src/app/globals.css`; no `tailwind.config.ts`.
**Alternatives considered.** Pin Tailwind v3 to match the spec literally.
**Trade-offs.** Deviates from the spec's file list but follows the tool's current default; pinning an old major version would be the less defensible choice.

## ADR-006 — Next.js standalone output and build-time API URL

**Context.** The browser calls the FastAPI backend directly. `NEXT_PUBLIC_*` variables are inlined into the JS bundle at `next build`.
**Decision.** `output: "standalone"` for a small runtime image; `NEXT_PUBLIC_API_URL` passed as a Docker build arg.
**Alternatives considered.** Proxying `/api/*` through Next.js rewrites (same origin, no CORS); a runtime `/config` endpoint.
**Trade-offs.** One image per environment (the URL is baked in). A Next proxy would remove CORS but adds a hop and can buffer SSE streams.
