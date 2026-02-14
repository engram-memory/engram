"""Tests for the Analytics Dashboard backend."""

import tempfile
from pathlib import Path

import pytest

from engram.client import Memory
from engram.config import EngramConfig


@pytest.fixture
def mem():
    with tempfile.TemporaryDirectory() as d:
        cfg = EngramConfig(db_path=Path(d) / "test.db", enable_embeddings=False)
        m = Memory(config=cfg)
        m.store(
            "I love pizza for dinner", type="preference", importance=8, tags=["food", "italian"]
        )
        m.store(
            "Python is my favorite language",
            type="preference",
            importance=7,
            tags=["python", "coding"],
        )
        m.store("I work as an HVAC technician", type="fact", importance=9, tags=["work", "hvac"])
        m.store(
            "Always use parameterized queries",
            type="pattern",
            importance=9,
            tags=["sql", "security"],
        )
        m.store(
            "Fixed login bug with null check",
            type="error_fix",
            importance=6,
            tags=["python", "bugs"],
        )
        m.store("Use dark mode and compact layout", type="preference", importance=5, tags=["ui"])
        m.store(
            "Project deadline is March 15", type="fact", importance=8, tags=["work", "deadlines"]
        )
        m.store("React 19 breaks useEffect", type="error_fix", importance=6, tags=["react", "bugs"])
        m.store("Team uses PostgreSQL", type="decision", importance=7, tags=["database"])
        m.store("API rate limit is 100 rps", type="decision", importance=4, tags=["api"])
        yield m


class TestAnalytics:
    def test_returns_all_fields(self, mem):
        data = mem.analytics()
        assert "growth" in data
        assert "tags" in data
        assert "namespaces" in data
        assert "distribution" in data
        assert "types" in data
        assert "total_memories" in data
        assert "period_days" in data

    def test_total_memories(self, mem):
        data = mem.analytics()
        assert data["total_memories"] == 10

    def test_growth_has_entries(self, mem):
        data = mem.analytics()
        assert len(data["growth"]) >= 1
        for entry in data["growth"]:
            assert "date" in entry
            assert "count" in entry

    def test_tags_sorted_by_count(self, mem):
        data = mem.analytics()
        assert len(data["tags"]) > 0
        # "python" and "work" each appear twice
        top_tags = [t["tag"] for t in data["tags"][:5]]
        assert "python" in top_tags or "work" in top_tags or "bugs" in top_tags
        # Verify sorted descending
        counts = [t["count"] for t in data["tags"]]
        assert counts == sorted(counts, reverse=True)

    def test_distribution_sums_to_total(self, mem):
        data = mem.analytics()
        total_from_dist = sum(data["distribution"].values())
        assert total_from_dist == data["total_memories"]

    def test_types_present(self, mem):
        data = mem.analytics()
        assert "preference" in data["types"]
        assert "fact" in data["types"]
        assert "error_fix" in data["types"]
        assert data["types"]["preference"] == 3
        assert data["types"]["fact"] == 2

    def test_namespaces(self, mem):
        data = mem.analytics()
        assert len(data["namespaces"]) >= 1
        ns = data["namespaces"][0]
        assert "namespace" in ns
        assert "count" in ns
        assert "avg_importance" in ns

    def test_period_days(self, mem):
        data = mem.analytics(days=30)
        assert data["period_days"] == 30

    def test_empty_db(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = EngramConfig(db_path=Path(d) / "empty.db", enable_embeddings=False)
            m = Memory(config=cfg)
            data = m.analytics()
            assert data["total_memories"] == 0
            assert data["growth"] == []
            assert data["tags"] == []
            assert data["distribution"] == {}
            assert data["types"] == {}
