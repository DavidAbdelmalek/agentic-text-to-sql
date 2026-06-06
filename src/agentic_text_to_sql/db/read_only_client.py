"""Read-only Snowflake client. The agent reaches the warehouse ONLY through here, and ONLY
with the read-only AGENT_RO role. Belt-and-braces: this client also refuses anything that
isn't a single SELECT/EXPLAIN, even though the role would reject writes anyway."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlglot import exp

from agentic_text_to_sql.db import snowflake as sf

_DIALECT = "snowflake"

# Expression types that must never appear anywhere in a query the agent runs.
_FORBIDDEN = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Command,
    exp.Grant,
    exp.Into,
)


class UnsafeQueryError(RuntimeError):
    """Raised when SQL reaching the client is not a single read-only statement."""


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]


def assert_read_only(sql: str) -> exp.Expression:
    """Parse + assert exactly one read-only statement. Returns the parsed expression."""
    statements = sqlglot.parse(sql, read=_DIALECT)
    if len(statements) != 1 or statements[0] is None:
        raise UnsafeQueryError("exactly one statement is allowed")
    stmt = statements[0]
    if not isinstance(stmt, exp.Select | exp.Union | exp.Subquery):
        raise UnsafeQueryError(f"only SELECT queries are allowed, got {type(stmt).__name__}")
    for node in stmt.walk():
        if isinstance(node, _FORBIDDEN):
            raise UnsafeQueryError(f"forbidden statement element: {type(node).__name__}")
    return stmt


class ReadOnlyClient:
    def __init__(self, statement_timeout_ms: int = 5000) -> None:
        self._timeout_s = max(1, int(statement_timeout_ms) // 1000)

    def _connect(self) -> Any:
        # Connect with the READ-ONLY role on the marts schema. The role has only SELECT
        # (+ Cortex) — Snowflake rejects writes at the engine level.
        conn = sf.connect(role=sf.AGENT_ROLE, schema=sf.MARTS_SCHEMA)
        conn.cursor().execute(
            f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {self._timeout_s}"
        )
        return conn

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> QueryResult:
        assert_read_only(sql)
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(sql, params or None)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = [tuple(r) for r in cur.fetchall()]
        finally:
            conn.close()
        return QueryResult(columns=columns, rows=rows)

    def explain(self, sql: str, params: dict[str, Any] | None = None) -> str:
        """Run EXPLAIN (Snowflake plan, no execution). Raises on error; the message feeds the
        repair loop."""
        assert_read_only(sql)
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(f"EXPLAIN USING TEXT {sql}", params or None)
            return "\n".join(str(r[0]) for r in cur.fetchall())
        finally:
            conn.close()
