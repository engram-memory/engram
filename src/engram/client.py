"""User-facing Memory client — the 5-line API."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engram.config import EngramConfig
from engram.context import ContextResult, build_context
from engram.core.types import MemoryEntry, MemoryType, SearchResult
from engram.exceptions import MemoryNotFoundError
from engram.storage.sqlite_backend import SQLiteBackend


class Memory:
    """Universal memory layer for AI agents.

    >>> mem = Memory()
    >>> mem.store("User prefers Python", type="preference", importance=8)
    1
    >>> results = mem.search("programming language")
    >>> context = mem.recall(limit=10)
    """

    def __init__(
        self,
        config: EngramConfig | None = None,
        *,
        namespace: str | None = None,
        db_path: str | Path | None = None,
    ):
        self._config = config or EngramConfig()
        if db_path:
            self._config.db_path = Path(db_path)
        self._namespace = namespace or self._config.default_namespace
        self._backend = SQLiteBackend(self._config.db_path)

        # Optional embedding provider (graceful fallback)
        self._embedder = None
        if self._config.enable_embeddings:
            try:
                from engram.embeddings.local import LocalEmbedding

                self._embedder = LocalEmbedding(self._config.embedding_model)
            except ImportError:
                import warnings

                warnings.warn(
                    "sentence-transformers not installed. Embeddings disabled. "
                    "Install with: pip install engram-core[embeddings]",
                    stacklevel=2,
                )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(
        self,
        content: str,
        *,
        type: str = "fact",
        importance: int = 5,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        namespace: str | None = None,
        ttl_days: int | None = None,
    ) -> int | None:
        """Store a memory. Returns the id, or ``None`` if duplicate."""
        from datetime import timedelta

        expires_at = None
        if ttl_days is not None and ttl_days > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)

        entry = MemoryEntry(
            content=content,
            memory_type=MemoryType(type),
            importance=importance,
            namespace=namespace or self._namespace,
            tags=tags or [],
            metadata=metadata or {},
            expires_at=expires_at,
        )
        if self._embedder:
            entry.embedding = self._embedder.embed(content)
        return self._backend.store(entry)

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        namespace: str | None = None,
        semantic: bool = False,
    ) -> list[SearchResult]:
        """Search memories by text (FTS5) or semantically."""
        ns = namespace or self._namespace
        if semantic and self._embedder:
            vec = self._embedder.embed(query)
            return self._backend.search_vector(vec, namespace=ns, limit=limit)
        return self._backend.search_text(query, namespace=ns, limit=limit)

    def recall(
        self,
        *,
        limit: int = 20,
        namespace: str | None = None,
        min_importance: int = 7,
    ) -> list[MemoryEntry]:
        """Retrieve highest-priority memories for context injection."""
        return self._backend.get_priority_memories(
            namespace=namespace or self._namespace,
            limit=limit,
            min_importance=min_importance,
        )

    def context(
        self,
        prompt: str,
        *,
        max_tokens: int = 2000,
        namespace: str | None = None,
        min_importance: int = 3,
    ) -> ContextResult:
        """Build a token-budgeted context from the most relevant memories."""
        return build_context(
            self._backend,
            self._embedder,
            prompt,
            max_tokens=max_tokens,
            namespace=namespace or self._namespace,
            min_importance=min_importance,
        )

    def get(self, memory_id: int) -> MemoryEntry:
        """Fetch a single memory by id."""
        entry = self._backend.get(memory_id)
        if entry is None:
            raise MemoryNotFoundError(memory_id)
        return entry

    def delete(self, memory_id: int) -> bool:
        """Delete a memory. Returns True if it existed."""
        return self._backend.delete(memory_id)

    def update(self, memory_id: int, **fields: Any) -> MemoryEntry:
        """Partial update of a memory's fields."""
        entry = self._backend.update(memory_id, **fields)
        if entry is None:
            raise MemoryNotFoundError(memory_id)
        return entry

    def list(
        self,
        *,
        namespace: str | None = None,
        type: str | None = None,
        min_importance: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """List memories with optional filters."""
        return self._backend.list_memories(
            namespace=namespace or self._namespace,
            memory_type=type,
            min_importance=min_importance,
            limit=limit,
            offset=offset,
        )

    def stats(self, namespace: str | None = None) -> dict[str, Any]:
        """Return aggregate statistics."""
        return self._backend.stats(namespace=namespace or self._namespace)

    def prune(
        self,
        *,
        days: int = 30,
        min_importance: int = 3,
        namespace: str | None = None,
    ) -> int:
        """Remove old, low-importance, rarely-accessed memories."""
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        ns = namespace or self._namespace

        with self._backend._conn() as conn:
            cur = conn.execute(
                """
                DELETE FROM memories
                WHERE accessed_at < ?
                  AND importance < ?
                  AND access_count < 3
                  AND namespace = ?
                """,
                (cutoff.isoformat(), min_importance, ns),
            )
            conn.commit()
            return cur.rowcount

    def backfill_embeddings(self, *, namespace: str | None = None, batch_size: int = 100) -> int:
        """Generate embeddings for memories that don't have them. Returns count."""
        if not self._embedder:
            return 0
        ns = namespace or self._namespace
        count = 0
        offset = 0
        while True:
            entries = self._backend.list_memories_without_embeddings(
                namespace=ns,
                limit=batch_size,
                offset=offset,
            )
            if not entries:
                break
            for entry in entries:
                embedding = self._embedder.embed(entry.content)
                self._backend.update_embedding(entry.id, embedding)
                count += 1
            offset += batch_size
        return count

    def cleanup_expired(self, *, namespace: str | None = None) -> int:
        """Permanently delete expired memories. Returns count of removed entries."""
        return self._backend.delete_expired(namespace=namespace or self._namespace)

    def export_memories(
        self,
        *,
        namespace: str | None = None,
        format: str = "json",
    ) -> str:
        """Export all memories in a namespace as JSON or Markdown."""
        entries = self.list(namespace=namespace, limit=10000)
        if format == "markdown":
            lines = [f"# Engram Memory Export ({datetime.now(timezone.utc).isoformat()})\n"]
            for e in entries:
                lines.append(f"## [{e.memory_type.value}] (importance: {e.importance})")
                lines.append(e.content)
                if e.tags:
                    lines.append(f"Tags: {', '.join(e.tags)}")
                lines.append("")
            return "\n".join(lines)
        return json.dumps(
            [e.model_dump(mode="json", exclude={"embedding"}) for e in entries],
            indent=2,
            default=str,
        )

    def import_memories(self, data: str) -> int:
        """Import memories from a JSON string. Returns count of new memories."""
        items = json.loads(data)
        count = 0
        for item in items:
            entry = MemoryEntry(**item)
            if self._backend.store(entry) is not None:
                count += 1
        return count
