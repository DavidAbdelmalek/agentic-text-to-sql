# CLAUDE.md — project memory

Agentic **text-to-SQL**: a LangGraph agent that answers business questions over a **Snowflake**
star-schema warehouse by generating + executing **read-only** SQL, with the LLM running
**in-warehouse** (Snowflake Cortex), Langfuse tracing, and an automated eval harness.
Portfolio-grade, production-style.

> Read `docs/ARCHITECTURE.md` for the graph + diagram and `docs/DECISIONS.md` for the "why"
> behind every non-obvious choice. This file is the orientation; those are the depth.

> **History:** the project was first built on Postgres (8 phases) and then **fully pivoted to
> Snowflake + Cortex**. `docs/DECISIONS.md` D17–D20 record the pivot; the older decisions are
> kept for the evolution story, marked where superseded.

## Architecture (one screen)
`generate SQL → guardian validate + EXPLAIN → execute via read-only role → bounded reflect/repair
(max N) → summarize`. The full schema (5-table star) is sent on every generation — at this size
retrieval can only drop a needed table, and the identifier guard is the real anti-hallucination
control, so there is no classify/retrieve node. Every node traced in Langfuse. Headline design
points: the **read-only guardrail**, the **bounded repair loop**, and the **refusal** behaviour
(it declines unanswerable questions instead of inventing a proxy).

## The read-only access model (most important thing here)
The agent connects ONLY as the `AGENT_RO` Snowflake role: `SELECT` + `SNOWFLAKE.CORTEX_USER`,
**no** DDL/DML. Created by `scripts/snowflake_provision.py` (or `terraform/snowflake`).
Defense-in-depth:
1. prompt/contract (`sql-generation-contract` skill) — can fail open
2. `sql_guard` module + `sql-guardian` subagent (sqlglot + EXPLAIN) — can fail open
3. the read-only role — **cannot** fail open; Snowflake rejects writes
An LLM-driven query agent must never hold write access — a prompt is not a control; a revoked
privilege is. The same read-only role runs the Cortex LLM, so the agent can read and *think*,
never write, and no data leaves the warehouse.

## Subagents (`.claude/agents/`) — use them during the build
- **schema-explorer** — introspects the warehouse and maintains the dbt Semantic Layer /
  semantic layer. Delegate schema work here.
- **sql-guardian** — reviews generated SQL for safety + runs EXPLAIN; rejects/repairs.
- **eval-runner** — runs the gold-set eval and reports execution accuracy + scores.
- **test-author** — writes/extends pytest unit + integration tests.

## Skills (`.claude/skills/`)
- **sql-generation-contract** — semantic-layer format, hard guardrails (read-only, row limits,
  Snowflake dialect notes), bounded self-repair + refusal policy. Load when writing/reviewing
  any SQL-emitting code.
- **eval-methodology** — gold-set format, execution-accuracy scoring + failure modes, retrieval
  correctness, offline/mock mode. Load when touching the eval harness.

## The semantic layer is generated
`data/semantic/semantic_layer.yaml` is a **generated artifact**, not hand-authored.
`scripts/generate_semantic_layer.py` merges the **dbt Semantic Layer**
(`dbt/models/marts/_semantic_models.yml` — entities/measures/dimensions/metrics) with the
**warehouse catalog** (`dbt/target/catalog.json`). Edit the dbt sources, then `make semantic`.
`--check` is a CI drift gate. The generated YAML both grounds the generator and feeds the
guard's allowed-identifier set.

## How to run
```bash
cp .env.example .env                 # Snowflake creds via GENAI_DBT_SNOWFLAKE_* env vars (key-pair)
make install                         # uv sync (pinned deps)
make provision                       # Snowflake schemas + read-only AGENT_RO role + grants
make load && make dbt-build          # load real UCI Online Retail II -> dbt star (Kimball)
make semantic                        # regenerate the semantic layer from dbt + warehouse catalog
make run-cli Q="..."                 # ask a question (Cortex)
make eval                            # gold-set eval (live)
make ci                              # ruff + format + mypy + unit tests (offline, mock)
```
Windows (no `make`): `./tasks.ps1 <target>` mirrors every target. OneDrive locks the venv mid
`uv sync` — use `uv run --no-sync`, and repair a broken venv with `uv pip install --reinstall
certifi`.

## Models
LLM = **Snowflake Cortex** (`SNOWFLAKE.CORTEX.COMPLETE`), default `mistral-large2` (in-region,
EU). Claude is reachable via cross-region inference (`claude-4-sonnet`). The provider is
pluggable (`llm_provider`): `cortex` | `anthropic` | `openai` | `azure` | `mock`. The
deterministic `MockLLM` runs the whole graph offline (no warehouse, no key) — the CI path.

## Conventions
- Python 3.11+, `uv`, pinned deps. `ruff` (lint+format), `mypy --strict`, `pytest`.
- All env access via `src/agentic_text_to_sql/config.py` (`get_settings()`), never raw
  `os.environ`. Secrets only in `.env` (gitignored); `.env.example` is the template.
- Warehouse access only through `db/read_only_client.py` (which uses `db/snowflake.py`). No
  module connects to Snowflake directly.
- Generated SQL must reference only identifiers in the semantic layer.

## Data
Warehouse = **UCI Online Retail II** (real UK/EU e-commerce invoices, 2009–2011, CC BY 4.0),
loaded from a pinned Hugging Face revision into `TTSQL_RAW` by `make load`
(`src/.../ingest.py`, `write_pandas`), then dbt-modeled into the star in `TTSQL`: `fct_sales`
(invoice lines, GBP), `dim_customer`, `dim_product`, `dim_country` (DACH/Europe/RoW rollup),
`dim_date`. Currency is **GBP**; there is **no** cost/margin or sales-rep data — which is why
the agent must *refuse* questions about them. The read-only role reads the marts in `TTSQL`,
never `TTSQL_RAW`.

## Status
Built on Postgres across 8 phases (LangGraph agent, read-only role, semantic layer, Langfuse,
eval, Terraform, docs), then **pivoted to Snowflake + Cortex**: in-warehouse Cortex LLM, read-only
`AGENT_RO` role, dbt models in Snowflake dialect, lean graph (classify/retrieve removed),
few-shot prompt + `CANNOT_ANSWER` refusal, and a semantic layer generated from the dbt Semantic
Layer + warehouse catalog. CI is offline (ruff/format/mypy/mock unit tests); 54 unit tests green.
Open: docs/DECISIONS detail, and re-running the full live eval for a Cortex accuracy number.
