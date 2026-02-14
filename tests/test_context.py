"""Tests for the Smart Context Builder."""

import tempfile
from pathlib import Path

import pytest

from engram.client import Memory
from engram.config import EngramConfig
from engram.context import ContextResult, estimate_tokens


@pytest.fixture
def mem():
    with tempfile.TemporaryDirectory() as d:
        cfg = EngramConfig(db_path=Path(d) / "test.db", enable_embeddings=False)
        m = Memory(config=cfg)
        # Seed diverse memories
        m.store("I love pizza for dinner", type="preference", importance=8)
        m.store("My favorite programming language is Python", type="preference", importance=7)
        m.store("I work as an HVAC technician in Vienna", type="fact", importance=9)
        m.store("Always use parameterized queries for SQL", type="pattern", importance=9)
        m.store("Fixed login bug by adding null check", type="error_fix", importance=6)
        m.store("Use dark mode and compact layout", type="preference", importance=5)
        m.store("Project deadline is March 15 2026", type="fact", importance=8)
        m.store("React 19 breaks useEffect cleanup", type="error_fix", importance=6)
        m.store("Team uses PostgreSQL for production", type="decision", importance=7)
        m.store("API rate limit is 100 requests per second", type="decision", importance=4)
        yield m


class TestEstimateTokens:
    def test_short_text(self):
        assert estimate_tokens("hello") >= 1

    def test_longer_text(self):
        tokens = estimate_tokens("This is a longer piece of text with many words")
        assert 5 < tokens < 20

    def test_empty(self):
        assert estimate_tokens("") == 1  # min 1


class TestContextBuilder:
    def test_basic_context(self, mem):
        result = mem.context("pizza food dinner")
        assert isinstance(result, ContextResult)
        assert result.memories_used > 0
        assert result.token_count > 0
        assert "pizza" in result.context
        assert len(result.memory_ids) == result.memories_used

    def test_token_budget_respected(self, mem):
        result = mem.context("programming", max_tokens=100)
        assert result.token_count <= 120  # small tolerance for header

    def test_truncation(self, mem):
        # Very small budget should truncate
        small = mem.context("everything", max_tokens=150)
        large = mem.context("everything", max_tokens=5000)
        assert small.memories_used <= large.memories_used

    def test_empty_prompt_uses_priority(self, mem):
        result = mem.context("")
        # Empty prompt = no search, only priority recall
        assert result.memories_used > 0
        # Should include high-importance memories
        assert "HVAC" in result.context or "parameterized" in result.context

    def test_min_importance_filter(self, mem):
        high = mem.context("", min_importance=8)
        low = mem.context("", min_importance=3)
        assert low.memories_used >= high.memories_used

    def test_no_results(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = EngramConfig(db_path=Path(d) / "empty.db", enable_embeddings=False)
            m = Memory(config=cfg)
            result = m.context("anything")
            assert result.memories_used == 0
            assert result.context == ""
            assert not result.truncated

    def test_header_format(self, mem):
        result = mem.context("pizza")
        if result.memories_used > 0:
            assert result.context.startswith("## Relevant Context")

    def test_memory_ids_valid(self, mem):
        result = mem.context("programming language")
        for mid in result.memory_ids:
            assert isinstance(mid, int)
            assert mid > 0
