"""Tests for the SQLite backend directly."""

from pathlib import Path

import pytest

from engram.core.types import MemoryEntry, MemoryType
from engram.storage.sqlite_backend import SQLiteBackend


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "backend_test.db")


def _entry(content: str = "test", **kw) -> MemoryEntry:
    return MemoryEntry(content=content, **kw)


class TestSQLiteBackend:
    def test_store_and_get(self, backend: SQLiteBackend):
        mid = backend.store(_entry("hello world"))
        assert mid is not None
        entry = backend.get(mid)
        assert entry is not None
        assert entry.content == "hello world"

    def test_duplicate_returns_none(self, backend: SQLiteBackend):
        backend.store(_entry("dup"))
        assert backend.store(_entry("dup")) is None

    def test_delete(self, backend: SQLiteBackend):
        mid = backend.store(_entry("to delete"))
        assert backend.delete(mid) is True
        assert backend.get(mid) is None

    def test_update(self, backend: SQLiteBackend):
        mid = backend.store(_entry("original", importance=3))
        updated = backend.update(mid, importance=10)
        assert updated is not None
        assert updated.importance == 10

    def test_list_with_filters(self, backend: SQLiteBackend):
        backend.store(_entry("a", memory_type=MemoryType.fact, importance=3))
        backend.store(_entry("b", memory_type=MemoryType.preference, importance=9))
        backend.store(_entry("c", memory_type=MemoryType.fact, importance=8))

        facts = backend.list_memories(memory_type="fact")
        assert len(facts) == 2

        high = backend.list_memories(min_importance=8)
        assert len(high) == 2

    def test_search_text(self, backend: SQLiteBackend):
        backend.store(_entry("Python rocks for scripting"))
        backend.store(_entry("Java is verbose"))
        results = backend.search_text("Python")
        assert len(results) >= 1
        assert "Python" in results[0].memory.content

    def test_stats(self, backend: SQLiteBackend):
        backend.store(_entry("x", memory_type=MemoryType.fact))
        backend.store(_entry("y", memory_type=MemoryType.decision))
        s = backend.stats()
        assert s["total_memories"] == 2
        assert "fact" in s["by_type"]
        assert "decision" in s["by_type"]

    def test_priority_memories(self, backend: SQLiteBackend):
        backend.store(_entry("low", importance=2))
        backend.store(_entry("high", importance=9))
        prio = backend.get_priority_memories(min_importance=7)
        assert len(prio) == 1
        assert prio[0].importance == 9

    def test_namespace_isolation(self, backend: SQLiteBackend):
        backend.store(_entry("ns1 data", namespace="ns1"))
        backend.store(_entry("ns2 data", namespace="ns2"))
        ns1_mems = backend.list_memories(namespace="ns1")
        assert len(ns1_mems) == 1
        assert ns1_mems[0].namespace == "ns1"
