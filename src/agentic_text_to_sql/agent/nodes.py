"""Graph nodes. Each takes the AgentState and returns a partial update (LangGraph merges it).
Dependencies (LLM, retriever, DB client, semantic layer) are injected via AgentNodes so the
nodes stay pure-ish and testable.

The headline pieces live here: the guard node (static checks + EXPLAIN before execution) and
the bounded reflect/repair routing.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from agentic_text_to_sql import sql_guard
from agentic_text_to_sql.agent.llm import LLM
from agentic_text_to_sql.agent.state import AgentState
from agentic_text_to_sql.config import Settings
from agentic_text_to_sql.db.read_only_client import ReadOnlyClient
from agentic_text_to_sql.semantic_layer.loader import SemanticLayer
from agentic_text_to_sql.semantic_layer.retriever import Retriever

_MAX_PREVIEW_ROWS = 20


def render_schema(layer: SemanticLayer, table_names: list[str]) -> str:
    """Compact schema text for the generation prompt: only the retrieved tables, their
    columns, and the joins. Small prompt + bounded vocabulary = fewer hallucinations."""
    lines: list[str] = []
    for name in table_names:
        t = layer.get(name)
        if t is None:
            continue
        cols = ", ".join(f"{c.name} {c.type}" for c in t.columns)
        lines.append(f"TABLE {t.name} ({t.grain}): {cols}")
    joins = [j for j in layer.joinable_paths if any(n in j for n in table_names)]
    if joins:
        lines.append("JOINS: " + " | ".join(joins))
    return "\n".join(lines)


def _render_rows(columns: list[str], rows: list[tuple[object, ...]]) -> str:
    head = " | ".join(columns)
    body = "\n".join(" | ".join(str(v) for v in row) for row in rows[:_MAX_PREVIEW_ROWS])
    more = f"\n... ({len(rows)} rows total)" if len(rows) > _MAX_PREVIEW_ROWS else ""
    return f"{head}\n{body}{more}"


@dataclass
class AgentNodes:
    settings: Settings
    llm: LLM
    retriever: Retriever
    client: ReadOnlyClient
    layer: SemanticLayer

    # --- nodes -------------------------------------------------------------
    def classify(self, state: AgentState) -> AgentState:
        return {"question_class": self.llm.classify(state["question"])}

    def retrieve(self, state: AgentState) -> AgentState:
        hits = self.retriever.retrieve(state["question"], k=4)
        tables = [h.table for h in hits]
        return {
            "retrieved_tables": tables,
            "schema_context": render_schema(self.layer, tables),
        }

    def generate(self, state: AgentState) -> AgentState:
        # Note: we do NOT clear state['error'] here — generate consumes the last error to
        # repair. The guard/execute nodes clear it on success.
        sql = self.llm.generate_sql(
            state["question"], state.get("schema_context", ""), state.get("error")
        )
        return {"sql": sql}

    def guard(self, state: AgentState) -> AgentState:
        """Static guardrail + EXPLAIN. Sets error (-> repair) or clears it (-> execute)."""
        result = sql_guard.review(
            state["sql"],
            self.layer.allowed_identifiers(),
            self.settings.sql_default_row_limit,
        )
        if result.verdict == sql_guard.Verdict.REJECT:
            return {"error": "; ".join(result.reasons), "guard_reasons": result.reasons}

        sql = result.repaired_sql or state["sql"]  # apply LIMIT injection if any
        try:
            self.client.explain(sql)
        except psycopg.Error as e:
            return {"sql": sql, "error": str(e).strip(), "guard_reasons": result.reasons}
        return {"sql": sql, "error": None, "guard_reasons": result.reasons}

    def execute(self, state: AgentState) -> AgentState:
        try:
            res = self.client.execute(state["sql"])
        except psycopg.Error as e:
            return {"error": str(e).strip()}
        return {"result_columns": res.columns, "result_rows": res.rows, "error": None}

    def repair(self, state: AgentState) -> AgentState:
        return {"repair_attempts": state.get("repair_attempts", 0) + 1}

    def summarize(self, state: AgentState) -> AgentState:
        preview = _render_rows(state["result_columns"], state["result_rows"])
        return {"answer": self.llm.summarize(state["question"], preview)}

    def give_up(self, state: AgentState) -> AgentState:
        return {
            "answer": (
                f"Could not produce a valid query after "
                f"{state.get('repair_attempts', 0)} repair attempt(s). "
                f"Last error: {state.get('error')}"
            ),
            "failed": True,
        }

    # --- routers -----------------------------------------------------------
    def route_after_guard(self, state: AgentState) -> str:
        return "repair" if state.get("error") else "execute"

    def route_after_execute(self, state: AgentState) -> str:
        return "repair" if state.get("error") else "summarize"

    def route_after_repair(self, state: AgentState) -> str:
        """The bounded loop: keep repairing until the retry budget is spent, then give up."""
        if state.get("repair_attempts", 0) <= self.settings.sql_max_repair_retries:
            return "generate"
        return "give_up"
