"""Embedding providers."""

from engram.embeddings.base import EmbeddingProvider
from engram.embeddings.none import NoopEmbedding

__all__ = ["EmbeddingProvider", "NoopEmbedding"]
