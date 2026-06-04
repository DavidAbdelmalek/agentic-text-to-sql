"""Phase 4 unit tests for the read-only client's static guard (`assert_read_only`).

Pure parsing only — no database connection. This is the belt-and-braces check that sits
in front of the read-only Postgres role: the client must refuse anything that isn't a
single read-only statement before it ever reaches the engine.
"""

from __future__ import annotations

import pytest
from sqlglot import exp

from agentic_text_to_sql.db.read_only_client import UnsafeQueryError, assert_read_only


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
