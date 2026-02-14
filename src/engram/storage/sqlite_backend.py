"""SQLite + FTS5 storage backend."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engram.core.dedup import content_hash
from engram.core.search import sanitize_fts_query
from engram.core.types import MemoryEntry, MemoryType, SearchResult

_NOT_EXPIRED = "(expires_at IS NULL OR expires_at > datetime('now'))"


class SQLiteBackend:
    """SQLite storage with FTS5 full-text search."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    memory_type TEXT NOT NULL DEFAULT 'fact',
                    importance INTEGER DEFAULT 5,
                    namespace TEXT DEFAULT 'default',
                    tags TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}',
                    content_hash TEXT UNIQUE,
                    embedding BLOB,
                    decay_score REAL DEFAULT 1.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    access_count INTEGER DEFAULT 0,
                    expires_at TIMESTAMP
                )
            """)

            # Migration: add expires_at to existing tables
            self._migrate_add_column(conn, "memories", "expires_at", "TIMESTAMP")

            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                    content, tags, namespace,
                    content='memories',
                    content_rowid='id'
                )
            """)

            # Keep FTS in sync
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                    INSERT INTO memories_fts(rowid, content, tags, namespace)
                    VALUES (new.id, new.content, new.tags, new.namespace);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content, tags, namespace)
                    VALUES ('delete', old.id, old.content, old.tags, old.namespace);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content, tags, namespace)
                    VALUES ('delete', old.id, old.content, old.tags, old.namespace);
                    INSERT INTO memories_fts(rowid, content, tags, namespace)
                    VALUES (new.id, new.content, new.tags, new.namespace);
                END
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON memories(memory_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_importance ON memories(importance DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_namespace ON memories(namespace)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hash ON memories(content_hash)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ns_importance "
                "ON memories(namespace, importance DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_priority "
                "ON memories(importance DESC, access_count DESC, accessed_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_expires_at ON memories(expires_at)"
            )
            conn.commit()

    @staticmethod
    def _migrate_add_column(
        conn: sqlite3.Connection, table: str, column: str, col_type: str
    ) -> None:
        """Safely add a column if it doesn't exist."""
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def store(self, entry: MemoryEntry) -> int | None:
        """Insert a memory. On duplicate hash, bump access_count instead."""
        if not entry.content_hash:
            entry.content_hash = content_hash(entry.content)

        tags_str = json.dumps(entry.tags)
        meta_str = json.dumps(entry.metadata)
        emb_blob = _encode_embedding(entry.embedding)
        expires_str = entry.expires_at.isoformat() if entry.expires_at else None

        try:
            with self._conn() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO memories
                        (content, memory_type, importance, namespace, tags, metadata,
                         content_hash, embedding, decay_score,
                         created_at, accessed_at, access_count, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.content,
                        entry.memory_type.value,
                        entry.importance,
                        entry.namespace,
                        tags_str,
                        meta_str,
                        entry.content_hash,
                        emb_blob,
                        entry.decay_score,
                        entry.created_at.isoformat(),
                        entry.accessed_at.isoformat(),
                        entry.access_count,
                        expires_str,
                    ),
                )
                conn.commit()
                return cur.lastrowid
        except sqlite3.IntegrityError:
            # Duplicate — bump access count + importance
            with self._conn() as conn:
                conn.execute(
                    """
                    UPDATE memories
                    SET access_count = access_count + 1,
                        accessed_at  = CURRENT_TIMESTAMP,
                        importance   = MAX(importance, ?)
                    WHERE content_hash = ?
                    """,
                    (entry.importance, entry.content_hash),
                )
                conn.commit()
            return None

    def get(self, memory_id: int) -> MemoryEntry | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"SELECT * FROM memories WHERE id = ? AND {_NOT_EXPIRED}",
                (memory_id,),
            ).fetchone()
            if row is None:
                return None
            # Touch access
            conn.execute(
                "UPDATE memories SET access_count = access_count + 1, "
                "accessed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (memory_id,),
            )
            conn.commit()
            return _row_to_entry(row)

    def search_text(
        self,
        query: str,
        *,
        namespace: str | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        fts_expr = sanitize_fts_query(query)
        if fts_expr is None:
            return []

        ns_filter = ""
        params: list[Any] = [fts_expr]
        if namespace:
            ns_filter = "AND m.namespace = ?"
            params.append(namespace)
        params.append(limit)

        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    f"""
                    SELECT m.*, rank AS _score
                    FROM memories m
                    JOIN memories_fts fts ON m.id = fts.rowid
                    WHERE memories_fts MATCH ? AND {_NOT_EXPIRED} {ns_filter}
                    ORDER BY rank, m.importance DESC
                    LIMIT ?
                    """,
                    params,
                ).fetchall()
                return [
                    SearchResult(
                        memory=_row_to_entry(r),
                        score=abs(r["_score"]),
                        match_type="fts",
                    )
                    for r in rows
                ]
            except sqlite3.OperationalError:
                # FTS5 query failed — fallback to LIKE
                words = query.split()
                if not words:
                    return []
                like = f"%{words[0]}%"
                like_params: list[Any] = [like]
                ns_like = ""
                if namespace:
                    ns_like = "AND namespace = ?"
                    like_params.append(namespace)
                like_params.append(limit)
                rows = conn.execute(
                    f"""
                    SELECT * FROM memories
                    WHERE content LIKE ? AND {_NOT_EXPIRED} {ns_like}
                    ORDER BY importance DESC
                    LIMIT ?
                    """,
                    like_params,
                ).fetchall()
                return [
                    SearchResult(memory=_row_to_entry(r), score=0.0, match_type="like")
                    for r in rows
                ]

    def search_vector(
        self,
        embedding: list[float],
        *,
        namespace: str | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """Brute-force cosine similarity against stored embeddings."""
        ns_filter = f"WHERE {_NOT_EXPIRED}"
        params: list[Any] = []
        if namespace:
            ns_filter += " AND namespace = ?"
            params.append(namespace)

        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(f"SELECT * FROM memories {ns_filter}", params).fetchall()

        results: list[SearchResult] = []
        for r in rows:
            stored = _decode_embedding(r["embedding"])
            if stored is None:
                continue
            sim = _cosine_similarity(embedding, stored)
            results.append(SearchResult(memory=_row_to_entry(r), score=sim, match_type="semantic"))
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]

    def list_memories(
        self,
        *,
        namespace: str | None = None,
        memory_type: str | None = None,
        min_importance: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        clauses: list[str] = [_NOT_EXPIRED]
        params: list[Any] = []

        if namespace:
            clauses.append("namespace = ?")
            params.append(namespace)
        if memory_type:
            clauses.append("memory_type = ?")
            params.append(memory_type)
        if min_importance is not None:
            clauses.append("importance >= ?")
            params.append(min_importance)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.extend([limit, offset])

        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM memories {where} "
                "ORDER BY importance DESC, accessed_at DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
            return [_row_to_entry(r) for r in rows]

    def delete(self, memory_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            return cur.rowcount > 0

    def update(self, memory_id: int, **fields: Any) -> MemoryEntry | None:
        existing = self.get(memory_id)
        if existing is None:
            return None

        allowed = {
            "content",
            "memory_type",
            "importance",
            "namespace",
            "tags",
            "metadata",
            "decay_score",
        }
        sets: list[str] = []
        params: list[Any] = []

        for key, val in fields.items():
            if key not in allowed:
                continue
            if key == "tags":
                val = json.dumps(val)
            elif key == "metadata":
                val = json.dumps(val)
            elif key == "memory_type" and isinstance(val, MemoryType):
                val = val.value
            sets.append(f"{key} = ?")
            params.append(val)

        if "content" in fields:
            new_hash = content_hash(fields["content"])
            sets.append("content_hash = ?")
            params.append(new_hash)

        if not sets:
            return existing

        params.append(memory_id)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE memories SET {', '.join(sets)} WHERE id = ?",
                params,
            )
            conn.commit()

        return self.get(memory_id)

    def stats(self, namespace: str | None = None) -> dict[str, Any]:
        base_filter = f"WHERE {_NOT_EXPIRED}"
        params: list[Any] = []
        if namespace:
            base_filter += " AND namespace = ?"
            params.append(namespace)

        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            total = conn.execute(
                f"SELECT COUNT(*) AS count FROM memories {base_filter}", params
            ).fetchone()["count"]

            by_type = conn.execute(
                f"SELECT memory_type, COUNT(*) AS count FROM memories "
                f"{base_filter} GROUP BY memory_type",
                params,
            ).fetchall()

            avg_imp = (
                conn.execute(
                    f"SELECT AVG(importance) AS avg FROM memories {base_filter}", params
                ).fetchone()["avg"]
                or 0
            )

            emb_count = conn.execute(
                f"SELECT COUNT(*) AS count FROM memories {base_filter} "
                "AND embedding IS NOT NULL",
                params,
            ).fetchone()["count"]

            db_size = self.db_path.stat().st_size / (1024 * 1024) if self.db_path.exists() else 0

        return {
            "total_memories": total,
            "by_type": {r["memory_type"]: r["count"] for r in by_type},
            "average_importance": round(avg_imp, 2),
            "db_size_mb": round(db_size, 2),
            "namespace": namespace,
            "embeddings_count": emb_count,
            "embeddings_coverage": round(emb_count / max(total, 1) * 100, 1),
        }

    def get_priority_memories(
        self,
        *,
        namespace: str | None = None,
        limit: int = 20,
        min_importance: int = 7,
    ) -> list[MemoryEntry]:
        clauses = [_NOT_EXPIRED, "importance >= ?"]
        params: list[Any] = [min_importance]
        if namespace:
            clauses.append("(namespace = ? OR namespace = 'default')")
            params.append(namespace)
        where = "WHERE " + " AND ".join(clauses)
        params.append(limit)

        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT * FROM memories {where}
                ORDER BY importance DESC, access_count DESC, accessed_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [_row_to_entry(r) for r in rows]

    # ------------------------------------------------------------------
    # Backfill & Cleanup
    # ------------------------------------------------------------------

    def list_memories_without_embeddings(
        self,
        *,
        namespace: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """Return memories that have no embedding stored."""
        clauses = [_NOT_EXPIRED, "embedding IS NULL"]
        params: list[Any] = []
        if namespace:
            clauses.append("namespace = ?")
            params.append(namespace)
        where = "WHERE " + " AND ".join(clauses)
        params.extend([limit, offset])

        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM memories {where} ORDER BY id LIMIT ? OFFSET ?",
                params,
            ).fetchall()
            return [_row_to_entry(r) for r in rows]

    def update_embedding(self, memory_id: int, embedding: list[float]) -> None:
        """Update just the embedding column for a single memory."""
        blob = _encode_embedding(embedding)
        with self._conn() as conn:
            conn.execute(
                "UPDATE memories SET embedding = ? WHERE id = ?",
                (blob, memory_id),
            )
            conn.commit()

    def delete_expired(self, *, namespace: str | None = None) -> int:
        """Physically remove all expired memories."""
        clauses = ["expires_at IS NOT NULL", "expires_at <= datetime('now')"]
        params: list[Any] = []
        if namespace:
            clauses.append("namespace = ?")
            params.append(namespace)
        where = "WHERE " + " AND ".join(clauses)

        with self._conn() as conn:
            cur = conn.execute(f"DELETE FROM memories {where}", params)
            conn.commit()
            return cur.rowcount


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
    tags = json.loads(row["tags"]) if row["tags"] else []
    metadata = json.loads(row["metadata"]) if row["metadata"] else {}
    embedding = _decode_embedding(row["embedding"])

    expires_at = None
    try:
        raw = row["expires_at"]
        if raw:
            expires_at = _parse_dt(raw)
    except (IndexError, KeyError):
        pass  # Column may not exist in old DBs

    return MemoryEntry(
        id=row["id"],
        content=row["content"],
        memory_type=MemoryType(row["memory_type"]),
        importance=row["importance"],
        namespace=row["namespace"] or "default",
        tags=tags,
        metadata=metadata,
        content_hash=row["content_hash"],
        embedding=embedding,
        decay_score=row["decay_score"],
        created_at=_parse_dt(row["created_at"]),
        accessed_at=_parse_dt(row["accessed_at"]),
        access_count=row["access_count"],
        expires_at=expires_at,
    )


def _parse_dt(val: str | None) -> datetime:
    if val is None:
        return datetime.now(timezone.utc)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def _encode_embedding(emb: list[float] | None) -> bytes | None:
    if emb is None:
        return None
    import struct

    return struct.pack(f"{len(emb)}f", *emb)


def _decode_embedding(blob: bytes | None) -> list[float] | None:
    if blob is None:
        return None
    import struct

    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    try:
        import numpy as np

        a_arr = np.asarray(a, dtype=np.float32)
        b_arr = np.asarray(b, dtype=np.float32)
        dot = np.dot(a_arr, b_arr)
        norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
        return float(dot / norm) if norm > 0 else 0.0
    except ImportError:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
