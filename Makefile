# DocMind AI — common tasks. Run `make help` for a list.
.DEFAULT_GOAL := help
COMPOSE := docker compose
BACKEND := $(COMPOSE) exec backend

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

test-frontend: ## Run frontend tests
	cd frontend && npm test

lint: ## Lint backend (ruff, black) and frontend (eslint, prettier)
	$(BACKEND) ruff check app tests alembic
	$(BACKEND) black --check app tests alembic
	cd frontend && npm run lint && npm run format:check

eval: ## Run the evaluation set against the running API and write docs/EVAL_RESULTS.md
	$(BACKEND) python /scripts/eval.py

study-guide: ## Build docs/Interview-Study-Guide.pdf
	$(BACKEND) python /scripts/build_study_guide.py

lockfile: ## Regenerate frontend/package-lock.json with the same npm as the Docker image
	docker run --rm -v "$(CURDIR)/frontend:/app" -w /app node:24-alpine npm install --package-lock-only --no-audit --no-fund
