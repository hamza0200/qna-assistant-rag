# 13. DevOps and workflow

## Docker and Compose

- **Image** = a read-only template (filesystem + metadata); **container** = a running instance. Images are built in **layers**; each Dockerfile instruction adds one, and unchanged layers are cached — so copy dependency manifests and install them *before* copying source code.
- **Compose** describes a multi-container app: DocMind's `docker-compose.yml` defines `db` (pgvector/pgvector:pg16 with a `pg_isready` healthcheck and a named volume), `backend` (waits for a healthy DB, runs `alembic upgrade head`, then uvicorn; its own HTTP healthcheck) and `frontend`. Services reach each other by name (`db:5432`). `make up` = `docker compose up -d --build --wait`.
- **Volumes** persist data beyond container lifetimes (`pgdata`, `uploads`); bind mounts share host folders (`./scripts`, `./sample-docs` read-only into the backend for `make seed`/`make eval`).

## Multi-stage builds

```dockerfile
FROM python:3.12-slim AS builder
RUN python -m venv /opt/venv && pip install -r requirements.txt
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/models')"

FROM python:3.12-slim AS runtime
RUN useradd --create-home --uid 1000 app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/models /opt/models
USER app
```

The runtime stage gets only the built artefacts — no compilers, caches or build tools — so it's smaller and has less attack surface; it runs as a **non-root user**. The frontend does the same with Next's standalone output. DocMind bakes the embedding model into the image: fast startup, works offline, identical model on every replica.

## Environment configuration

12-factor: config in the environment, not in code. `.env.example` documents every variable with safe placeholders; `.env` is git-ignored; `pydantic-settings` validates types at startup. Remember build-time vs run-time: `NEXT_PUBLIC_API_URL` is baked into the frontend bundle during `docker build`, while backend variables are read at start. Per environment: different `.env`/secret-manager values, same image (except the frontend URL).

## CI/CD with GitHub Actions

`.github/workflows/ci.yml` runs on every push/PR, with two parallel jobs:

- **backend:** Python 3.12 with pip cache → ruff + black → `alembic upgrade head` + `alembic check` against a `pgvector/pgvector:pg16` **service container** → `pytest`.
- **frontend:** Node 24 with npm cache → `npm ci` → ESLint → Prettier check → `tsc --noEmit` → Vitest → `next build`.

**CD** (next step): on merge to `main`, build and push images tagged with the commit SHA to a registry (GHCR/ECR), deploy to staging, run smoke tests (`/api/health`, a scripted chat with the fake provider), then promote to production — with migrations run as a separate step before the new version takes traffic.

A CI-only failure story from this project: an incremental `npm install` on the host's newer npm produced a lockfile that `npm ci` inside the Node container rejected (missing optional WebAssembly packages). Fix: regenerate the lockfile with the same npm as the image (`make lockfile`).

## Git branching strategies

- **Trunk-based development:** short-lived branches (hours to a day) merged to `main` behind CI; incomplete features hidden with feature flags. Best for continuous delivery and small teams — what most modern teams use.
- **GitHub Flow:** branch → PR → review → merge → deploy. Trunk-based in practice.
- **Git Flow:** long-lived `develop`, `release/*`, `hotfix/*` branches. Suits versioned software with scheduled releases; heavy for web apps.

## Conventional Commits

`type(scope): summary` — `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`, `ci:`; `!` or `BREAKING CHANGE:` for majors. Benefits: readable history, automatic changelogs and semantic version bumps (semantic-release, release-please). DocMind has one commit per build phase, e.g. `feat: retrieval, streaming RAG chat over SSE with citations and chat UI`.

## Code review practices

- Small PRs with a clear description (what, why, how tested, screenshots for UI).
- Automate the nitpicks (formatters, linters, type checks in CI) so humans review design, correctness, security and tests.
- Review for: correctness and edge cases, authorization on every new query, error handling, test coverage of the change, naming and clarity, performance traps (N+1, blocking the event loop), secrets or PII in code/logs.
- Be specific and kind; separate blocking issues from suggestions ("nit:"); approve when it's better than before, not perfect.

## Deploying to the cloud (high level)

| Component | AWS | GCP | Azure | Simpler option |
|---|---|---|---|---|
| Frontend | CloudFront + S3 / Amplify | Cloud Run + Cloud CDN / Firebase Hosting | Static Web Apps | **Vercel** (native Next.js) |
| Backend containers | ECS Fargate / App Runner / EKS | **Cloud Run** / GKE | Container Apps / AKS | Fly.io, Render, Railway |
| Postgres + pgvector | RDS / Aurora PostgreSQL | Cloud SQL / AlloyDB | Azure Database for PostgreSQL | Supabase, Neon |
| Files | S3 | Cloud Storage | Blob Storage | — |
| Queue | SQS | Pub/Sub / Cloud Tasks | Service Bus | Redis |
| Secrets | Secrets Manager | Secret Manager | Key Vault | platform env vars |

A pragmatic first production deployment for DocMind: frontend on Vercel, backend on Cloud Run or ECS Fargate (min instances ≥ 1 to avoid cold-loading the embedding model; request timeout long enough for streams), managed Postgres with pgvector, S3 for files, secrets from the platform's secret manager, TLS everywhere.
