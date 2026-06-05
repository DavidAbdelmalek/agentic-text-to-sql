# Agentic Text-to-SQL

> A **safe, observable, evaluated** SQL agent: ask a business question in plain English,
> get an answer backed by **read-only** SQL it generated, validated, and ran — with full
> tracing and an automated accuracy eval. Built with production data-engineering discipline.

**What this proves in 60 seconds**
- **Agentic GenAI** — a multi-step **LangGraph** agent (classify → retrieve schema →
  generate SQL → validate → execute → bounded repair → summarize), not a single prompt.
- **Safety by construction** — the agent can only ever *read*: a dedicated **read-only
  Postgres role** is the hard boundary, with a sqlglot + `EXPLAIN` guardrail in front.
- **It's measured, not a demo** — an **execution-accuracy** eval over a curated gold set,
  logged to **Langfuse** and run as a CI smoke gate.
- **Real data engineering underneath** — real **UCI Online Retail II** data, cleaned and
  modeled into a **star schema** with **dbt** (Kimball), provisioned with **Terraform**,
  one-command Dockerized, **free**.

```
question ─▶ classify ─▶ retrieve schema ─▶ generate SQL ─▶ guardian (sqlglot + EXPLAIN)
                                                              │ approve
                                                              ▼
        summarize ◀─ execute (READ-ONLY role) ◀──────────────┘
              ▲              │ error
              └── reflect & repair (max N, bounded) ──┘
```
Full diagram: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Every design trade-off:
[`docs/DECISIONS.md`](docs/DECISIONS.md).

## The safety model (the headline)
| Layer | Mechanism | Can it fail open? |
|---|---|---|
| 1. Contract | prompt + `sql-generation-contract` skill: one read-only SELECT | yes (prompts can be bypassed) |
| 2. Guardrail | `sql_guard`: single-statement, no DDL/DML, identifiers resolve, LIMIT, `EXPLAIN` | yes (parser gaps) |
| 3. **DB role** | agent connects as `agent_ro` — `SELECT`/`EXPLAIN`, **no** write grants | **no — engine rejects writes** |

An LLM emits arbitrary text, so the only trustworthy control is a **revoked privilege**.
Layers 1–2 are fast, explainable filters; layer 3 is the wall.

## Quickstart (local, free, one command-ish)
```bash
cp .env.example .env     # defaults: local Ollama LLM + local embeddings, no API keys
make install             # uv sync, pinned deps (Python 3.11+)
make up                  # Postgres 16 + pgvector + read-only role (docker compose)
make load && make dbt-build   # load real UCI data -> dbt star schema (~805k fact rows), tested
make semantic            # build the semantic layer (anti-hallucination ground truth)
make run-cli Q="Top 5 countries by revenue in 2011"
make run-api             # FastAPI: POST /ask {"question": "..."}  (http://localhost:8000)
make eval                # execution-accuracy eval over the gold set

make obs-up              # optional: self-hosted Langfuse tracing UI (http://localhost:3000)
```
Every agent run traces each node (classify → retrieve → generate → guard → execute → repair →
summarize) to Langfuse when keys are set — see exactly what SQL was generated and how many
repair loops ran, per question.
On Windows without `make`: use `./tasks.ps1 <target>`. Cloud LLM? Set `LLM_PROVIDER` +
keys in `.env` (OpenAI/Azure). No key at all? Eval still runs in deterministic **mock mode**.

## Evaluation
Primary metric: **execution accuracy** (does the agent's result set match the reference?),
plus SQL structural similarity (diagnostic) and retrieval correctness (right tables?).
Methodology + failure modes: [`eval-methodology` skill](.claude/skills/eval-methodology/SKILL.md).

18-question gold set; `make eval` (or `make eval-smoke` for the CI subset). Numbers below are
the **deterministic mock baseline** (no LLM key) — they validate the harness + scoring, not a
model. Set `LLM_PROVIDER=ollama|openai|azure` for real model accuracy across the full set.

| Run | Execution accuracy | Retrieval ok-rate | Mean struct. sim |
|---|---|---|---|
| Smoke subset (mock, CI gate) | **1.00** (6/6) | 1.00 | 0.997 |
| Full set (mock baseline) | 0.33 (6/18) | 0.89 | 0.75 |

The mock only knows ~6 query patterns, so the full-set mock score is expected to be low — that
gap is what a real model closes. Note q14 scored 0.91 structural similarity yet **failed**
execution accuracy — exactly why structural similarity is a secondary diagnostic, never a gate.
Every run logs `execution_accuracy`, `retrieval_recall`, and `structural_similarity` to Langfuse.

## Tech stack
Python · LangGraph · LangChain · Langfuse · Postgres + pgvector · dbt (dbt-postgres;
dbt-snowflake variant) · Terraform · FastAPI + Typer CLI · GitHub Actions (ruff, mypy,
pytest, dbt build, smoke eval) · uv.

## Repo layout
```
src/    agent graph + nodes, semantic_layer, sql_guard, read-only db client, eval, api, cli
dbt/    Kimball star schema + tests        terraform/  local + Snowflake read-only variant
docker/ Postgres init: extensions + read-only role     data/  seed · semantic layer · gold set
.claude/ permissions · subagents · skills  .mcp.json  read-only Postgres MCP for introspection
docs/   ARCHITECTURE.md · DECISIONS.md      tests/  pytest unit + integration
```

## How it's built
Claude Code drives this repo as a structured multi-agent workflow with **scoped**
permissions (no blanket allow), four single-responsibility **subagents** (schema-explorer,
sql-guardian, eval-runner, test-author), and two **skills** encoding the SQL contract + eval
method. See [`CLAUDE.md`](CLAUDE.md). Built in reviewed phases; current status there.

_Data: UCI **Online Retail II**, UCI Machine Learning Repository, licensed **CC BY 4.0**.
Loaded from a pinned Hugging Face revision; not redistributed in this repo._
