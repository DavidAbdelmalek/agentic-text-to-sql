"""Read-only Postgres client. The agent reaches the database ONLY through here, and ONLY
with the read-only role DSN. Belt-and-braces: this client also refuses anything that isn't a
single SELECT/EXPLAIN, even though the DB role would reject writes anyway — two independent
checks in front of the engine-level guarantee."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
import sqlglot
from sqlglot import exp

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
    statements = sqlglot.parse(sql, read="postgres")
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
    def __init__(self, dsn: str, statement_timeout_ms: int = 5000) -> None:
        self._dsn = dsn
        self._statement_timeout_ms = statement_timeout_ms

    def _connect(self) -> psycopg.Connection[tuple[Any, ...]]:
        conn = psycopg.connect(self._dsn)
        # Hard cap runaway queries. Session-level; applies to every statement on this conn.
        conn.execute(f"SET statement_timeout = {int(self._statement_timeout_ms)}")
        return conn

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> QueryResult:
        assert_read_only(sql)
        with self._connect() as conn:
            cur = conn.execute(sql, params or {})
            columns = [d.name for d in cur.description] if cur.description else []
            rows = cur.fetchall()
        return QueryResult(columns=columns, rows=rows)

    def explain(self, sql: str, params: dict[str, Any] | None = None) -> str:
        """Run EXPLAIN (never ANALYZE — that would execute the query). Returns the plan text,
        or raises psycopg.Error, whose message feeds the repair loop."""
        assert_read_only(sql)
        with self._connect() as conn:
            cur = conn.execute(f"EXPLAIN {sql}", params or {})
            return "\n".join(row[0] for row in cur.fetchall())
