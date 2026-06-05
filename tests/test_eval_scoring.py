"""Phase 6 unit tests for the eval scoring functions. No database, no LLM.

Covers the three scoring primitives the harness is judged on:
- execution_accuracy (PRIMARY): multiset / sequence comparison after cell normalization.
- structural_similarity (SECONDARY): sqlglot-normalized diff ratio, diagnostic only.
- retrieval_metrics: did the agent surface the gold tables.

These are pure + deterministic, so they run on the CI fast path.
"""

from __future__ import annotations

from decimal import Decimal

from agentic_text_to_sql.eval.scoring import (
    RetrievalScore,
    execution_accuracy,
    retrieval_metrics,
    structural_similarity,
)

# --------------------------------------------------------------------------- #
# execution_accuracy
# --------------------------------------------------------------------------- #


def test_execution_accuracy_identical_rows_true() -> None:
    rows = [("DE", 10), ("UK", 20)]
    assert execution_accuracy(rows, rows, ordered=False) is True


def test_execution_accuracy_different_values_false() -> None:
    agent = [("DE", 10), ("UK", 20)]
    reference = [("DE", 10), ("UK", 99)]
    assert execution_accuracy(agent, reference, ordered=False) is False


def test_execution_accuracy_order_insensitive_shuffled_rows_true() -> None:
    agent = [("UK", 20), ("DE", 10)]
    reference = [("DE", 10), ("UK", 20)]
    assert execution_accuracy(agent, reference, ordered=False) is True


def test_execution_accuracy_order_sensitive_different_row_order_false() -> None:
    agent = [("UK", 20), ("DE", 10)]
    reference = [("DE", 10), ("UK", 20)]
    assert execution_accuracy(agent, reference, ordered=True) is False


def test_execution_accuracy_column_order_insensitive_true() -> None:
    """The normalizer sorts cells WITHIN each row (order_sensitive_columns is always
    False inside execution_accuracy), so ("DE", 10) and (10, "DE") compare equal."""
    agent = [("DE", 10)]
    reference = [(10, "DE")]
    assert execution_accuracy(agent, reference, ordered=False) is True


def test_execution_accuracy_numeric_tolerance_rounds_to_2dp() -> None:
    # Decimal('10.00') vs float 10.004 both normalize to "10.00" -> equal.
    agent = [(Decimal("10.00"),)]
    reference = [(10.004,)]
    assert execution_accuracy(agent, reference, ordered=False) is True


def test_execution_accuracy_numeric_difference_beyond_2dp_false() -> None:
    agent = [(10.00,)]
    reference = [(10.01,)]
    assert execution_accuracy(agent, reference, ordered=False) is False


def test_execution_accuracy_agent_none_is_false() -> None:
    assert execution_accuracy(None, [("DE", 10)], ordered=False) is False
    assert execution_accuracy(None, [("DE", 10)], ordered=True) is False


# --------------------------------------------------------------------------- #
# structural_similarity
# --------------------------------------------------------------------------- #


def test_structural_similarity_identical_sql_is_one() -> None:
    sql = "SELECT country, SUM(revenue_gbp) FROM fct_sales GROUP BY country"
    assert structural_similarity(sql, sql) == 1.0


def test_structural_similarity_agent_none_is_zero() -> None:
    assert structural_similarity(None, "SELECT 1 FROM fct_sales") == 0.0


def test_structural_similarity_different_valid_selects_strictly_between() -> None:
    agent = "SELECT country FROM dim_country"
    reference = "SELECT region, country FROM dim_country WHERE region = 'DACH'"
    score = structural_similarity(agent, reference)
    assert 0.0 < score < 1.0


def test_structural_similarity_garbage_does_not_raise() -> None:
    score = structural_similarity("SELEKT *** FROM WHERE", "SELECT 1 FROM fct_sales")
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


# --------------------------------------------------------------------------- #
# retrieval_metrics
# --------------------------------------------------------------------------- #


def test_retrieval_superset_ok_and_full_recall() -> None:
    score = retrieval_metrics(
        ["fct_sales", "dim_country", "dim_date"], ["fct_sales", "dim_country"]
    )
    assert isinstance(score, RetrievalScore)
    assert score.ok is True
    assert score.recall == 1.0


def test_retrieval_missing_gold_table_not_ok_and_low_recall() -> None:
    score = retrieval_metrics(["fct_sales"], ["fct_sales", "dim_country"])
    assert score.ok is False
    assert score.recall < 1.0
    assert score.recall == 0.5


def test_retrieval_precision_reflects_extra_retrieved_tables() -> None:
    # 2 retrieved, 1 relevant -> precision 0.5; recall still full so ok is True.
    score = retrieval_metrics(["fct_sales", "dim_unused"], ["fct_sales"])
    assert score.precision == 0.5
    assert score.recall == 1.0
    assert score.ok is True


def test_retrieval_empty_gold_is_unconstrained_ok() -> None:
    score = retrieval_metrics(["fct_sales", "dim_country"], [])
    assert score.ok is True
    assert score.precision == 1.0
    assert score.recall == 1.0
