"""Graph nodes. Each takes the AgentState and returns a partial update (LangGraph merges it).
Dependencies (LLM, DB client, semantic layer) are injected via AgentNodes so the nodes stay
pure-ish and testable.

The headline pieces live here: the guard node (static checks + EXPLAIN before execution) and
the bounded reflect/repair routing. The full semantic layer is sent to the model on every
generation — for a fixed 5-table star, retrieval can only drop a table the query needs, and
the identifier guard (not retrieval) is the anti-hallucination backstop.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentic_text_to_sql import sql_guard
from agentic_text_to_sql.agent.llm import CANNOT_ANSWER, LLM
from agentic_text_to_sql.agent.state import AgentState
from agentic_text_to_sql.config import Settings
from agentic_text_to_sql.db.read_only_client import ReadOnlyClient
from agentic_text_to_sql.semantic_layer.loader import SemanticLayer

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
    client: ReadOnlyClient
    layer: SemanticLayer
    schema_context: str  # full schema rendered once at build time (all tables)
    all_table_names: list[str]

    # --- nodes -------------------------------------------------------------
    def generate(self, state: AgentState) -> AgentState:
        """Generate SQL via LLM from the full schema. On repair, passes prior error for fix."""
        # Note: we do NOT clear state['error'] here — generate consumes the last error to
        # repair. The guard/execute nodes clear it on success.
        sql = self.llm.generate_sql(state["question"], self.schema_context, state.get("error"))
        # retrieved_tables = the whole schema (we never drop a table); kept for eval scoring.
        return {"sql": sql, "retrieved_tables": self.all_table_names}

    def guard(self, state: AgentState) -> AgentState:
        """Safety check: reject DDL/DML, verify identifiers exist, inject LIMIT, EXPLAIN.
        Feeds errors to repair loop; clears error on success to allow execution."""
        result = sql_guard.review(
            state["sql"],
            self.layer.allowed_identifiers(),
            self.settings.sql_default_row_limit,
        )
        if result.verdict == sql_guard.Verdict.REJECT:
            return {"error": "; ".join(result.reasons)}

        sql = result.repaired_sql or state["sql"]  # apply LIMIT injection if any
        try:
            self.client.explain(sql)
        except Exception as e:  # noqa: BLE001 — any DB/EXPLAIN error feeds the repair loop
            return {"sql": sql, "error": str(e).strip()}
        return {"sql": sql, "error": None}

    def execute(self, state: AgentState) -> AgentState:
        """Run SQL via read-only role (AGENT_RO). Catch execution errors for repair."""
        try:
            res = self.client.execute(state["sql"])
        except Exception as e:  # noqa: BLE001 — any execution error feeds the repair loop
            return {"error": str(e).strip()}
        return {"result_columns": res.columns, "result_rows": res.rows, "error": None}

    def repair(self, state: AgentState) -> AgentState:
        """Increment repair attempt counter. Routed back to generate if budget remains."""
        return {"repair_attempts": state.get("repair_attempts", 0) + 1}

    def summarize(self, state: AgentState) -> AgentState:
        """Summarize result rows into an English answer. If the model refused (CANNOT_ANSWER
        sentinel — the schema can't answer the question), surface the refusal instead of
        narrating a meaningless row."""
        cols = state.get("result_columns") or []
        rows = state.get("result_rows") or []
        refused = (
            [c.lower() for c in cols] == ["status", "reason"]
            and rows
            and str(rows[0][0]).upper() == CANNOT_ANSWER
        )
        if refused:
            msg = f"I can't answer that from this data: {rows[0][1]}."
            return {"answer": msg, "failed": True}
        preview = _render_rows(cols, rows)
        return {"answer": self.llm.summarize(state["question"], preview)}

    def give_up(self, state: AgentState) -> AgentState:
        """Repair budget exhausted. Return failure with last error."""
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
