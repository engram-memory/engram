"""Engram configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class EngramConfig(BaseModel):
    """Global configuration for an Engram instance."""

    db_path: Path = Field(
        default_factory=lambda: Path.home() / ".engram" / "memory.db",
    )
    storage_backend: str = "sqlite"
    enable_embeddings: bool = True
    embedding_model: str = "all-MiniLM-L6-v2"
    default_namespace: str = "default"
    auto_decay: bool = False
    decay_rate: float = Field(default=0.01, ge=0.0, le=1.0)
    api_key: str | None = None
