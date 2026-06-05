# CLAUDE.md — project memory

Agentic **text-to-SQL**: a LangGraph agent that answers business questions over a Postgres
star-schema warehouse by generating + executing **read-only** SQL, with Langfuse tracing
and an automated eval harness. Portfolio-grade, production-style, runs locally and free.

> Read `docs/ARCHITECTURE.md` for the graph + diagram and `docs/DECISIONS.md` for the "why"
> behind every non-obvious choice. This file is the orientation; those are the depth.

## Architecture (one screen)
`classify → retrieve schema (pgvector over the semantic layer) → generate SQL → guardian
validate + EXPLAIN → execute via read-only role → bounded reflect/repair (max N) →
summarize`. Every node traced in Langfuse. Headline design points: the **read-only
guardrail** and the **bounded repair loop**.

## The read-only access model (most important thing here)
The agent connects ONLY as the `agent_ro` Postgres role: `SELECT` + `EXPLAIN`, **no**
DDL/DML. Created in `docker/initdb/02-create-readonly-role.sh`. Defense-in-depth:
1. prompt/contract (`sql-generation-contract` skill) — can fail open
2. `sql_guard` module + `sql-guardian` subagent (sqlglot + EXPLAIN) — can fail open
3. the read-only role — **cannot** fail open; the engine rejects writes
An LLM-driven query agent must never hold write access — a prompt is not a control; a
revoked privilege is.

## Subagents (`.claude/agents/`) — use them during the build
- **schema-explorer** — introspects the DB (postgres-ro MCP, or `make introspect` fallback)
  and produces/refreshes `data/semantic/semantic_layer.yaml`. Delegate all schema work here.
- **sql-guardian** — reviews generated SQL for safety + runs EXPLAIN; rejects/repairs.
  Review any SQL before it runs with this agent.
- **eval-runner** — runs the gold-set eval and reports execution accuracy + scores.
- **test-author** — writes/extends pytest unit + integration tests for new modules.

## Skills (`.claude/skills/`)
- **sql-generation-contract** — semantic-layer format, hard guardrails (read-only,
  parameterization, row limits, Postgres/Snowflake dialect notes), bounded self-repair
  policy. Load when writing/reviewing any SQL-emitting code.
- **eval-methodology** — gold-set format, execution-accuracy scoring + failure modes,
  retrieval correctness, offline/mock mode. Load when touching the eval harness.

## MCP
`.mcp.json` defines `postgres-ro` (read-only, `--access-mode=restricted`) for dev schema
introspection. Approve it via `/mcp` on first use (project MCP is not auto-trusted; we keep
`enableAllProjectMcpServers: false`). If it can't run non-interactively, use `make introspect`.

## How to run
```bash
cp .env.example .env          # defaults run locally + free, no keys needed
make install                  # uv sync (pinned deps)
make up                       # Postgres + pgvector + read-only role
make load && make dbt-build   # Phase 2: load real UCI Online Retail II -> dbt star (Kimball)
make semantic                 # Phase 3: build the semantic layer
make run-cli Q="..."          # ask a question (Phase 5)
make eval                     # Phase 6: gold-set eval
make ci                       # lint + type + unit tests (CI fast path)
```
Windows (no `make`): `./tasks.ps1 <target>` mirrors every target.

## Conventions
- Python 3.11+, `uv`, pinned deps. `ruff` (lint+format), `mypy --strict`, `pytest`.
- All env access via `src/agentic_text_to_sql/config.py` (`get_settings()`), never raw
  `os.environ`. Secrets only in `.env` (gitignored); `.env.example` is the template.
- DB access only through `db/read_only_client.py`. No module connects to Postgres directly.
- Generated SQL must reference only identifiers in the semantic layer.

## Data
Warehouse = **UCI Online Retail II** (real UK/EU e-commerce invoices, 2009–2011, CC BY 4.0),
loaded from a pinned Hugging Face revision into a `raw` schema by `make load`
(`src/.../ingest.py`), then dbt-modeled into the star: `fct_sales` (≈805k invoice lines, GBP),
`dim_customer`, `dim_product`, `dim_country` (DACH/Europe/RoW rollup), `dim_date`. Currency
is **GBP**; no cost/margin or sales-rep fields exist in this source (revenue-focused model).
The agent's read-only role is granted on `public` only — it can read the marts, never `raw`.

## Build status
Phase 1 done: permissions, read-only role + docker, MCP, subagents, skills, skeleton, CI.
Phase 2 done: real-data ingest, dbt star schema + 42 passing tests, read-only role verified.
Phase 3 done: introspection (`make introspect`) -> semantic_layer.yaml (authored by the
schema-explorer subagent) -> pgvector store (`make semantic`); retriever with vector
(fastembed/pgvector) + deterministic keyword backends; test-author wrote loader/retriever tests.
Phase 4 done: LangGraph agent (classify -> retrieve -> generate -> guard[sqlglot + EXPLAIN] ->
execute[read-only] -> bounded reflect/repair -> summarize). LLM providers (Ollama/OpenAI/Azure
+ deterministic MockLLM). sql_guard + read-only client implemented; `ttsql ask "..."` runs it
live; 36 tests (guardrail rules, bounded loop, read-only refusal). Runs offline via mock.
Phase 5 done: Langfuse tracing (callback handler, no-op without keys) on every node; self-host
via `make obs-up` (compose observability profile, headless-seeded keys); FastAPI `POST /ask`.
Phase 6 done: eval harness (18-Q gold set, `make eval` / `make eval-smoke`). Execution accuracy
(multiset compare, primary) + structural similarity (secondary) + retrieval correctness; logs
3 scores/question to Langfuse; offline mock mode; CI smoke gate (mock + keyword, exec_acc==1.0).
55 tests total.
Phase 7 done: Terraform — `terraform/postgres` (read-only role as IaC, alt to the init script)
+ `terraform/snowflake` (documented cloud read-only variant). Both `terraform validate` clean.
Phase 8 (docs/README polish + deprecation cleanup) remains.
