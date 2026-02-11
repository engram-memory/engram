"""Storage backend protocol."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from engram.core.types import MemoryEntry, SearchResult


@runtime_checkable
class StorageBackend(Protocol):
    """Minimal interface every storage backend must implement."""

    def store(self, entry: MemoryEntry) -> int | None:
        """Persist *entry*. Return its id, or ``None`` if duplicate."""
        ...

    def get(self, memory_id: int) -> MemoryEntry | None:
        """Fetch a single memory by id."""
        ...

    def search_text(
        self,
        query: str,
        *,
        namespace: str | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """Full-text search."""
        ...

    def search_vector(
        self,
        embedding: list[float],
        *,
        namespace: str | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """Semantic / vector search."""
        ...

    def list_memories(
        self,
        *,
        namespace: str | None = None,
        memory_type: str | None = None,
        min_importance: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """List memories with optional filters."""
        ...

    def delete(self, memory_id: int) -> bool:
        """Delete by id. Return ``True`` if found."""
        ...

    def update(self, memory_id: int, **fields: Any) -> MemoryEntry | None:
        """Partial update. Return the updated entry or ``None``."""
        ...

    def stats(self, namespace: str | None = None) -> dict[str, Any]:
        """Return aggregate statistics."""
        ...
