"""Tests for schema retrieval.

Cover the deterministic, zero-dependency `KeywordRetriever` and the `get_retriever` factory.
They run on CI's fast lane with no database. The retriever is no longer in the agent hot path
(the full schema is sent), but it stays as the eval's retrieval-scoring target and the
documented scale swap-in, so its behaviour is still pinned.
"""

from __future__ import annotations

import pytest

from agentic_text_to_sql.config import Settings
from agentic_text_to_sql.semantic_layer.loader import load_semantic_layer
from agentic_text_to_sql.semantic_layer.retriever import (
    KeywordRetriever,
    Retrieved,
    get_retriever,
)


@pytest.fixture
def layer():
    return load_semantic_layer()


def test_keyword_retriever_is_deterministic(layer) -> None:
    r = KeywordRetriever(layer)
    first = r.retrieve("total revenue by country", k=5)
    second = r.retrieve("total revenue by country", k=5)
    assert first == second
    # Sanity: results are Retrieved instances sorted by score descending.
    assert all(isinstance(x, Retrieved) for x in first)
    scores = [x.score for x in first]
    assert scores == sorted(scores, reverse=True)


def test_keyword_retriever_relevance_revenue_by_country(layer) -> None:
    r = KeywordRetriever(layer)
    results = r.retrieve("total revenue by country", k=3)
    tables = {x.table for x in results}
    assert "fct_sales" in tables
    assert "dim_country" in tables


def test_keyword_retriever_relevance_units_per_product(layer) -> None:
    r = KeywordRetriever(layer)
    results = r.retrieve("how many units of each product", k=3)
    tables = {x.table for x in results}
    assert "dim_product" in tables


def test_keyword_retriever_filters_zero_score(layer) -> None:
    """Tables whose tokens don't overlap the question must not appear, and every
    returned result has a strictly positive score."""
    r = KeywordRetriever(layer)
    results = r.retrieve("total revenue by country", k=10)
    assert all(x.score > 0 for x in results)
    # A purely date-oriented dimension shares no tokens with this question.
    assert "dim_date" not in {x.table for x in results}


def test_keyword_retriever_no_match_returns_empty(layer) -> None:
    r = KeywordRetriever(layer)
    # Nonsense with no overlap -> nothing scores above zero.
    assert r.retrieve("zzzzz qqqqq wwwww", k=3) == []


def test_keyword_retriever_respects_k(layer) -> None:
    r = KeywordRetriever(layer)
    results = r.retrieve("revenue customer product country date", k=2)
    assert len(results) <= 2


def test_get_retriever_returns_keyword(layer) -> None:
    """The factory yields a KeywordRetriever with no DB connection and no model load."""
    retriever = get_retriever(Settings(), layer)
    assert isinstance(retriever, KeywordRetriever)
