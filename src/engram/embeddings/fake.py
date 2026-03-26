"""Fake embedding provider for CI/testing — deterministic hash-based vectors."""

from __future__ import annotations

import hashlib

DIMENSIONS = 1024  # Same as mxbai-embed-large


class FakeEmbedding:
    """Generates deterministic fake embeddings from text hash.

    Produces consistent vectors (same text → same vector) without
    requiring Ollama or any ML model. Suitable for CI and tests.
    """

    @property
    def dimensions(self) -> int:
        return DIMENSIONS

    def embed(self, text: str) -> list[float]:
        """Return a deterministic pseudo-embedding based on text hash."""
        h = hashlib.sha256(text.encode()).digest()
        # Expand hash to fill DIMENSIONS floats (cycle through hash bytes)
        raw = []
        for i in range(DIMENSIONS):
            byte_val = h[i % len(h)]
            # Normalize to [-1, 1] range like real embeddings
            raw.append((byte_val / 127.5) - 1.0)
        # L2 normalize
        norm = sum(x * x for x in raw) ** 0.5
        if norm > 0:
            raw = [x / norm for x in raw]
        return raw
