"""Tests for the Memory client (store / search / recall / delete)."""

import tempfile
from pathlib import Path

import pytest

from engram import Memory, MemoryEntry
from engram.config import EngramConfig
from engram.exceptions import MemoryNotFound


@pytest.fixture()
def mem(tmp_path: Path) -> Memory:
    cfg = EngramConfig(db_path=tmp_path / "test.db")
    return Memory(config=cfg)


# ------------------------------------------------------------------
# Store
# ------------------------------------------------------------------

class TestStore:
    def test_store_returns_id(self, mem: Memory):
        mid = mem.store("Python is great", type="fact", importance=7)
        assert isinstance(mid, int)
        assert mid >= 1

    def test_store_duplicate_returns_none(self, mem: Memory):
        mem.store("duplicate content")
        result = mem.store("duplicate content")
        assert result is None

    def test_store_with_tags_and_metadata(self, mem: Memory):
        mid = mem.store(
            "Use ruff for linting",
            type="pattern",
            importance=8,
            tags=["python", "tooling"],
            metadata={"source": "config"},
        )
        entry = mem.get(mid)
        assert entry.tags == ["python", "tooling"]
        assert entry.metadata == {"source": "config"}


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------

class TestSearch:
    def test_search_finds_stored_memory(self, mem: Memory):
        mem.store("User prefers dark mode", type="preference", importance=8)
        results = mem.search("dark mode")
        assert len(results) >= 1
        assert "dark mode" in results[0].memory.content

    def test_search_empty_returns_empty(self, mem: Memory):
        assert mem.search("") == []

    def test_search_no_match_returns_empty(self, mem: Memory):
        mem.store("hello world")
        results = mem.search("xyznonexistent")
        assert results == []

    def test_search_respects_limit(self, mem: Memory):
        for i in range(10):
            mem.store(f"memory number {i}", type="fact", importance=5)
        results = mem.search("memory", limit=3)
        assert len(results) <= 3


# ------------------------------------------------------------------
# Recall
# ------------------------------------------------------------------

class TestRecall:
    def test_recall_returns_high_importance(self, mem: Memory):
        mem.store("low importance item", type="fact", importance=2)
        mem.store("critical item", type="fact", importance=9)
        results = mem.recall(min_importance=7)
        assert len(results) == 1
        assert results[0].importance >= 7

    def test_recall_respects_limit(self, mem: Memory):
        for i in range(10):
            mem.store(f"important item {i}", type="fact", importance=9)
        results = mem.recall(limit=3, min_importance=7)
        assert len(results) <= 3


# ------------------------------------------------------------------
# Get / Delete / Update
# ------------------------------------------------------------------

class TestCRUD:
    def test_get_existing(self, mem: Memory):
        mid = mem.store("test entry")
        entry = mem.get(mid)
        assert entry.content == "test entry"
        assert entry.id == mid

    def test_get_nonexistent_raises(self, mem: Memory):
        with pytest.raises(MemoryNotFound):
            mem.get(99999)

    def test_delete(self, mem: Memory):
        mid = mem.store("to be deleted")
        assert mem.delete(mid) is True
        with pytest.raises(MemoryNotFound):
            mem.get(mid)

    def test_delete_nonexistent(self, mem: Memory):
        assert mem.delete(99999) is False

    def test_update(self, mem: Memory):
        mid = mem.store("original", importance=3)
        updated = mem.update(mid, importance=9)
        assert updated.importance == 9

    def test_update_nonexistent_raises(self, mem: Memory):
        with pytest.raises(MemoryNotFound):
            mem.update(99999, importance=1)


# ------------------------------------------------------------------
# List / Stats / Export / Import
# ------------------------------------------------------------------

class TestListStatsExportImport:
    def test_list(self, mem: Memory):
        mem.store("a")
        mem.store("b")
        entries = mem.list()
        assert len(entries) == 2

    def test_stats(self, mem: Memory):
        mem.store("s1", type="fact")
        mem.store("s2", type="preference")
        s = mem.stats()
        assert s["total_memories"] == 2
        assert "fact" in s["by_type"]

    def test_export_import_roundtrip(self, mem: Memory, tmp_path: Path):
        mem.store("export me", type="decision", importance=7, tags=["test"])
        exported = mem.export_memories(format="json")

        # Import into a fresh instance
        cfg2 = EngramConfig(db_path=tmp_path / "import.db")
        mem2 = Memory(config=cfg2)
        count = mem2.import_memories(exported)
        assert count == 1
        entries = mem2.list()
        assert entries[0].content == "export me"

    def test_prune(self, mem: Memory):
        mem.store("old low", importance=1)
        # Prune with 0 days should remove low-importance, low-access memories
        removed = mem.prune(days=0, min_importance=3)
        assert removed >= 1
