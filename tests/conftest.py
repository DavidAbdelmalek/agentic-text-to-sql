"""Shared test fixtures for the Phase 4 agent unit tests (no database).

The `tiny_layer` is a hand-built two-table SemanticLayer so the set returned by
`allowed_identifiers()` is small and fully known — that set is what the guardrail
resolves generated identifiers against, so pinning it makes the anti-hallucination
and repair-loop assertions deterministic.
"""

from __future__ import annotations

import pytest

from agentic_text_to_sql.semantic_layer.loader import Column, SemanticLayer, Table


@pytest.fixture
def tiny_layer() -> SemanticLayer:
    """fct_sales(sales_key, revenue_gbp, country_key) + dim_country(country_key, country).

    allowed_identifiers() is therefore exactly:
        {fct_sales, dim_country,
         sales_key, revenue_gbp, country_key, country,
         fct_sales.sales_key, fct_sales.revenue_gbp, fct_sales.country_key,
         dim_country.country_key, dim_country.country}
    """
    return SemanticLayer(
        tables=[
            Table(
                name="fct_sales",
                grain="one row per sale",
                description="Sales fact table.",
                columns=[
                    Column(
                        name="sales_key", type="bigint", description="surrogate key", is_pk=True
                    ),
                    Column(
                        name="revenue_gbp", type="numeric", description="revenue", is_measure=True
                    ),
                    Column(name="country_key", type="bigint", description="country FK", is_fk=True),
                ],
                primary_key=["sales_key"],
            ),
            Table(
                name="dim_country",
                grain="one row per country",
                description="Country dimension.",
                columns=[
                    Column(
                        name="country_key", type="bigint", description="surrogate key", is_pk=True
                    ),
                    Column(
                        name="country", type="text", description="country name", is_dimension=True
                    ),
                ],
                primary_key=["country_key"],
            ),
        ],
        joinable_paths=["fct_sales.country_key = dim_country.country_key"],
    )
