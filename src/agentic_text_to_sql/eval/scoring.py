"""Scoring functions for the eval harness. Pure + deterministic so they unit-test cleanly.

- execution_accuracy (PRIMARY): do two result sets match as multisets (order-insensitive)
  after normalizing cell values? If the question is order-sensitive, compare as sequences.
- structural_similarity (SECONDARY, diagnostic only): how similar are the two SQL strings
  after sqlglot normalization. A correct query can score low here — never gate on it.
- retrieval metrics: did the agent surface the gold tables.
"""

from __future__ import annotations

import difflib
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import sqlglot

Row = tuple[Any, ...]


def _normalize_cell(value: Any) -> str:
    """Round numerics to 2dp and stringify so float/Decimal/locale noise doesn't fail a
    genuinely-equal result."""
    if value is None:
        return "∅"  # explicit null marker
    if isinstance(value, Decimal | float):
        return f"{float(value):.2f}"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return str(value)


def _normalize_row(row: Row, *, order_sensitive_columns: bool) -> tuple[str, ...]:
    cells = tuple(_normalize_cell(v) for v in row)
    # When column order can differ between agent and reference, sort cells within the row so
    # the comparison is also column-order-insensitive.
    return cells if order_sensitive_columns else tuple(sorted(cells))


def execution_accuracy(
    agent_rows: list[Row] | None,
    reference_rows: list[Row],
    *,
    ordered: bool,
) -> bool:
    if agent_rows is None:
        return False
    a = [_normalize_row(r, order_sensitive_columns=False) for r in agent_rows]
    b = [_normalize_row(r, order_sensitive_columns=False) for r in reference_rows]
    if ordered:
        return a == b
    return Counter(a) == Counter(b)


def _normalize_sql(sql: str) -> str:
    try:
        return sqlglot.parse_one(sql, read="snowflake").sql(normalize=True, comments=False).lower()
    except Exception:  # noqa: BLE001
        return sql.strip().lower()


def structural_similarity(agent_sql: str | None, reference_sql: str) -> float:
    if not agent_sql:
        return 0.0
    a, b = _normalize_sql(agent_sql), _normalize_sql(reference_sql)
    return round(difflib.SequenceMatcher(None, a, b).ratio(), 3)


@dataclass(frozen=True)
class RetrievalScore:
    precision: float
    recall: float
    ok: bool  # all gold tables retrieved


def retrieval_metrics(retrieved: list[str], gold_tables: list[str]) -> RetrievalScore:
    rset, gset = set(retrieved), set(gold_tables)
    if not gset:
        return RetrievalScore(1.0, 1.0, True)
    hit = len(rset & gset)
    precision = hit / len(rset) if rset else 0.0
    recall = hit / len(gset)
    return RetrievalScore(round(precision, 3), round(recall, 3), gset <= rset)
