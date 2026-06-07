# Canonical task runner (Linux/macOS/CI). Windows users: use ./tasks.ps1 <target>,
# which mirrors these targets. Every target is idempotent and re-runnable.
# The warehouse is Snowflake (cloud); credentials come from GENAI_DBT_SNOWFLAKE_* env vars.
.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help install provision verify-ro load dbt-build semantic drift \
        lint type test test-fast fmt eval eval-smoke run-api run-cli \
        docker-build docker-run ci clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Sync pinned deps (uv)
	uv sync --group dev

provision: ## Create Snowflake schemas + the read-only AGENT_RO role + grants
	uv run python scripts/snowflake_provision.py

verify-ro: ## Prove AGENT_RO can read + use Cortex but cannot write
	uv run python scripts/snowflake_verify_readonly.py

load: ## Download pinned UCI Online Retail II (HF) -> TTSQL_RAW
	uv run python -m agentic_text_to_sql.ingest

dbt-build: ## Build + test dbt models (raw -> star) on Snowflake
	cd dbt && uv run dbt deps && uv run dbt build

semantic: ## Regenerate semantic_layer.yaml from the dbt Semantic Layer + warehouse catalog
	cd dbt && uv run dbt docs generate
	uv run python scripts/generate_semantic_layer.py

lint: ## ruff lint
	uv run ruff check src tests

fmt: ## ruff format
	uv run ruff format src tests

type: ## mypy strict
	uv run mypy

test-fast: ## Unit tests only (mock mode, no warehouse)
	uv run pytest -m "not integration"

test: ## All tests (needs Snowflake creds for integration tests)
	uv run pytest

eval: ## Full gold-set eval, logged to Langfuse if configured (needs Snowflake)
	uv run python -m agentic_text_to_sql.eval

eval-smoke: ## CI smoke subset (mock mode if no warehouse)
	uv run python -m agentic_text_to_sql.eval --smoke

run-api: ## FastAPI server (dev; prod uses gunicorn in the container)
	uv run uvicorn agentic_text_to_sql.api:app --reload

run-cli: ## Ask a question from the CLI: make run-cli Q="..."
	uv run ttsql ask "$(Q)"

drift: ## Fail if the committed semantic layer is stale vs the dbt catalog (offline)
	uv run python scripts/generate_semantic_layer.py --check

docker-build: ## Build the API container image
	docker build -t agentic-text-to-sql .

docker-run: ## Run the API container. Mount the Snowflake key + pass creds for /ask to work.
	docker run --rm -p 8000:8000 --env-file .env agentic-text-to-sql

ci: lint fmt-check type drift test-fast ## What CI runs (offline)

fmt-check: ## ruff format check (CI)
	uv run ruff format --check src tests

clean: ## Remove caches + generated dbt artifacts
	rm -rf .ruff_cache .mypy_cache .pytest_cache dbt/target dbt/logs logs data/eval/results
