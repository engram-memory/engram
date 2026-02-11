"""Local sentence-transformers embedding provider."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class LocalEmbedding:
    """Wraps a ``sentence-transformers`` model for local embedding."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "Install the embeddings extra: pip install engram-ai[embeddings]"
            ) from exc
        self._model = SentenceTransformer(model_name)
        self._dims: int = self._model.get_sentence_embedding_dimension()  # type: ignore[assignment]

    @property
    def dimensions(self) -> int:
        return self._dims

    def embed(self, text: str) -> list[float]:
        vec = self._model.encode(text)
        return vec.tolist()
