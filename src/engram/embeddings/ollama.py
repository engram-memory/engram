"""Ollama embedding provider — uses local Ollama server for GPU-accelerated embeddings."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


class OllamaEmbedding:
    """Generates embeddings via a local Ollama instance (mxbai-embed-large etc.)."""

    MAX_RETRIES = 3
    RETRY_DELAY = 2.0  # seconds

    def __init__(
        self,
        model: str = "mxbai-embed-large",
        base_url: str = "http://localhost:11434",
    ):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._dims: int | None = None

    @property
    def dimensions(self) -> int:
        if self._dims is None:
            vec = self.embed("dimension probe")
            self._dims = len(vec)
        return self._dims

    def embed(self, text: str) -> list[float]:
        """Return an embedding vector for *text* via Ollama /api/embeddings."""
        # Clean: truncate (1000 chars, avoid VRAM contention), strip nulls
        clean = text[:1000].replace("\x00", "")
        payload = json.dumps({"model": self._model, "prompt": clean}).encode()

        last_exc = None
        for attempt in range(self.MAX_RETRIES):
            req = urllib.request.Request(
                f"{self._base_url}/api/embeddings",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read())

                embedding = data.get("embedding")
                if not embedding:
                    raise RuntimeError(f"Ollama returned no embedding: {data}")

                if self._dims is None:
                    self._dims = len(embedding)
                return embedding

            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY * (attempt + 1))

        msg = f"Ollama embedding failed after {self.MAX_RETRIES} retries: {last_exc}"
        raise RuntimeError(msg) from last_exc
