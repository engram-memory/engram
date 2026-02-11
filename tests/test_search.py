"""Tests for search engine and FTS5 edge cases."""

from pathlib import Path

import pytest

from engram import Memory
from engram.config import EngramConfig
from engram.core.search import sanitize_fts_query


@pytest.fixture()
def mem(tmp_path: Path) -> Memory:
    cfg = EngramConfig(db_path=tmp_path / "search_test.db")
    return Memory(config=cfg)


class TestSanitizeFtsQuery:
    def test_simple(self):
        assert sanitize_fts_query("hello world") == '"hello" OR "world"'

    def test_special_characters(self):
        result = sanitize_fts_query("hello-world foo@bar")
        assert '"hello"' in result
        assert '"world"' in result

    def test_empty_returns_none(self):
        assert sanitize_fts_query("") is None
        assert sanitize_fts_query("   ") is None

    def test_max_words(self):
        q = " ".join(f"word{i}" for i in range(20))
        result = sanitize_fts_query(q, max_words=5)
        assert result.count('"') == 10  # 5 words × 2 quotes each

    def test_only_special_chars(self):
        assert sanitize_fts_query("!@#$%") is None


class TestFTS5Search:
    def test_partial_word_match(self, mem: Memory):
        mem.store("JavaScript is a programming language")
        results = mem.search("JavaScript")
        assert len(results) >= 1

    def test_multi_word_search(self, mem: Memory):
        mem.store("Python is great for data science")
        mem.store("JavaScript is great for web development")
        results = mem.search("Python data")
        assert len(results) >= 1
        assert "Python" in results[0].memory.content

    def test_case_insensitive(self, mem: Memory):
        mem.store("Docker containers are useful")
        results = mem.search("docker")
        assert len(results) >= 1

    def test_search_by_tags(self, mem: Memory):
        mem.store("Tag search test", tags=["python", "testing"])
        results = mem.search("python")
        assert len(results) >= 1

    def test_search_respects_namespace(self, mem: Memory):
        mem.store("agent1 memory", namespace="agent1")
        mem.store("agent2 memory", namespace="agent2")
        r1 = mem.search("memory", namespace="agent1")
        assert all(r.memory.namespace == "agent1" for r in r1)
