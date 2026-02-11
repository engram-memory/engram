"""No-op embedding provider (default — FTS5 only, no vectors)."""

from __future__ import annotations


class NoopEmbedding:
    """Returns nothing. Used when embeddings are disabled."""

    @property
    def dimensions(self) -> int:
        return 0

    def embed(self, text: str) -> list[float]:
        return []
