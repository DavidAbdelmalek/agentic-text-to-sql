"""LLM providers for the agent's three model tasks: classify, generate SQL, summarize.

Design:
- Task-oriented interface (not a raw chat) so prompts live with the provider and the MockLLM
  can be fully deterministic.
- MockLLM runs the whole graph offline — no API key, no local model, no network. It is the
  CI/offline path and the eval's mock mode. It returns real, guardrail-valid SQL for a small
  set of canonical questions and a safe default otherwise.
- Cortex (Snowflake, in-warehouse) is the only real provider: the LLM runs inside the
  warehouse, so no data leaves it and there is no external API key.
"""

from __future__ import annotations

import re
from typing import Protocol

from agentic_text_to_sql.config import Settings

_FENCE = re.compile(r"```(?:sql)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)

# Sentinel the model must emit when the schema cannot answer the question. The agent detects
# it (see nodes.summarize) and reports a refusal instead of a confidently-wrong number.
CANNOT_ANSWER = "CANNOT_ANSWER"

_SQL_SYSTEM = (
    "You are a careful Snowflake analytics engineer. Convert the user's question into ONE "
    "read-only SQL SELECT over the provided schema. Follow every rule:\n"
    "1. Use ONLY the tables and columns listed in the schema. Never invent, rename, or guess a "
    "column.\n"
    "2. Join the fact table to dimensions on the matching *_key columns. All money is GBP "
    "(revenue_gbp additive; unit_price_gbp non-additive — average it, do not sum).\n"
    "3. REFUSE rather than approximate. If the schema has no column for the concept asked "
    "(e.g. profit, margin, cost, discount, tax, sales rep, supplier, inventory), do NOT "
    "substitute or compute a proxy from other columns. Return EXACTLY this single line:\n"
    f"   SELECT '{CANNOT_ANSWER}' AS status, '<which data is missing>' AS reason\n"
    "4. Otherwise return one single SELECT (no DDL/DML, no second statement, no semicolon) and "
    "always include a LIMIT.\n"
    "5. Output ONLY the SQL — no prose, no explanation, no markdown fences."
)

# Few-shot examples. Chosen to teach the join/aggregate/filter PATTERNS while staying disjoint
# from the eval gold set (no leakage): avg aggregate, date-range + COUNT DISTINCT, ILIKE text
# filter. Keep these distinct from data/eval/gold.yaml if you add more.
_FEWSHOT = """Examples:
Q: What is the average unit price by product?
SQL: SELECT dim_product.product_name, AVG(fct_sales.unit_price_gbp) AS avg_unit_price_gbp \
FROM fct_sales JOIN dim_product ON fct_sales.product_key = dim_product.product_key \
GROUP BY dim_product.product_name ORDER BY avg_unit_price_gbp DESC LIMIT 100

Q: How many invoices were placed in December 2010?
SQL: SELECT COUNT(DISTINCT fct_sales.invoice_no) AS invoice_count \
FROM fct_sales JOIN dim_date ON fct_sales.date_key = dim_date.date_key \
WHERE dim_date.year = 2010 AND dim_date.month = 12 LIMIT 100

Q: Which products have 'HEART' in their name, by revenue?
SQL: SELECT dim_product.product_name, SUM(fct_sales.revenue_gbp) AS revenue_gbp \
FROM fct_sales JOIN dim_product ON fct_sales.product_key = dim_product.product_key \
WHERE dim_product.product_name ILIKE '%HEART%' \
GROUP BY dim_product.product_name ORDER BY revenue_gbp DESC LIMIT 100

Q: What is the profit margin per sales rep?
SQL: SELECT 'CANNOT_ANSWER' AS status, 'schema has no profit, cost, or sales-rep data' AS reason"""


def _build_sql_user(schema_context: str, question: str, error: str | None) -> str:
    """The user message for SQL generation: schema, few-shot examples, the question, and (on a
    repair retry) the previous error. Shared by every real provider."""
    parts = [f"Schema:\n{schema_context}", _FEWSHOT, f"Question: {question}"]
    if error:
        parts.append(f"The previous attempt failed with:\n{error}\nFix it.")
    return "\n\n".join(parts)


def _extract_sql(text: str) -> str:
    """Pull a bare SQL statement out of a model response (strip ``` fences / prose)."""
    m = _FENCE.search(text)
    sql = (m.group(1) if m else text).strip()
    # Drop a trailing semicolon so it stays a single statement for the guard.
    return sql.rstrip(";").strip()


class LLM(Protocol):
    def classify(self, question: str) -> str: ...
    def generate_sql(self, question: str, schema_context: str, error: str | None) -> str: ...
    def summarize(self, question: str, result_preview: str) -> str: ...


# --------------------------------------------------------------------------- Mock
class MockLLM:
    """Deterministic. Canonical questions -> known-good SQL; everything else -> a safe total.
    These fixtures double as a starting point for the eval gold set."""

    FIXTURES: list[tuple[set[str], str]] = [
        (
            {"country", "revenue"},
            "SELECT c.country, ROUND(SUM(f.revenue_gbp), 2) AS revenue_gbp "
            "FROM fct_sales f JOIN dim_country c ON f.country_key = c.country_key "
            "GROUP BY c.country ORDER BY revenue_gbp DESC LIMIT 100",
        ),
        (
            {"region", "revenue"},
            "SELECT c.region, ROUND(SUM(f.revenue_gbp), 2) AS revenue_gbp "
            "FROM fct_sales f JOIN dim_country c ON f.country_key = c.country_key "
            "GROUP BY c.region ORDER BY revenue_gbp DESC LIMIT 100",
        ),
        (
            {"product", "revenue"},
            "SELECT p.product_name, ROUND(SUM(f.revenue_gbp), 2) AS revenue_gbp "
            "FROM fct_sales f JOIN dim_product p ON f.product_key = p.product_key "
            "GROUP BY p.product_name ORDER BY revenue_gbp DESC LIMIT 5",
        ),
        (
            {"month", "revenue"},
            "SELECT d.year, d.month, ROUND(SUM(f.revenue_gbp), 2) AS revenue_gbp "
            "FROM fct_sales f JOIN dim_date d ON f.date_key = d.date_key "
            "GROUP BY d.year, d.month ORDER BY d.year, d.month LIMIT 100",
        ),
        (
            {"customer", "revenue"},
            "SELECT f.customer_key, ROUND(SUM(f.revenue_gbp), 2) AS revenue_gbp "
            "FROM fct_sales f GROUP BY f.customer_key ORDER BY revenue_gbp DESC LIMIT 10",
        ),
    ]
    DEFAULT_SQL = "SELECT ROUND(SUM(revenue_gbp), 2) AS total_revenue_gbp FROM fct_sales"

    def classify(self, question: str) -> str:
        q = question.lower()
        if any(w in q for w in ("trend", "month", "year", "over time")):
            return "trend"
        if any(w in q for w in ("how many", "count", "number of")):
            return "aggregate"
        if any(w in q for w in ("top", "sum", "total", "average", "revenue", "by ")):
            return "aggregate"
        return "lookup"

    _WORD_MAP = {"monthly": "month", "yearly": "year", "countries": "country", "sales": "revenue"}

    def generate_sql(self, question: str, schema_context: str, error: str | None) -> str:
        words = set(re.findall(r"[a-z]+", question.lower()))
        words |= {w.rstrip("s") for w in words}  # plural-tolerant
        words |= {self._WORD_MAP[w] for w in list(words) if w in self._WORD_MAP}
        for required, sql in self.FIXTURES:
            if required <= words:
                return sql
        return self.DEFAULT_SQL

    def summarize(self, question: str, result_preview: str) -> str:
        return f"Result for: {question}\n{result_preview}"


# --------------------------------------------------------------------------- Snowflake Cortex
class CortexLLM:
    """Snowflake Cortex — the LLM runs IN the warehouse via SNOWFLAKE.CORTEX.COMPLETE, called
    over the agent's read-only connection (the AGENT_RO role holds the CORTEX_USER grant). No
    external API key, no data leaving Snowflake. Model e.g. llama3.1-70b (EU region)."""

    def __init__(self, settings: Settings) -> None:
        from agentic_text_to_sql.db import snowflake as sf

        self._sf = sf
        self._model = settings.cortex_model
        # One persistent read-only connection, reused across the run.
        self._conn = sf.connect(role=sf.AGENT_ROLE, schema=sf.MARTS_SCHEMA)

    def _complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        prompt = f"{system}\n\n{user}"
        cur = self._conn.cursor()
        # AI_COMPLETE is Snowflake's current Cortex completion function (supersedes
        # CORTEX.COMPLETE). temperature 0 => deterministic SQL, so the same question yields the
        # same query (reproducible eval). model + prompt are bound; the options object is inlined.
        cur.execute(
            "select ai_complete(%s, %s, {'temperature': 0, 'max_tokens': %s})",
            (self._model, prompt, max_tokens),
        )
        row = cur.fetchone()
        return str(row[0]) if row else ""

    def classify(self, question: str) -> str:
        out = self._complete(
            "Classify the question as one word: lookup, aggregate, or trend. Reply with the "
            "word only.",
            question,
        )
        return out.strip().lower().split()[0] if out.strip() else "aggregate"

    def generate_sql(self, question: str, schema_context: str, error: str | None) -> str:
        user = _build_sql_user(schema_context, question, error)
        return _extract_sql(self._complete(_SQL_SYSTEM, user))

    def summarize(self, question: str, result_preview: str) -> str:
        return self._complete(
            "Answer the question in one or two sentences using the result rows, with numbers.",
            f"Question: {question}\n\nResult:\n{result_preview}",
        )


def get_llm(settings: Settings) -> LLM:
    """Pick a provider. Cortex is the only real backend; everything else (including unset creds)
    falls back to the deterministic MockLLM so the graph (and eval) always run."""
    if settings.llm_enabled and settings.llm_provider == "cortex":
        return CortexLLM(settings)
    return MockLLM()
