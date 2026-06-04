# Canonical task runner (Linux/macOS/CI). Windows users: use ./tasks.ps1 <target>,
# which mirrors these targets. Every target is idempotent and re-runnable.
.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help install up down logs psql load dbt-build introspect semantic \
        lint type test test-fast fmt eval eval-smoke run-api run-cli ci clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Sync pinned deps + dev/local-llm extras (uv)
	uv sync --all-extras --group dev

up: ## Start Postgres + pgvector (one command)
	docker compose up -d
	@echo "waiting for warehouse healthy..." && \
	  until docker compose exec -T warehouse pg_isready -U $${POSTGRES_SUPERUSER:-postgres} >/dev/null 2>&1; do sleep 1; done
	@echo "warehouse ready."

down: ## Stop containers (keeps volume)
	docker compose down

logs: ## Tail warehouse logs
	docker compose logs -f warehouse

psql: ## Open a read-only psql shell as the agent role
	psql "$${AGENT_DATABASE_URL:-postgresql://agent_ro:agent_ro_pw@localhost:5432/warehouse}"

load: ## (Phase 2) Download pinned UCI Online Retail II (HF) -> raw schema
	uv run python -m agentic_text_to_sql.ingest

dbt-build: ## (Phase 2) deps + build + test dbt models (raw -> star) against Postgres
	cd dbt && uv run dbt deps && uv run dbt build

introspect: ## (Phase 3 fallback) Dump raw schema to data/semantic/raw_schema.json
	uv run python scripts/introspect_schema.py

semantic: ## (Phase 3) Refresh the semantic layer (delegated to schema-explorer)
	uv run python -m agentic_text_to_sql.semantic_layer.build

lint: ## ruff lint
	uv run ruff check src tests

fmt: ## ruff format
	uv run ruff format src tests

type: ## mypy strict
	uv run mypy

test-fast: ## Unit tests only (no DB)
	uv run pytest -m "not integration"

test: ## All tests (needs DB up)
	uv run pytest

eval: ## (Phase 6) Full gold-set eval, logged to Langfuse if configured
	uv run python -m agentic_text_to_sql.eval

eval-smoke: ## (Phase 6) CI smoke subset (mock mode if no LLM key)
	uv run python -m agentic_text_to_sql.eval --smoke

run-api: ## (Phase 5) FastAPI server
	uv run uvicorn agentic_text_to_sql.api:app --reload

run-cli: ## (Phase 5) Ask a question from the CLI: make run-cli Q="..."
	uv run ttsql ask "$(Q)"

ci: lint type test-fast ## What CI runs on the fast path

clean: ## Remove caches + generated artifacts (NOT the DB volume)
	rm -rf .ruff_cache .mypy_cache .pytest_cache dbt/target dbt/logs \
	  data/semantic/raw_schema.json data/eval/results
