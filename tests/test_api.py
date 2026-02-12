"""Tests for the FastAPI REST server."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path: Path, monkeypatch):
    """Point Engram at a temp DB so tests don't touch real data."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ENGRAM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("ENGRAM_CLOUD_MODE", raising=False)
    monkeypatch.delenv("ENGRAM_API_KEY", raising=False)
    # Clear cached Memory instances
    import server.api as api_mod

    api_mod._memories.clear()
    api_mod._DATA_DIR = tmp_path / "data"


@pytest.fixture()
def client():
    from server.api import app

    return TestClient(app)


class TestHealth:
    def test_health(self, client: TestClient):
        r = client.get("/v1/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"


class TestCRUD:
    def test_store_and_get(self, client: TestClient):
        r = client.post("/v1/memories", json={"content": "test memory", "importance": 7})
        assert r.status_code == 200
        mid = r.json()["id"]
        assert mid is not None

        r2 = client.get(f"/v1/memories/{mid}")
        assert r2.status_code == 200
        assert r2.json()["content"] == "test memory"

    def test_list(self, client: TestClient):
        client.post("/v1/memories", json={"content": "a"})
        client.post("/v1/memories", json={"content": "b"})
        r = client.get("/v1/memories")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_update(self, client: TestClient):
        r = client.post("/v1/memories", json={"content": "original"})
        mid = r.json()["id"]
        r2 = client.put(f"/v1/memories/{mid}", json={"importance": 10})
        assert r2.status_code == 200
        assert r2.json()["importance"] == 10

    def test_delete(self, client: TestClient):
        r = client.post("/v1/memories", json={"content": "to delete"})
        mid = r.json()["id"]
        r2 = client.delete(f"/v1/memories/{mid}")
        assert r2.status_code == 200
        r3 = client.get(f"/v1/memories/{mid}")
        assert r3.status_code == 404

    def test_not_found(self, client: TestClient):
        assert client.get("/v1/memories/99999").status_code == 404
        assert client.delete("/v1/memories/99999").status_code == 404


class TestSearch:
    def test_search(self, client: TestClient):
        client.post("/v1/memories", json={"content": "Python is awesome"})
        r = client.post("/v1/search", json={"query": "Python"})
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert "Python" in data[0]["memory"]["content"]

    def test_recall(self, client: TestClient):
        client.post("/v1/memories", json={"content": "critical fact", "importance": 9})
        client.post("/v1/memories", json={"content": "trivial", "importance": 2})
        r = client.post("/v1/recall", json={"min_importance": 7})
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1


class TestStatsExportImport:
    def test_stats(self, client: TestClient):
        client.post("/v1/memories", json={"content": "stat1"})
        r = client.get("/v1/stats")
        assert r.status_code == 200
        assert r.json()["total_memories"] == 1

    def test_export_import(self, client: TestClient):
        client.post("/v1/memories", json={"content": "exportable", "importance": 8})
        r = client.post("/v1/export", json={"format": "json"})
        assert r.status_code == 200
        exported = r.json()["data"]

        r2 = client.post("/v1/import", json={"data": exported})
        assert r2.status_code == 200
