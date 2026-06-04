"""`make semantic` / `python -m agentic_text_to_sql.semantic_layer.build`.

Embeds each table's semantic-layer document and stores the vectors in a `semantic` schema
(pgvector), then grants the read-only role SELECT on it so the retriever can query it. Runs
as the BUILD superuser. Idempotent: rebuilds the embeddings table from scratch.

The semantic-layer YAML itself is authored by the schema-explorer subagent; this step only
indexes it for retrieval.
"""

from __future__ import annotations

import os

import psycopg
from pgvector.psycopg import register_vector

from agentic_text_to_sql.config import get_settings, superuser_dsn
from agentic_text_to_sql.semantic_layer.embeddings import get_embedder
from agentic_text_to_sql.semantic_layer.loader import load_semantic_layer


def main() -> None:
    settings = get_settings()
    layer = load_semantic_layer()
    embedder = get_embedder(settings)
    agent_user = os.environ.get("AGENT_DB_USER", "agent_ro")

    docs = [(t.name, t.document()) for t in layer.tables]
    vectors = embedder.embed([d for _, d in docs])
    dim = embedder.dim

    with psycopg.connect(superuser_dsn(), autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute("CREATE SCHEMA IF NOT EXISTS semantic")
        conn.execute("DROP TABLE IF EXISTS semantic.table_embeddings")
        conn.execute(
            f"CREATE TABLE semantic.table_embeddings ("
            f"  table_name text PRIMARY KEY,"
            f"  document   text NOT NULL,"
            f"  embedding  vector({dim}) NOT NULL)"
        )
        register_vector(conn)
        with conn.cursor() as cur:
            for (name, document), vec in zip(docs, vectors, strict=True):
                cur.execute(
                    "INSERT INTO semantic.table_embeddings (table_name, document, embedding) "
                    "VALUES (%s, %s, %s)",
                    (name, document, vec),
                )
        # Let the read-only agent role read the embeddings (read-only on this schema too).
        conn.execute(f"GRANT USAGE ON SCHEMA semantic TO {agent_user}")
        conn.execute(f"GRANT SELECT ON semantic.table_embeddings TO {agent_user}")

    print(
        f"semantic build OK -> semantic.table_embeddings: {len(docs)} tables embedded "
        f"({dim}-dim, model={settings.embed_model})."
    )


if __name__ == "__main__":
    main()
