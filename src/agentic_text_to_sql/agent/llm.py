"""LLM providers for the agent's three model tasks: classify, generate SQL, summarize.

Design:
- Task-oriented interface (not a raw chat) so prompts live with the provider and the MockLLM
  can be fully deterministic.
- MockLLM runs the whole graph offline — no API key, no local model, no network. It is the
  CI/offline path and the eval's mock mode. It returns real, guardrail-valid SQL for a small
  set of canonical questions and a safe default otherwise.
- Ollama (local, free, default) and OpenAI/Azure (cloud, via env) are the real providers.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from agentic_text_to_sql.config import Settings

_FENCE = re.compile(r"```(?:sql)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)

_SQL_SYSTEM = (
    "You are a careful analytics engineer. Translate the question into ONE read-only "
    "PostgreSQL SELECT statement. Rules: use ONLY the tables/columns in the provided schema; "
    "never write DDL/DML; always include a LIMIT; return ONLY the SQL, no prose."
)


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


# --------------------------------------------------------------------------- Ollama
class OllamaLLM:
    def __init__(self, settings: Settings) -> None:
        import ollama

        self._client = ollama.Client(host=settings.ollama_base_url)
        self._model = settings.llm_model

    def _chat(self, system: str, user: str) -> str:
        resp = self._client.chat(
            model=self._model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            options={"temperature": 0},
        )
        return str(resp["message"]["content"])

    def classify(self, question: str) -> str:
        out = self._chat(
            "Classify the question as one word: lookup, aggregate, or trend. Reply with the "
            "word only.",
            question,
        )
        return out.strip().lower().split()[0] if out.strip() else "aggregate"

    def generate_sql(self, question: str, schema_context: str, error: str | None) -> str:
        user = f"Schema:\n{schema_context}\n\nQuestion: {question}"
        if error:
            user += f"\n\nThe previous attempt failed with:\n{error}\nFix it."
        return _extract_sql(self._chat(_SQL_SYSTEM, user))

    def summarize(self, question: str, result_preview: str) -> str:
        return self._chat(
            "Answer the user's question in one or two sentences using the result rows. Be "
            "precise and include the numbers.",
            f"Question: {question}\n\nResult:\n{result_preview}",
        )


# --------------------------------------------------------------------------- OpenAI / Azure
class OpenAILLM:
    _model: Any

    def __init__(self, settings: Settings) -> None:
        if settings.llm_provider == "azure":
            from langchain_openai import AzureChatOpenAI

            self._model = AzureChatOpenAI(
                azure_endpoint=settings.azure_openai_endpoint,
                api_key=settings.azure_openai_api_key,  # type: ignore[arg-type]
                azure_deployment=settings.azure_openai_deployment,
                api_version="2024-06-01",
                temperature=0,
            )
        else:
            from langchain_openai import ChatOpenAI

            self._model = ChatOpenAI(
                model=settings.llm_model,
                api_key=settings.openai_api_key,  # type: ignore[arg-type]
                base_url=settings.openai_base_url or None,
                temperature=0,
            )

    def _chat(self, system: str, user: str) -> str:
        resp = self._model.invoke([("system", system), ("user", user)])
        return str(resp.content)

    def classify(self, question: str) -> str:
        out = self._chat(
            "Classify the question as one word: lookup, aggregate, or trend.", question
        )
        return out.strip().lower().split()[0] if out.strip() else "aggregate"

    def generate_sql(self, question: str, schema_context: str, error: str | None) -> str:
        user = f"Schema:\n{schema_context}\n\nQuestion: {question}"
        if error:
            user += f"\n\nThe previous attempt failed with:\n{error}\nFix it."
        return _extract_sql(self._chat(_SQL_SYSTEM, user))

    def summarize(self, question: str, result_preview: str) -> str:
        return self._chat(
            "Answer the question in one or two sentences using the result rows, with numbers.",
            f"Question: {question}\n\nResult:\n{result_preview}",
        )


def get_llm(settings: Settings) -> LLM:
    """Pick a provider. Falls back to the deterministic MockLLM whenever a real model can't be
    reached, so the graph (and eval) always run."""
    if not settings.llm_enabled:
        return MockLLM()
    if settings.llm_provider in ("openai", "azure"):
        return OpenAILLM(settings)
    if settings.llm_provider == "ollama":
        return OllamaLLM(settings)
    return MockLLM()
