"""Tests for MCP server tool dispatch logic (no actual MCP transport)."""

import tempfile
from pathlib import Path

import pytest

from engram.config import EngramConfig


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    import mcp_server.server as srv

    srv._config = EngramConfig(db_path=tmp_path / "mcp_test.db")
    srv._memories.clear()


class TestMCPDispatch:
    def test_store(self):
        from mcp_server.server import _dispatch

        result = _dispatch("memory_store", {"content": "MCP test", "importance": 8})
        assert result["status"] == "stored"
        assert result["id"] is not None

    def test_search(self):
        from mcp_server.server import _dispatch

        _dispatch("memory_store", {"content": "Python MCP integration"})
        result = _dispatch("memory_search", {"query": "Python"})
        assert result["count"] >= 1

    def test_recall(self):
        from mcp_server.server import _dispatch

        _dispatch("memory_store", {"content": "important fact", "importance": 9})
        result = _dispatch("memory_recall", {"min_importance": 7})
        assert result["count"] >= 1

    def test_delete(self):
        from mcp_server.server import _dispatch

        r = _dispatch("memory_store", {"content": "delete me"})
        mid = r["id"]
        result = _dispatch("memory_delete", {"memory_id": mid})
        assert result["deleted"] is True

    def test_stats(self):
        from mcp_server.server import _dispatch

        _dispatch("memory_store", {"content": "stat item"})
        result = _dispatch("memory_stats", {})
        assert result["total_memories"] >= 1

    def test_unknown_tool(self):
        from mcp_server.server import _dispatch

        result = _dispatch("nonexistent_tool", {})
        assert "error" in result
