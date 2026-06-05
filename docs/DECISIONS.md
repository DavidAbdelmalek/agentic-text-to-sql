# Design Decisions (the "why" log)

Every non-obvious choice, with the trade-off. This is the interview cheat-sheet — each
entry is something you should be able to defend out loud.

## D1 — LangGraph over a single-prompt chain
**Why:** the task is inherently multi-step with cycles (generate → validate → execute →
*loop back on error*). A single prompt can't enforce a guardrail between generation and
execution, can't bound a repair loop, and can't expose per-step state for tracing/eval.
LangGraph gives explicit nodes, typed shared state (`AgentState`), and conditional edges —
so the reflect/repair cycle and the safety gate are *structural*, not vibes inside one
prompt. **Trade-off:** more moving parts than a chain; justified because safety and
observability are the whole point.

## D2 — Read-only Postgres role is the real security boundary
**Why:** an LLM emits arbitrary text; "please only read" in a prompt is not a control.
We connect the agent with a role that has `SELECT`/`EXPLAIN` and *no* write/DDL grants, so
Postgres rejects any mutation at the engine level no matter what the model produces. The
prompt contract and `sql_guard` are cheap early filters (good error messages, fast
rejection) but they can fail open; the revoked privilege cannot. **Trade-off:** an extra
role + grant plumbing (`ALTER DEFAULT PRIVILEGES` so dbt's future tables stay readable).
Cheap insurance.

## D3 — `EXPLAIN` before execute
**Why:** validates the query against the live schema (catches bad identifiers/joins the
static check missed) and surfaces the planner's cost *without running the query*. Feeds the
repair loop a real Postgres error to reflect on. We use `EXPLAIN`, never `EXPLAIN ANALYZE`
(that would execute it). **Trade-off:** an extra round-trip; negligible.

## D4 — Bounded reflect-and-repair (max N, default 2)
**Why:** unbounded self-correction burns tokens/time and can oscillate. We cap retries,
require each retry to consume *new information* (the verbatim error), forbid relaxing a
guardrail during repair, and on exhaustion return a typed failure with the last SQL+error.
**Trade-off:** some genuinely-fixable queries fail after N; acceptable — predictable cost
and no infinite loops beat a marginal recall gain.

## D5 — Semantic layer as the anti-hallucination ground truth
**Why:** LLMs invent plausible column names. The generator may reference *only* identifiers
present in `semantic_layer.yaml`, and the guardian rejects anything else by name. Retrieval
(pgvector over table/column descriptions) keeps the prompt small and focused. **Trade-off:**
the semantic layer must be kept in sync with the schema — automated via the `schema-explorer`
subagent + `make semantic`.

## D6 — Execution accuracy as the primary eval metric
**Why:** there are many correct SQLs for one question, so string/AST match under-counts
correct answers. Comparing *result sets* (multiset equality, order-insensitive unless the
question is ordered) measures what users care about: the right answer. SQL structural
similarity is kept only as a secondary diagnostic. **Failure modes (documented, not hidden):**
buggy reference SQL, semantic ties, float/locale drift, empty-result false-passes — see the
`eval-methodology` skill. **Trade-off:** needs a live DB and curated gold outputs; that
curation is exactly what makes the metric trustworthy.

## D7 — Local-and-free by default, cloud by env
**Why:** a portfolio repo must run for anyone with `docker` + `uv`, no paid keys. Defaults:
Ollama LLM, local sentence-transformers embeddings, dockerized Postgres. Swap to
OpenAI/Azure purely via `.env`. If no LLM key exists, eval runs in deterministic **mock
mode** so CI stays green without paid inference. **Trade-off:** local models are weaker;
fine — we're proving the *system*, and eval numbers are reported with the model named.

## D8 — Scoped Claude Code permissions, no blanket allow
**Why:** the agent that *builds* this repo runs with an allowlist (dev tooling) + denylist
(destructive shell, secret files, DB write-paths) and asks before anything outside it. Same
least-privilege principle as the runtime read-only role, applied to the dev loop. **Note:**
the command allowlist is convenience, not security — it can't parse SQL intent; the DB role
does that. **Trade-off:** occasional prompts for new commands; that's the point.

## D9 — uv + pinned deps, Python 3.11+
**Why:** `uv` gives fast, reproducible, fully-locked installs (`uv.lock`); compatible-release
pins (`~=`) keep upgrades deliberate. 3.11+ for `TypedDict`/typing ergonomics and speed.
**Trade-off:** uv is newer than pip/poetry; the speed + lockfile determinism win for CI.

## D15 — Eval: result-set comparison details + a deterministic gate
**Why:** execution accuracy compares result *sets*, normalized so genuine equality survives
noise: numerics rounded to 2dp, nulls marked explicitly, and **cells sorted within each row**
so the agent naming/ordering its output columns differently from the reference doesn't cause a
false fail. Row order is ignored (multiset/`Counter` compare) unless the question is
`ordered: true` (e.g. a ranked top-N or a quarter-by-quarter series), where rows compare as a
sequence. **Known property:** within-row cell sorting makes the compare column-order-insensitive
even for `ordered` questions — a deliberate robustness choice; it could mask a genuine
column-position swap, which is acceptable for analytical questions where the *set of values* is
the answer. **Reference-SQL trust:** accuracy rides on the gold `reference_sql` being correct —
the headline failure mode — so the gold queries are reviewed and kept simple. The **smoke**
subset is phrased to match the deterministic MockLLM fixtures, so `make eval-smoke` scores 1.0
offline and acts as a stable CI gate (mock LLM + keyword retriever, no model/key/network).
Structural similarity stays a secondary diagnostic only (a correct query can look very
different from the reference — proven by a gold item scoring 0.91 similarity while failing
execution).

## D14 — Tracing via a callback handler, optional + self-hostable
**Why:** observability is a headline. LangGraph runs each node as a LangChain runnable, so a
single Langfuse **CallbackHandler** auto-traces classify/retrieve/generate/guard/execute/
repair/summarize — inputs, outputs, timings, and how many repair loops ran — with no manual
span code in the nodes. The handler is created only when Langfuse keys are set and any failure
to build it returns None, so **tracing never breaks a query** (it's a no-op when unconfigured).
Langfuse is self-hosted via an opt-in compose profile with **headlessly-seeded** keys
(`LANGFUSE_INIT_*`), so traces work locally and free without a UI signup; it also points at
Langfuse Cloud by changing env. **Trade-off:** the self-host profile adds a container + its own
Postgres; kept behind a profile so the default `up` stays lean. Phase 6 reuses the same
Langfuse to log eval scores.

## D13 — Provider abstraction + a deterministic MockLLM
**Why:** the agent's three model tasks (classify, generate SQL, summarize) sit behind one
`LLM` interface with Ollama (local default), OpenAI/Azure (env), and a **MockLLM**. The mock
returns real, guardrail-valid SQL for a small set of canonical questions and a safe default
otherwise, so the *entire graph* runs with **no API key, no local model, no network** — which
is what lets CI and the eval's offline mode exercise the orchestration, guard, and repair loop
deterministically. **Trade-off:** the mock isn't a real model, so its "accuracy" is never
reported as model accuracy — it validates the *system*, not the LLM. Swapping providers is one
env var; nodes never change. The bounded repair loop is enforced structurally in the graph
edges (`route_after_repair`), not in a prompt — tested to give up after exactly
`max_retries + 1` generations with no DB access.

## D12 — Schema retrieval: pgvector + a keyword fallback
**Why:** the retrieval node returns only the relevant tables for a question, so the prompt
stays small AND the model can reference fewer things — which, with the guardrail's identifier
check, is the anti-hallucination story. Two backends behind one interface: **VectorRetriever**
(pgvector cosine over **fastembed** BGE-small embeddings — ONNX, *no torch*, so it stays light
and CPU-only) is the headline path that scales to hundreds of tables; **KeywordRetriever**
(IDF-weighted token overlap, zero-dependency, deterministic) is the default for tests/CI and
the offline path. **Honesty:** for a 5-table schema retrieval is easy and the two agree; the
value is the *mechanism*. The keyword path has a real, demonstrated weakness — no stemmer, so
"customers" misses "customer" unless mapped — which the vector path handles semantically; we
keep both to make that trade-off explicit. Embeddings live in a separate `semantic` schema the
read-only role is granted SELECT on — infra, not warehouse data. **Trade-off:** a one-time
~90 MB model download (cached) for the vector path; the keyword path needs nothing.

## D11 — Real public data (pinned) over fully-synthetic
**Why:** the warehouse is the **UCI Online Retail II** dataset (real UK/EU e-commerce
invoices, 2009–2011), loaded from a **pinned** Hugging Face revision + commit sha into a
`raw` schema, then dbt-modeled into the star. Real data is more credible than Faker *and*
exercises the skill that matters: cleaning genuinely messy input (cancellations, returns,
blank customer ids, sub-cent prices that round to zero, one stock code with many
descriptions). Determinism — which execution-accuracy eval needs — is preserved by pinning
the source revision: every run/CI loads byte-identical rows, so gold results stay fixed.
**Trade-offs / honesty:** (a) a one-time ~95 MB download (cached) replaces zero-dependency
generation; (b) the data is **GBP**, UK-centric, and has **no cost/margin or sales-rep**
fields, so the model is revenue-focused (we kept a DACH/Europe/RoW region rollup for the
DACH angle); (c) license is UCI **CC BY 4.0** — redistribution-safe with attribution, and we
don't commit the data, we fetch it. The earlier synthetic-Faker path (D7) was dropped in
Phase 2 at the user's request; its determinism argument now lives here via revision pinning.

## D10 — Postgres now, Snowflake-ready interface
**Why:** Postgres runs free locally; the design (read-only role, dbt models, DB client
interface) maps 1:1 onto Snowflake. dbt swaps `dbt-postgres`→`dbt-snowflake`; the role
becomes a Snowflake read-only role (Terraform `snowflake/`). SQL stays ANSI where possible,
dialect specifics isolated behind the client + noted in comments. **Trade-off:** a thin
abstraction tax now; pays off as the "this ports to our warehouse" interview answer.
