"""Engram configuration."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class EngramConfig(BaseModel):
    """Global configuration for an Engram instance."""

    db_path: Path = Field(
        default_factory=lambda: Path.home() / ".engram" / "memory.db",
    )
    storage_backend: str = "sqlite"
    enable_embeddings: bool = True
    embedding_provider: str = Field(
        default_factory=lambda: os.environ.get("ENGRAM_EMBEDDING_PROVIDER", "ollama"),
    )  # "ollama" (GPU), "local", or "fake" (CI/testing)
    embedding_model: str = "mxbai-embed-large"
    ollama_base_url: str = "http://localhost:11434"
    default_namespace: str = "default"
    auto_decay: bool = False
    decay_rate: float = Field(default=0.01, ge=0.0, le=1.0)
    api_key: str | None = None
