-- Runs once on first cluster init, as superuser, inside POSTGRES_DB.
-- pgvector powers schema-retrieval embeddings (semantic layer search).
CREATE EXTENSION IF NOT EXISTS vector;
