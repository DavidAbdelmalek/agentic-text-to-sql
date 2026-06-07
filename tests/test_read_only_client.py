"""Phase 4 unit tests for the read-only client's static guard (`assert_read_only`).

Pure parsing only — no database connection. This is the belt-and-braces check that sits
in front of the read-only Postgres role: the client must refuse anything that isn't a
single read-only statement before it ever reaches the engine.
"""

from __future__ import annotations

import pytest
from snowflake.connector.errors import OperationalError, ProgrammingError
from sqlglot import exp

from agentic_text_to_sql.db.read_only_client import (
    ReadOnlyClient,
    UnsafeQueryError,
    assert_read_only,
)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM fct_sales",
        "INSERT INTO fct_sales (sales_key) VALUES (1)",
        "UPDATE fct_sales SET revenue_gbp = 0",
        "DROP TABLE fct_sales",
        "SELECT 1; SELECT 2",
    ],
    ids=["delete", "insert", "update", "drop", "two_statements"],
)
def test_assert_read_only_rejects_non_read_only(sql: str) -> None:
    with pytest.raises(UnsafeQueryError):
        assert_read_only(sql)


def test_assert_read_only_returns_expression_for_select() -> None:
    stmt = assert_read_only("SELECT country FROM dim_country LIMIT 10")
    assert isinstance(stmt, exp.Expression)


def test_retry_recovers_from_transient_error() -> None:
    """A transient Snowflake fault is retried; the operation succeeds on a later attempt."""
    client = ReadOnlyClient(max_attempts=3)
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise OperationalError("transient network blip")
        return "ok"

    assert client._with_retry(flaky) == "ok"
    assert calls["n"] == 2


def test_retry_does_not_mask_deterministic_error() -> None:
    """A non-transient error (bad SQL) is raised immediately, not retried — no wasted budget."""
    client = ReadOnlyClient(max_attempts=3)
    calls = {"n": 0}

    def bad() -> str:
        calls["n"] += 1
        raise ProgrammingError("syntax error")

    with pytest.raises(ProgrammingError):
        client._with_retry(bad)
    assert calls["n"] == 1
