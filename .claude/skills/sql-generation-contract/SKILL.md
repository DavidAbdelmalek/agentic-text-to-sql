---
name: sql-generation-contract
description: The binding contract for generating SQL in this repo — the semantic-layer format the agent reads, the hard read-only guardrails, row-limit and parameterization rules, Postgres-now / Snowflake-later dialect notes, and the bounded self-repair policy. Use whenever writing or reviewing the SQL-generation node, the guardrail, or any prompt that emits SQL.
---

# SQL Generation Contract

Every piece of SQL this system emits — by the agent at runtime or by a human/subagent —
obeys this contract. It exists so behavior is consistent and auditable, and so the agent
cannot hallucinate its way to an unsafe or wrong query.

## 1. Read only from the semantic layer
The generator's ONLY source of truth for tables/columns is `data/semantic/semantic_layer.yaml`
(produced by the `schema-explorer` subagent). Format per table:

```yaml
- name: fct_sales
  grain: "one row per order line"
  description: "Sales order lines for the DACH region."
  primary_key: [sales_key]
  foreign_keys:
    - { column: customer_key, references: dim_customer.customer_key }
    - { column: date_key,     references: dim_date.date_key }
  columns:
    - { name: net_amount_eur, type: numeric, is_measure: true,  description: "Net line revenue in EUR." }
    - { name: customer_key,   type: integer, is_fk: true,       description: "FK to dim_customer." }
  joinable_paths:
    - "fct_sales.customer_key = dim_customer.customer_key"
```

**Never reference an identifier not present in this file.** If the question needs data
that isn't there, return "insufficient schema" — do not invent columns.

## 2. Hard guardrails (non-negotiable)
- **Read-only**: exactly one statement; `SELECT`/CTE-to-SELECT or `EXPLAIN` only. No
  DDL/DML ever. Enforced three times: this contract, the `sql_guard` module, and the
  read-only Postgres role (the real backstop).
- **Row limit**: every row-returning query carries a `LIMIT` (default `SQL_DEFAULT_ROW_LIMIT`).
  Aggregates that collapse to few rows are exempt.
- **No unbounded scans**: no `SELECT *` on a fact table without an aggregate or a WHERE+LIMIT.
- **Parameterization**: user-supplied literals (dates, ids, names) bind as parameters, never
  string-concatenated into SQL — prevents injection and keeps EXPLAIN plans cacheable.
- **Statement timeout**: queries run under `SQL_STATEMENT_TIMEOUT_MS`.

## 3. Dialect
- **Now: Postgres.** Generate Postgres-valid SQL; validate with sqlglot(dialect="postgres").
- **Later: Snowflake.** Keep SQL ANSI where possible; isolate dialect specifics behind the
  DB client interface. Note divergences (e.g. `DATE_TRUNC`, `ILIKE`, identifier casing,
  `LIMIT` vs `TOP`) in comments rather than branching prompts.

## 4. Bounded self-repair policy
On an execution or guardrail error, the agent may reflect-and-repair, bounded:
- Max `SQL_MAX_REPAIR_RETRIES` attempts (default 2).
- Each retry MUST consume new information: the verbatim Postgres/guardrail error, fed back
  into generation. No blind re-rolls.
- A repair may only narrow scope or fix identifiers/syntax — never relax a guardrail.
- On exhaustion: stop, return a typed failure with the last error and attempted SQL. Never
  loop unbounded, never downgrade safety to force a result.
