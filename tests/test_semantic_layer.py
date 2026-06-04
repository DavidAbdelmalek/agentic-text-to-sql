"""Phase 3 unit tests for the semantic-layer loader.

No database. These exercise the loader against the real
`data/semantic/semantic_layer.yaml`, plus a hand-built `SemanticLayer` for
`document()`. The `allowed_identifiers()` checks are the anti-hallucination
backstop the guardrail relies on, so they get the most attention.
"""

from __future__ import annotations

from agentic_text_to_sql.semantic_layer.loader import (
    Column,
    SemanticLayer,
    Table,
    load_semantic_layer,
)

EXPECTED_TABLES = {"fct_sales", "dim_customer", "dim_product", "dim_country", "dim_date"}


def test_load_real_layer_has_expected_tables() -> None:
    layer = load_semantic_layer()
    names = {t.name for t in layer.tables}
    assert names >= EXPECTED_TABLES
    # The five known tables are exactly what the warehouse ships with.
    assert names == EXPECTED_TABLES


def test_fct_sales_keys() -> None:
    layer = load_semantic_layer()
    fct = layer.get("fct_sales")
    assert fct is not None
    assert fct.primary_key == ["sales_key"]
    assert len(fct.foreign_keys) == 4
    # Each FK references a dimension's surrogate key.
    referenced = {fk.references for fk in fct.foreign_keys}
    assert referenced == {
        "dim_customer.customer_key",
        "dim_product.product_key",
        "dim_country.country_key",
        "dim_date.date_key",
    }


def test_get_returns_none_for_unknown_table() -> None:
    layer = load_semantic_layer()
    assert layer.get("does_not_exist") is None


def test_allowed_identifiers_anti_hallucination() -> None:
    """The guardrail resolves generated identifiers against this set: real ones
    must be present, fabricated ones must NOT be."""
    layer = load_semantic_layer()
    ids = layer.allowed_identifiers()

    # Table name, bare column name, and qualified table.column all legal.
    assert "fct_sales" in ids
    assert "revenue_gbp" in ids
    assert "fct_sales.revenue_gbp" in ids

    # A column that does not exist must never be admitted.
    assert "fct_sales.bogus_col" not in ids
    assert "bogus_col" not in ids
    # A real column qualified by the wrong table is also not a valid identifier.
    assert "dim_customer.revenue_gbp" not in ids


def test_document_includes_table_and_column_names() -> None:
    layer = SemanticLayer(
        tables=[
            Table(
                name="tiny_table",
                grain="one row per widget",
                description="A small hand-built table.",
                columns=[
                    Column(name="widget_id", type="bigint", description="surrogate key"),
                    Column(name="widget_name", type="text", description="display name"),
                ],
                primary_key=["widget_id"],
            )
        ]
    )
    doc = layer.tables[0].document()
    assert "tiny_table" in doc
    assert "widget_id" in doc
    assert "widget_name" in doc


def test_hand_built_layer_allowed_identifiers() -> None:
    layer = SemanticLayer(
        tables=[
            Table(
                name="t",
                grain="g",
                description="d",
                columns=[Column(name="c", type="int")],
            )
        ]
    )
    assert layer.allowed_identifiers() == {"t", "c", "t.c"}
