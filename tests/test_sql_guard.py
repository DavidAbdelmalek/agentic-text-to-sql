"""Phase 4 unit tests for the SQL guardrail (`sql_guard.review`). No database.

One test per rule, mirroring the guard's rule set: read-only shape, single statement,
identifier resolution (anti-hallucination), LIMIT injection, and parse failure. These are
the rules the repo is judged on, so each gets its own assertion.
"""

from __future__ import annotations

import pytest

from agentic_text_to_sql import sql_guard
from agentic_text_to_sql.semantic_layer.loader import SemanticLayer
from agentic_text_to_sql.sql_guard import Verdict

_LIMIT = 1000


def _allowed(layer: SemanticLayer) -> set[str]:
    return layer.allowed_identifiers()


def test_approve_valid_select_with_limit(tiny_layer: SemanticLayer) -> None:
    sql = (
        "SELECT c.country, SUM(f.revenue_gbp) AS revenue_gbp "
        "FROM fct_sales f JOIN dim_country c ON f.country_key = c.country_key "
        "GROUP BY c.country ORDER BY revenue_gbp DESC LIMIT 100"
    )
    result = sql_guard.review(sql, _allowed(tiny_layer), _LIMIT)
    assert result.verdict == Verdict.APPROVE
    assert result.repaired_sql is None


def test_repair_injects_limit_when_missing(tiny_layer: SemanticLayer) -> None:
    """Same valid query WITHOUT a LIMIT -> REPAIR with a LIMIT-bearing repaired_sql."""
    sql = (
        "SELECT c.country, SUM(f.revenue_gbp) AS revenue_gbp "
        "FROM fct_sales f JOIN dim_country c ON f.country_key = c.country_key "
        "GROUP BY c.country ORDER BY revenue_gbp DESC"
    )
    result = sql_guard.review(sql, _allowed(tiny_layer), _LIMIT)
    assert result.verdict == Verdict.REPAIR
    assert result.repaired_sql is not None
    assert "LIMIT" in result.repaired_sql.upper()
    assert str(_LIMIT) in result.repaired_sql


@pytest.mark.parametrize(
    "sql",
    [
        # A UNION with no top-level LIMIT (even if one arm is limited) must still be capped.
        "SELECT c.country FROM dim_country c UNION SELECT c.country FROM dim_country c",
        "SELECT c.country FROM dim_country c LIMIT 5 UNION SELECT c.country FROM dim_country c",
        # A subquery whose outer query has no LIMIT must be capped.
        "SELECT country FROM (SELECT c.country AS country FROM dim_country c) sub",
    ],
    ids=["union", "union_one_arm_limited", "subquery"],
)
def test_repair_caps_set_ops_and_subqueries(sql: str, tiny_layer: SemanticLayer) -> None:
    """Row output of set-operations and subqueries is bounded: a missing top-level LIMIT is
    repaired by injection, so an unbounded UNION/subquery can never reach the warehouse uncapped.
    (Inner-subquery scan cost is a separate control: STATEMENT_TIMEOUT + warehouse sizing.)"""
    result = sql_guard.review(sql, _allowed(tiny_layer), _LIMIT)
    assert result.verdict == Verdict.REPAIR
    assert result.repaired_sql is not None
    assert str(_LIMIT) in result.repaired_sql


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM fct_sales",
        "UPDATE fct_sales SET revenue_gbp = 0",
        "INSERT INTO fct_sales (sales_key) VALUES (1)",
        "DROP TABLE fct_sales",
        "CREATE TABLE evil (id int)",
    ],
    ids=["delete", "update", "insert", "drop", "create_table"],
)
def test_reject_non_read_only(sql: str, tiny_layer: SemanticLayer) -> None:
    result = sql_guard.review(sql, _allowed(tiny_layer), _LIMIT)
    assert result.verdict == Verdict.REJECT
    assert result.reasons


def test_reject_multiple_statements(tiny_layer: SemanticLayer) -> None:
    result = sql_guard.review("SELECT 1; SELECT 2", _allowed(tiny_layer), _LIMIT)
    assert result.verdict == Verdict.REJECT
    assert any("one statement" in r for r in result.reasons)


def test_reject_unknown_column_anti_hallucination(tiny_layer: SemanticLayer) -> None:
    """A generated column that does not exist in the semantic layer must be rejected,
    and the reason must name the offending identifier."""
    sql = "SELECT fct_sales.bogus FROM fct_sales LIMIT 10"
    result = sql_guard.review(sql, _allowed(tiny_layer), _LIMIT)
    assert result.verdict == Verdict.REJECT
    assert any("bogus" in r for r in result.reasons)


def test_reject_unparseable_garbage(tiny_layer: SemanticLayer) -> None:
    result = sql_guard.review("SELEKT *** FROM WHERE", _allowed(tiny_layer), _LIMIT)
    assert result.verdict == Verdict.REJECT
    assert result.reasons
