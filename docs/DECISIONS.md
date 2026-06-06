# Design decisions (the "why" log)

Every non-obvious choice, with the trade-off. This is the interview cheat-sheet. Each entry is
something I should be able to defend out loud.

The project was first built on Postgres (D1 to D16), then moved to Snowflake with in-warehouse
Cortex LLMs (D17 to D20). I kept the Postgres-era entries so the evolution is visible, and added
a "superseded" note where the move changed something. The principles all survived the move:
read-only role, EXPLAIN before execute, a bounded repair loop, execution-accuracy as the metric,
and grounding the model in a generated semantic layer.

## D17: Move to Snowflake with in-warehouse Cortex LLMs

I have a Snowflake account, so the warehouse moved off local Postgres onto Snowflake, and the
LLM moved into the warehouse through Snowflake Cortex (`COMPLETE`). The agent connects only as
the read-only `AGENT_RO` role, which has `SELECT` plus `CORTEX_USER`. That one role both reads
the data and runs the model, so no rows leave Snowflake and there is no external API key. The
default model is `mistral-large2` (in-region, EU); Claude is reachable through cross-region
inference (`claude-4-sonnet`). The provider stays pluggable (OpenAI, Anthropic, mock) behind the
same `LLM` interface, so the same graph can compare model backends.

Trade-off: Cortex's model menu depends on the region (no local Claude in eu-central without
cross-region), and CI can no longer spin up a free containerised database, so CI is now offline
and mock-only (see D19). The read-only boundary from D2 ports directly: a Snowflake role with no
write or DDL grants. This supersedes the Postgres specifics of D2, D7, D10, and D13.

## D18: Lean graph: drop classify and retrieve, send the full schema

For a fixed five-table star, dynamic retrieval is a net loss. With k close to the number of
tables it returns almost the whole schema anyway, and on the questions where it does drop a
table, it drops the fact table (which scores low when the question is phrased in dimension
terms), which then forces a repair cycle. The `classify` node was dead code; nothing downstream
read `question_class`. So I removed both nodes. The full schema is rendered once and sent on
every generation. Hallucination is still caught by the guard's identifier check, not by
retrieval.

Trade-off: I lose a "retrieval stage" talking point. I think the honest replacement is stronger:
retrieval is a scale tool, and at five tables it only hurts. The keyword retriever stays behind
the `Retriever` interface as the eval's retrieval-scoring target and as the documented swap-in
once the warehouse grows. This supersedes D12 (the pgvector retriever) as the runtime path.

## D19: Generate the semantic layer from the dbt Semantic Layer plus the warehouse catalog

The agent's `semantic_layer.yaml` used to be hand-maintained, which means it drifts from the
models. It is now generated. `scripts/generate_semantic_layer.py` merges two sources: the dbt
Semantic Layer (`_semantic_models.yml`, which carries entities for keys and joins, measures for
additivity, dimensions, and grain) and the warehouse catalog (`catalog.json`, the full column
list with types). The dbt Semantic Layer is the standard home for these semantics, the same
definitions a BI tool or MetricFlow would read, so nothing agent-specific is written by hand.
Running the script with `--check` is a CI drift gate; the YAML is treated like a lockfile.

Trade-off: it depends on a dbt catalog (one warehouse round-trip) and on the legacy MetricFlow
YAML, which dbt Fusion flags as deprecated but still parses. This supersedes the "kept in sync by
hand" mechanism described in D5.

## D20: Refuse instead of inventing a proxy

LLMs hallucinate semantics, not only column names. Asked for "profit margin per sales rep" when
no such data exists, the model will force the question onto real columns (it computed
`revenue - unit_price` as a fake "margin") and return a confident wrong number. The guard cannot
catch that, because every column it used is real. So the system prompt and one few-shot example
tell the model to return a `CANNOT_ANSWER` sentinel when the schema lacks the concept. The
`summarize` node detects the sentinel and reports a refusal with `failed=True`.

Trade-off: instruction plus a few-shot example is roughly 80% reliable, not a guarantee. The
robust fix is a separate answerability check before generation; this is the cheap version that
buys most of the value. It is also the honest answer to "the guard checks safety, not
correctness."

## D1: LangGraph over a single-prompt chain

The task is multi-step with cycles: generate, validate, execute, and loop back on error. A single
prompt cannot enforce a guardrail between generation and execution, cannot bound a repair loop,
and cannot expose per-step state for tracing and eval. LangGraph gives explicit nodes, typed
shared state (`AgentState`), and conditional edges, so the repair cycle and the safety gate are
part of the structure rather than something I hope the prompt does.

Trade-off: more moving parts than a chain. Worth it, because safety and observability are the
point.

## D2: The read-only database role is the real security boundary

An LLM emits arbitrary text, and "please only read" in a prompt is not a control. The agent
connects with a role that has `SELECT` and `EXPLAIN` and no write or DDL grants, so the database
rejects any mutation at the engine level no matter what the model produces. The prompt contract
and `sql_guard` are cheap early filters that give fast rejection and good error messages, but
they can fail open. The revoked privilege cannot.

Trade-off: an extra role plus grant plumbing (on Postgres, `ALTER DEFAULT PRIVILEGES` so dbt's
future tables stay readable). Cheap insurance. (Now a Snowflake role; see D17.)

## D3: EXPLAIN before execute

`EXPLAIN` validates the query against the live schema, which catches bad identifiers and joins
the static check missed, and it surfaces the planner's cost without running the query. It also
feeds the repair loop a real database error to reflect on. I use `EXPLAIN`, never
`EXPLAIN ANALYZE`, because the latter would execute the query.

Trade-off: one extra round-trip. Negligible.

## D4: Bounded reflect-and-repair (max N, default 2)

Unbounded self-correction burns tokens and time and can oscillate. So retries are capped, each
retry has to consume new information (the verbatim error), the guard cannot be relaxed during a
repair, and on exhaustion the agent returns a typed failure with the last SQL and error.

Trade-off: some genuinely fixable queries fail after N tries. Acceptable. Predictable cost and no
infinite loops beat a small recall gain.

## D5: The semantic layer is the anti-hallucination ground truth

LLMs invent plausible column names. The generator may reference only identifiers present in
`semantic_layer.yaml`, and the guard rejects anything else by name. Keeping the prompt grounded
in that layer is what bounds what the model can say.

Trade-off: the semantic layer has to stay in sync with the schema. That sync is now automated
(see D19).

## D6: Execution accuracy as the primary eval metric

There are many correct SQL queries for one question, so a string or AST match under-counts
correct answers. Comparing result sets (multiset equality, order-insensitive unless the question
is ordered) measures what users care about, which is the right answer. SQL structural similarity
is kept only as a secondary diagnostic. The documented failure modes are buggy reference SQL,
semantic ties, float and locale drift, and empty-result false passes.

Trade-off: it needs a live database and curated gold outputs. That curation is exactly what makes
the metric trustworthy.

## D7: Local-and-free by default, cloud by env (Postgres era)

A portfolio repo should run for anyone with `docker` and `uv` and no paid keys. The original
defaults were an Ollama LLM, local embeddings, and a dockerized Postgres, with a switch to
OpenAI or Azure through `.env`. With no LLM key, the eval ran in deterministic mock mode so CI
stayed green without paid inference.

Trade-off: local models are weaker, which is fine because the point is the system, and eval
numbers are always reported with the model named. Superseded by D17: the warehouse is now
Snowflake, and CI is offline mock-only.

## D8: Scoped Claude Code permissions, no blanket allow

The agent that builds this repo runs with an allowlist for dev tooling and a denylist for
destructive shell commands, secret files, and database write paths, and it asks before doing
anything outside that. Same least-privilege idea as the runtime read-only role, applied to the
dev loop. The command allowlist is convenience, not security; it cannot parse SQL intent, and the
database role does that.

Trade-off: the occasional prompt for a new command, which is the point.

## D9: uv and pinned deps, Python 3.11+

`uv` gives fast, reproducible, fully-locked installs through `uv.lock`, and compatible-release
pins (`~=`) keep upgrades deliberate. 3.11+ is for the typing ergonomics and speed.

Trade-off: `uv` is newer than pip or poetry. The speed and lockfile determinism win for CI.

## D10: Postgres now, Snowflake-ready interface (Postgres era)

Postgres ran free locally, and the design (read-only role, dbt models, a database-client
interface) mapped onto Snowflake without rework. dbt swaps `dbt-postgres` for `dbt-snowflake`,
the role becomes a Snowflake read-only role, SQL stays ANSI where possible, and dialect specifics
stay isolated behind the client and noted in comments.

Trade-off: a thin abstraction cost up front. It paid off as the actual move in D17.

## D11: Real public data (pinned) over fully synthetic

The warehouse is the UCI Online Retail II dataset (real UK and EU e-commerce invoices, 2009 to
2011), loaded from a pinned Hugging Face revision and commit sha into a raw schema, then modeled
into the star with dbt. Real data is more credible than Faker, and it exercises the skill that
matters: cleaning genuinely messy input, including cancellations, returns, blank customer ids,
sub-cent prices that round to zero, and one stock code with many descriptions. Determinism, which
execution-accuracy eval needs, comes from pinning the source revision so every run loads
byte-identical rows and the gold results stay fixed.

Trade-offs and honesty: a one-time download replaces zero-dependency generation; the data is GBP,
UK-centric, and has no cost, margin, or sales-rep fields, so the model is revenue-focused (I kept
a DACH / Europe / Rest-of-World region rollup for the DACH angle); the license is UCI CC BY 4.0,
which is redistribution-safe with attribution, and the repo fetches the data rather than
committing it. The earlier synthetic-Faker idea was dropped in Phase 2; its determinism argument
now lives here through revision pinning.

## D12: Schema retrieval: pgvector plus a keyword fallback (Postgres era)

The retrieval node returned only the relevant tables for a question, which kept the prompt small
and limited what the model could reference. Two backends sat behind one interface. VectorRetriever
used pgvector cosine over fastembed BGE-small embeddings (ONNX, no torch, so it stayed light and
CPU-only) and was the path that scales to hundreds of tables. KeywordRetriever used IDF-weighted
token overlap, had no dependencies, and was deterministic, so it was the default for tests and CI.
For a five-table schema, retrieval is easy and the two agree; the value was the mechanism. The
keyword path has a real weakness with no stemmer ("customers" misses "customer" unless mapped),
which the vector path handles.

Trade-off: a one-time model download for the vector path. Superseded at runtime by D18, which
sends the full schema; the keyword retriever stays behind the interface.

## D13: Provider abstraction plus a deterministic MockLLM

The agent's three model tasks (classify, generate SQL, summarize) sit behind one `LLM` interface.
The original providers were Ollama (local default) and OpenAI or Azure through env, plus a
MockLLM. The mock returns real, guardrail-valid SQL for a small set of canonical questions and a
safe default otherwise, so the whole graph runs with no API key, no local model, and no network.
That is what lets CI and the eval's offline mode exercise the orchestration, guard, and repair
loop deterministically.

Trade-off: the mock is not a real model, so its accuracy is never reported as model accuracy; it
validates the system, not the LLM. Swapping providers is one env var, and the nodes never change.
The bounded repair loop is enforced in the graph edges (`route_after_repair`), not in a prompt; a
test confirms it gives up after exactly `max_retries + 1` generations with no database access.
The Cortex provider was added in D17.

## D14: Tracing through a callback handler, optional and self-hostable

Observability is a headline. LangGraph runs each node as a LangChain runnable, so a single
Langfuse callback handler traces generate, guard, execute, repair, and summarize, including
inputs, outputs, timings, and how many repair loops ran, with no manual span code in the nodes.
The handler is built only when Langfuse keys are set, and any failure to build it returns None, so
tracing never breaks a query and is a no-op when unconfigured. The same Langfuse instance also
logs eval scores.

Trade-off: the self-host setup adds a container, kept behind a profile so the default path stays
lean.

## D15: Eval: result-set comparison details and a deterministic gate

Execution accuracy compares result sets, normalized so real equality survives noise: numerics are
rounded to two decimals, nulls are marked explicitly, and cells are sorted within each row so the
agent naming or ordering its output columns differently from the reference does not cause a false
fail. Row order is ignored (a multiset compare) unless the question is `ordered: true`, for
example a ranked top-N or a quarter-by-quarter series, where rows compare as a sequence. One known
property: sorting cells within a row makes the compare insensitive to column order even for
ordered questions. That is deliberate; it could mask a genuine column-position swap, which is
acceptable for analytical questions where the set of values is the answer. Accuracy rides on the
gold `reference_sql` being correct, which is the headline failure mode, so the gold queries are
reviewed and kept simple. The smoke subset is phrased to match the deterministic MockLLM
fixtures, so the smoke eval scores 1.0 offline and acts as a stable gate (mock LLM, keyword
retriever, no model, key, or network). Structural similarity stays a secondary diagnostic: a
correct query can look very different from the reference, proven by a gold item scoring 0.91
similarity while failing execution.

## D16: The read-only role as Terraform (and it ports to Snowflake)

The read-only boundary is the system's most important control, so it should not be a one-off
`GRANT` someone ran by hand. It is expressed as reviewed, version-controlled Terraform.
`terraform/snowflake` (snowflake-labs/snowflake) creates an `AGENT_RO` account role with `USAGE`
and `SELECT` on current and future tables and views, plus `CORTEX_USER`, and no write or DDL
grants anywhere. `terraform validate` is clean. The Postgres variant (cyrilgdn/postgresql) existed
during the Postgres era and was removed after the move.

Trade-off: Terraform is the production-grade path; the provisioning script
(`scripts/snowflake_provision.py`) is the zero-config default, and you run one or the other, not
both, since a role cannot be created twice. This is the "the safety model works on our warehouse,
as code" answer.
