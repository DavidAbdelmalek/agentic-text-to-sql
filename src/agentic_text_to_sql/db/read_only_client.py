"""Read-only Postgres client. Phase 4 implements execution; this stub fixes the
interface the rest of the system codes against (so Postgres now / Snowflake later
swap behind it without touching agent nodes)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]


class ReadOnlyClient:
    """Connects with the read-only role DSN, sets a statement timeout, and only ever
    runs SELECT/EXPLAIN. Implemented in Phase 4."""

    def __init__(self, dsn: str, statement_timeout_ms: int = 5000) -> None:
        self._dsn = dsn
        self._statement_timeout_ms = statement_timeout_ms

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> QueryResult:
        raise NotImplementedError("Phase 4: execute parameterized read-only query")

    def explain(self, sql: str, params: dict[str, Any] | None = None) -> str:
        raise NotImplementedError("Phase 4: run EXPLAIN (not ANALYZE) and return the plan")
