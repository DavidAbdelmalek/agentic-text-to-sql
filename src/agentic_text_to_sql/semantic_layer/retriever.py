"""Schema retrieval: given a natural-language question, return the most relevant tables.

The agent itself no longer retrieves — for the fixed 5-table star it sends the full schema
(retrieval can only drop a table the query needs; the guard, not retrieval, stops
hallucination). This module stays behind the `Retriever` interface as (a) the eval's
retrieval-correctness scoring target and (b) the documented swap-in for when the warehouse
grows past the context budget — at which point a Cortex Search / vector backend implements the
same `retrieve()` contract. KeywordRetriever is the zero-dependency, deterministic default.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Protocol

from agentic_text_to_sql.config import Settings
from agentic_text_to_sql.semantic_layer.loader import SemanticLayer, load_semantic_layer

_TOKEN = re.compile(r"[a-z0-9_]+")

# Maps natural-language words to schema vocabulary so lexical retrieval isn't brittle.
# (The keyword retriever has no stemmer, so plurals/variants are mapped explicitly. The
# vector retriever handles these semantically — this is the lexical path's known weakness.)
_SYNONYMS = {
    "sales": "revenue",
    "sale": "revenue",
    "spend": "revenue",
    "spent": "revenue",
    "turnover": "revenue",
    "sold": "quantity",
    "units": "quantity",
    "unit": "quantity",
    "order": "invoice",
    "orders": "invoice",
    "invoices": "invoice",
    "client": "customer",
    "clients": "customer",
    "customers": "customer",
    "item": "product",
    "items": "product",
    "products": "product",
    "nation": "country",
    "countries": "country",
    "region": "region",
    "regions": "region",
    "monthly": "month",
    "yearly": "year",
    "annual": "year",
    "quarterly": "quarter",
    "daily": "day",
}


def _tokenize(text: str) -> list[str]:
    toks = _TOKEN.findall(text.lower())
    return [_SYNONYMS.get(t, t) for t in toks]


@dataclass(frozen=True)
class Retrieved:
    table: str
    score: float


class Retriever(Protocol):
    def retrieve(self, question: str, k: int = 3) -> list[Retrieved]: ...


class KeywordRetriever:
    """IDF-weighted token overlap between the question and each table's document."""

    def __init__(self, layer: SemanticLayer) -> None:
        self._layer = layer
        self._docs = {t.name: set(_tokenize(t.document())) for t in layer.tables}
        n = len(self._docs)
        df: dict[str, int] = {}
        for tokens in self._docs.values():
            for tok in tokens:
                df[tok] = df.get(tok, 0) + 1
        # Smoothed IDF: rare tokens (e.g. 'revenue', 'country') weigh more than common ones.
        self._idf = {tok: math.log((n + 1) / (c + 0.5)) for tok, c in df.items()}

    def retrieve(self, question: str, k: int = 3) -> list[Retrieved]:
        q = set(_tokenize(question))
        scored = [
            Retrieved(name, sum(self._idf.get(tok, 0.0) for tok in (q & toks)))
            for name, toks in self._docs.items()
        ]
        scored.sort(key=lambda r: (-r.score, r.table))
        return [r for r in scored if r.score > 0][:k]


def get_retriever(settings: Settings, layer: SemanticLayer | None = None) -> Retriever:
    """Return the retrieval backend. Keyword-only today; a vector/Cortex-Search backend would
    slot in here behind the same `Retriever` interface at scale (see module docstring)."""
    return KeywordRetriever(layer or load_semantic_layer())
