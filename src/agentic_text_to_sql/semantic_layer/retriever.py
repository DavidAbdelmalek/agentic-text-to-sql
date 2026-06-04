"""Schema retrieval: given a natural-language question, return the most relevant tables to
put in front of the SQL generator. Two backends behind one interface:

- KeywordRetriever  — zero-dependency, deterministic token-overlap. Default for tests/CI and
  the offline/mock path. For a handful of tables it is genuinely sufficient.
- VectorRetriever   — pgvector cosine over fastembed embeddings (built by build.py). The
  headline path; it's the pattern that scales to hundreds of tables.

Why retrieval at all (interview): putting only the relevant tables/columns in the prompt
keeps it small AND bounds what the model can reference, which—together with the guardrail's
identifier check—is how we stop column hallucination.
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


class VectorRetriever:
    """pgvector cosine over fastembed embeddings built into the `semantic` schema."""

    def __init__(self, settings: Settings, layer: SemanticLayer) -> None:
        import psycopg

        from agentic_text_to_sql.semantic_layer.embeddings import get_embedder

        self._settings = settings
        self._layer = layer
        # Cheap reachability check FIRST, so we fall back to keyword without paying the
        # model-download cost when the vector store hasn't been built yet.
        with psycopg.connect(settings.agent_database_url) as conn:
            exists = conn.execute("SELECT to_regclass('semantic.table_embeddings')").fetchone()
        if not exists or exists[0] is None:
            raise RuntimeError("semantic.table_embeddings not found; run `make semantic`")
        self._embedder = get_embedder(settings)

    def retrieve(self, question: str, k: int = 3) -> list[Retrieved]:
        import psycopg
        from pgvector.psycopg import register_vector

        vec = self._embedder.embed([question])[0]
        with psycopg.connect(self._settings.agent_database_url) as conn:
            register_vector(conn)
            rows = conn.execute(
                "SELECT table_name, 1 - (embedding <=> %s::vector) AS score "
                "FROM semantic.table_embeddings ORDER BY embedding <=> %s::vector LIMIT %s",
                (vec, vec, k),
            ).fetchall()
        return [Retrieved(table=str(name), score=float(score)) for name, score in rows]


def get_retriever(settings: Settings, layer: SemanticLayer | None = None) -> Retriever:
    """Pick a backend. Vector when embeddings are configured AND the store is reachable;
    otherwise the deterministic keyword retriever."""
    layer = layer or load_semantic_layer()
    if settings.embed_provider == "local":
        try:
            return VectorRetriever(settings, layer)
        except Exception:  # noqa: BLE001 — any failure (no model/store) -> safe fallback
            return KeywordRetriever(layer)
    return KeywordRetriever(layer)
