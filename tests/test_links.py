"""Tests for Memory Links (Phase 3B)."""

from pathlib import Path

import pytest

from engram.client import Memory
from engram.config import EngramConfig
from engram.core.types import MemoryEntry
from engram.storage.sqlite_backend import SQLiteBackend

# ------------------------------------------------------------------
# Backend-level tests
# ------------------------------------------------------------------


@pytest.fixture()
def backend(tmp_path: Path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "links_test.db")


def _entry(content: str = "test", **kw) -> MemoryEntry:
    return MemoryEntry(content=content, **kw)


class TestLinkBackend:
    def test_link_creates_and_returns_id(self, backend: SQLiteBackend):
        a = backend.store(_entry("memory A"))
        b = backend.store(_entry("memory B"))
        link_id = backend.link(a, b, "caused_by")
        assert link_id is not None
        assert isinstance(link_id, int)

    def test_duplicate_link_returns_none(self, backend: SQLiteBackend):
        a = backend.store(_entry("dup A"))
        b = backend.store(_entry("dup B"))
        first = backend.link(a, b, "related")
        assert first is not None
        second = backend.link(a, b, "related")
        assert second is None

    def test_same_pair_different_relation_ok(self, backend: SQLiteBackend):
        a = backend.store(_entry("rel A"))
        b = backend.store(_entry("rel B"))
        l1 = backend.link(a, b, "caused_by")
        l2 = backend.link(a, b, "depends_on")
        assert l1 is not None
        assert l2 is not None
        assert l1 != l2

    def test_unlink(self, backend: SQLiteBackend):
        a = backend.store(_entry("unlink A"))
        b = backend.store(_entry("unlink B"))
        link_id = backend.link(a, b)
        assert backend.unlink(link_id) is True
        assert backend.unlink(link_id) is False  # already deleted

    def test_get_links_outgoing(self, backend: SQLiteBackend):
        a = backend.store(_entry("out A"))
        b = backend.store(_entry("out B"))
        c = backend.store(_entry("out C"))
        backend.link(a, b, "related")
        backend.link(a, c, "caused_by")
        links = backend.get_links(a, direction="outgoing")
        assert len(links) == 2
        assert all(lnk["direction"] == "outgoing" for lnk in links)

    def test_get_links_incoming(self, backend: SQLiteBackend):
        a = backend.store(_entry("in A"))
        b = backend.store(_entry("in B"))
        backend.link(a, b, "depends_on")
        links = backend.get_links(b, direction="incoming")
        assert len(links) == 1
        assert links[0]["direction"] == "incoming"
        assert links[0]["source_id"] == a

    def test_get_links_both(self, backend: SQLiteBackend):
        a = backend.store(_entry("both A"))
        b = backend.store(_entry("both B"))
        c = backend.store(_entry("both C"))
        backend.link(a, b, "related")
        backend.link(c, b, "caused_by")
        links = backend.get_links(b, direction="both")
        assert len(links) == 2

    def test_get_links_filter_by_relation(self, backend: SQLiteBackend):
        a = backend.store(_entry("filter A"))
        b = backend.store(_entry("filter B"))
        c = backend.store(_entry("filter C"))
        backend.link(a, b, "caused_by")
        backend.link(a, c, "depends_on")
        links = backend.get_links(a, direction="outgoing", relation="caused_by")
        assert len(links) == 1
        assert links[0]["relation"] == "caused_by"

    def test_cascade_delete_removes_links(self, backend: SQLiteBackend):
        a = backend.store(_entry("cascade A"))
        b = backend.store(_entry("cascade B"))
        backend.link(a, b, "related")
        # Delete memory A — link should be gone too
        backend.delete(a)
        links = backend.get_links(b, direction="both")
        assert len(links) == 0

    def test_graph_traversal_simple(self, backend: SQLiteBackend):
        a = backend.store(_entry("graph A"))
        b = backend.store(_entry("graph B"))
        c = backend.store(_entry("graph C"))
        backend.link(a, b, "caused_by")
        backend.link(b, c, "depends_on")

        graph = backend.get_graph(a, max_depth=2)
        assert graph["root"] == a
        assert len(graph["nodes"]) == 3
        assert len(graph["edges"]) == 2

    def test_graph_max_depth_limits(self, backend: SQLiteBackend):
        a = backend.store(_entry("depth A"))
        b = backend.store(_entry("depth B"))
        c = backend.store(_entry("depth C"))
        backend.link(a, b, "related")
        backend.link(b, c, "related")

        graph = backend.get_graph(a, max_depth=1)
        # Should only reach A and B, not C
        assert len(graph["nodes"]) == 2
        node_ids = {n["id"] for n in graph["nodes"]}
        assert a in node_ids
        assert b in node_ids
        assert c not in node_ids

    def test_graph_no_circular_loop(self, backend: SQLiteBackend):
        a = backend.store(_entry("circle A"))
        b = backend.store(_entry("circle B"))
        c = backend.store(_entry("circle C"))
        backend.link(a, b, "related")
        backend.link(b, c, "related")
        backend.link(c, a, "related")  # circular!

        graph = backend.get_graph(a, max_depth=5)
        # Should visit each node exactly once
        assert len(graph["nodes"]) == 3

    def test_graph_filter_by_relation(self, backend: SQLiteBackend):
        a = backend.store(_entry("grel A"))
        b = backend.store(_entry("grel B"))
        c = backend.store(_entry("grel C"))
        backend.link(a, b, "caused_by")
        backend.link(a, c, "depends_on")

        graph = backend.get_graph(a, max_depth=2, relation="caused_by")
        node_ids = {n["id"] for n in graph["nodes"]}
        assert a in node_ids
        assert b in node_ids
        assert c not in node_ids  # filtered out

    def test_link_invalid_memory_returns_none(self, backend: SQLiteBackend):
        a = backend.store(_entry("valid"))
        result = backend.link(a, 99999, "related")
        assert result is None


# ------------------------------------------------------------------
# Client-level tests
# ------------------------------------------------------------------


@pytest.fixture()
def mem(tmp_path: Path) -> Memory:
    config = EngramConfig(db_path=tmp_path / "client_links.db")
    return Memory(config=config)


class TestLinkClient:
    def test_link_and_links(self, mem: Memory):
        a = mem.store("client A")
        b = mem.store("client B")
        link_id = mem.link(a, b, "caused_by")
        assert link_id is not None

        links = mem.links(a)
        assert len(links) >= 1
        assert links[0]["relation"] == "caused_by"

    def test_unlink(self, mem: Memory):
        a = mem.store("unlink client A")
        b = mem.store("unlink client B")
        link_id = mem.link(a, b)
        assert mem.unlink(link_id) is True
        assert mem.unlink(link_id) is False

    def test_graph(self, mem: Memory):
        a = mem.store("graph client A")
        b = mem.store("graph client B")
        c = mem.store("graph client C")
        mem.link(a, b, "related")
        mem.link(b, c, "depends_on")

        graph = mem.graph(a, max_depth=3)
        assert graph["root"] == a
        assert len(graph["nodes"]) == 3
        assert len(graph["edges"]) == 2
