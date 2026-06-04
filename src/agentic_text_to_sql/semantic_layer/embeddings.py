"""Embedding providers for schema retrieval. Local default = fastembed (ONNX BGE-small,
no torch). Pluggable to OpenAI/Azure later behind the same Embedder protocol."""

from __future__ import annotations

from typing import Protocol

from agentic_text_to_sql.config import Settings


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedEmbedder:
    """Local, free, CPU. Downloads the ONNX model once on first use (then cached)."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name)
        # bge-small-en-v1.5 is 384-dim; read it off a probe so the DB column matches.
        self.dim = len(next(iter(self._model.embed(["dim probe"]))).tolist())

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts)]


def get_embedder(settings: Settings) -> Embedder:
    """Return the configured embedder. Only 'local' (fastembed) is wired today; OpenAI/Azure
    are TODO behind this same factory so callers never change."""
    if settings.embed_provider == "local":
        return FastEmbedEmbedder(settings.embed_model)
    raise NotImplementedError(
        f"embed_provider={settings.embed_provider!r} not implemented; use 'local' or the "
        f"keyword retriever (no embeddings needed)."
    )
