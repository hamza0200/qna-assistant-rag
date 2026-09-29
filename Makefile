# DocMind AI — common tasks. Run `make help` for a list.
.DEFAULT_GOAL := help
COMPOSE := docker compose
BACKEND := $(COMPOSE) exec backend
# Frontend checks run in a Node container so only Docker is required. node_modules
# lives in an anonymous volume so Linux binaries never clobber a host install.
NODE := docker run --rm -v "$(CURDIR)/frontend:/app" -v /app/node_modules -w /app node:24-alpine sh -c

.PHONY: help up down logs migrate seed test test-backend test-frontend lint eval study-guide lockfile

help: ## Show available targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-15s %s\n", $$1, $$2}'

up: ## Build and start db, backend, frontend
	@test -f .env || (echo "Missing .env — run: cp .env.example .env" && exit 1)
	$(COMPOSE) up -d --build --wait

down: ## Stop all services (data volumes are kept)
	$(COMPOSE) down

logs: ## Tail logs from all services
	$(COMPOSE) logs -f --tail=100

migrate: ## Apply database migrations
	$(BACKEND) alembic upgrade head

seed: ## Create the demo user and ingest every PDF in sample-docs/
	$(BACKEND) python /scripts/seed.py

test: test-backend test-frontend ## Run all tests

test-backend: ## Run backend tests (inside the backend container)
	$(BACKEND) pytest -q -p no:cacheprovider

test-frontend: ## Run frontend tests (in a Node container)
	$(NODE) "npm ci --no-audit --no-fund --loglevel=error && npm test"

lint: ## Lint backend (ruff, black) and frontend (eslint, prettier)
	$(BACKEND) ruff check --no-cache app tests alembic
	$(BACKEND) ruff check --no-cache --config pyproject.toml /scripts
	$(BACKEND) black --check --config pyproject.toml app tests alembic /scripts
	$(NODE) "npm ci --no-audit --no-fund --loglevel=error && npm run lint && npm run format:check && npx tsc --noEmit"

eval: ## Run the evaluation set against the running API and write docs/EVAL_RESULTS.md
	$(BACKEND) python /scripts/eval.py

study-guide: ## Build docs/Interview-Study-Guide.pdf (in a small tools container)
	docker build -q -t docmind-study-guide -f scripts/study_guide.Dockerfile scripts >/dev/null
	docker run --rm -v "$(CURDIR):/work" docmind-study-guide python scripts/build_study_guide.py $(ARGS)

lockfile: ## Regenerate frontend/package-lock.json with the same npm as the Docker image
	docker run --rm -v "$(CURDIR)/frontend:/app" -w /app node:24-alpine npm install --package-lock-only --no-audit --no-fund
