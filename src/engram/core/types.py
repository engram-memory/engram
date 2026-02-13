"""Core Pydantic models for Engram."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """Categories of memories."""

    fact = "fact"
    preference = "preference"
    decision = "decision"
    error_fix = "error_fix"
    pattern = "pattern"
    workflow = "workflow"
    summary = "summary"
    custom = "custom"


class MemoryEntry(BaseModel):
    """A single memory unit."""

    id: int | None = None
    content: str
    memory_type: MemoryType = MemoryType.fact
    importance: int = Field(default=5, ge=1, le=10)
    namespace: str = "default"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str | None = None
    embedding: list[float] | None = None
    decay_score: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    accessed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = 0

    def compute_hash(self) -> str:
        """SHA-256 content hash (first 16 hex chars) for deduplication."""
        return hashlib.sha256(self.content.encode()).hexdigest()[:16]

    def model_post_init(self, __context: Any) -> None:
        if self.content_hash is None:
            self.content_hash = self.compute_hash()


class SearchResult(BaseModel):
    """A search hit with relevance metadata."""

    memory: MemoryEntry
    score: float = 0.0
    match_type: str = "fts"  # "fts", "semantic", "like"
