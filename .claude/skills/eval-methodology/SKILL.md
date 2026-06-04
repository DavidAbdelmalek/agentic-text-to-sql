---
name: eval-methodology
description: How this repo measures the SQL agent — the gold-set format, execution-accuracy scoring (primary), SQL structural similarity (secondary), retrieval correctness, the known failure modes of each metric, and the offline/mock mode for CI. Use when building or changing the eval harness, the gold set, or interpreting eval results.
---

# Evaluation Methodology

Evaluation is what makes this repo credible rather than a demo. We score behavior, not vibes.

## Gold set
`data/eval/gold.yaml` — ~15–25 questions. Each item:
```yaml
- id: q07
  question: "Total net revenue in EUR per country for 2024, top 5."
  reference_sql: "SELECT ... LIMIT 5"
  gold_tables: [fct_sales, dim_customer, dim_date]   # for retrieval scoring
  ordered: true                                       # does row order matter for this Q?
```
Questions span: simple filters, joins, group-by aggregates, date logic, top-N, and a few
intentionally ambiguous ones to probe failure handling.

## Metrics

### 1. Execution accuracy (PRIMARY)
Run the agent's SQL and the `reference_sql` against the same DB; compare result sets.
- Default comparison: **multiset equality** (order-insensitive) after normalizing column
  order and numeric rounding. If the item is `ordered: true`, compare as ordered sequences.
- Pass = result sets equal. This is the headline number.
- **Failure modes to acknowledge in interview:**
  - *Reference-SQL bug* — a wrong gold query makes a correct agent look wrong. Mitigate by
    reviewing gold queries and pinning their expected output.
  - *Semantic ties* — multiple correct SQLs (e.g. different but equivalent groupings);
    multiset compare handles most, not all.
  - *Float/locale drift* — rounding and EUR formatting; normalize before compare.
  - *Empty-result false pass* — two queries both wrong but both empty. Flag zero-row golds.

### 2. SQL structural similarity (SECONDARY)
sqlglot-normalized AST/token similarity between agent SQL and reference SQL.
- Use ONLY as a diagnostic, never as a gate. A correct query can be structurally very
  different from the reference (its main failure mode), so low similarity != wrong.

### 3. Retrieval correctness
Did the retrieval node surface the `gold_tables`? Report precision/recall over the table
set. Catches "right answer for the wrong reason" and schema-retrieval regressions.

## Offline / mock mode
If no LLM key is set, the harness runs deterministically: the generator returns canned SQL
keyed by question id (or a templated stub), so CI can assert the *harness and scoring* work
without paid inference. Mock mode is clearly labeled in output and never reported as real
model accuracy.

## Wiring
- `make eval` — full gold set, logs each run to Langfuse if keys present.
- `make eval-smoke` — fixed subset, run in CI as a gate (mock mode by default).
