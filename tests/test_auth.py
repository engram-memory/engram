"""Tests for the authentication system."""

import os
from pathlib import Path

import pytest


class TestPasswords:
    def test_hash_and_verify(self):
        from server.auth.passwords import hash_password, verify_password

        pw = "MySecretPassword123"
        h = hash_password(pw)
        assert ":" in h
        assert verify_password(pw, h)
        assert not verify_password("wrong", h)

    def test_different_hashes(self):
        from server.auth.passwords import hash_password

        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # different salts


class TestJWT:
    def test_create_and_decode(self):
        from server.auth.jwt_handler import create_access_token, decode_token

        token, ttl = create_access_token("user-123", "pro")
        assert ttl > 0

        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["tier"] == "pro"
        assert payload["type"] == "access"

    def test_invalid_token(self):
        from server.auth.jwt_handler import decode_token

        assert decode_token("garbage.token.here") is None

    def test_refresh_token(self):
        from server.auth.jwt_handler import create_refresh_token, decode_token

        token = create_refresh_token("user-456")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-456"
        assert payload["type"] == "refresh"


class TestAPIKeys:
    def test_generate_key(self):
        from server.auth.api_keys import generate_api_key, hash_key

        key_id, full_key, key_hash = generate_api_key()
        assert full_key.startswith("engram_sk_")
        assert key_hash == hash_key(full_key)
        assert len(key_id) == 36  # UUID format


class TestAdminDB:
    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path: Path):
        from server.auth import database as db

        db.set_admin_db_path(tmp_path / "admin.db")
        db.init_admin_db()

    def test_create_and_get_user(self):
        from server.auth import database as db

        user = db.create_user("u1", "test@test.com", "hash123")
        assert user["email"] == "test@test.com"
        assert user["tier"] == "free"

        found = db.get_user_by_email("test@test.com")
        assert found is not None
        assert found["id"] == "u1"

    def test_duplicate_email(self):
        import sqlite3

        from server.auth import database as db

        db.create_user("u1", "dup@test.com", "hash")
        with pytest.raises(sqlite3.IntegrityError):
            db.create_user("u2", "dup@test.com", "hash2")

    def test_api_key_crud(self):
        from server.auth import database as db

        db.create_user("u1", "keys@test.com", "hash")
        db.store_api_key("k1", "u1", "keyhash", "engram_sk_abc", "my-key")

        keys = db.get_api_keys_for_user("u1")
        assert len(keys) == 1
        assert keys[0]["name"] == "my-key"

        found = db.get_api_key_by_hash("keyhash")
        assert found is not None
        assert found["user_id"] == "u1"

        assert db.delete_api_key("k1", "u1")
        assert len(db.get_api_keys_for_user("u1")) == 0

    def test_count_keys(self):
        from server.auth import database as db

        db.create_user("u1", "count@test.com", "hash")
        assert db.count_api_keys_for_user("u1") == 0
        db.store_api_key("k1", "u1", "h1", "p1", "key1")
        db.store_api_key("k2", "u1", "h2", "p2", "key2")
        assert db.count_api_keys_for_user("u1") == 2


class TestTiers:
    def test_get_tier(self):
        from server.tiers import get_tier

        free = get_tier("free")
        assert free.max_memories == 5_000
        assert not free.semantic_search

        pro = get_tier("pro")
        assert pro.max_memories == 250_000
        assert pro.semantic_search

        ent = get_tier("enterprise")
        assert ent.max_memories == 0  # unlimited
        assert ent.sso

    def test_unknown_tier_defaults_to_free(self):
        from server.tiers import get_tier

        assert get_tier("nonexistent").name == "free"


class TestCloudAuth:
    """Test auth routes in cloud mode."""

    @pytest.fixture(autouse=True)
    def _cloud_mode(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("ENGRAM_CLOUD_MODE", "true")
        monkeypatch.setenv("ENGRAM_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("HOME", str(tmp_path))

        from server.auth import database as db

        db.set_admin_db_path(tmp_path / "admin.db")
        db.init_admin_db()

        import server.auth.dependencies as deps
        deps.CLOUD_MODE = True

        import server.api as api_mod
        api_mod._memories.clear()
        api_mod._DATA_DIR = tmp_path / "data"

    @pytest.fixture()
    def client(self):
        from server.api import app
        from fastapi.testclient import TestClient

        return TestClient(app)

    def test_register(self, client):
        r = client.post("/v1/auth/register", json={
            "email": "new@test.com",
            "password": "securepass123",
        })
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_register_duplicate(self, client):
        client.post("/v1/auth/register", json={
            "email": "dup@test.com", "password": "securepass123",
        })
        r = client.post("/v1/auth/register", json={
            "email": "dup@test.com", "password": "otherpass123",
        })
        assert r.status_code == 409

    def test_login(self, client):
        client.post("/v1/auth/register", json={
            "email": "login@test.com", "password": "securepass123",
        })
        r = client.post("/v1/auth/login", json={
            "email": "login@test.com", "password": "securepass123",
        })
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_login_wrong_password(self, client):
        client.post("/v1/auth/register", json={
            "email": "wrong@test.com", "password": "securepass123",
        })
        r = client.post("/v1/auth/login", json={
            "email": "wrong@test.com", "password": "wrongpass",
        })
        assert r.status_code == 401

    def test_authenticated_memory_operations(self, client):
        # Register and get token
        r = client.post("/v1/auth/register", json={
            "email": "mem@test.com", "password": "securepass123",
        })
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Store
        r = client.post("/v1/memories", json={"content": "cloud memory"}, headers=headers)
        assert r.status_code == 200
        mid = r.json()["id"]

        # Get
        r = client.get(f"/v1/memories/{mid}", headers=headers)
        assert r.status_code == 200
        assert r.json()["content"] == "cloud memory"

        # Search
        r = client.post("/v1/search", json={"query": "cloud"}, headers=headers)
        assert r.status_code == 200

    def test_unauthenticated_rejected(self, client):
        r = client.post("/v1/memories", json={"content": "no auth"})
        assert r.status_code == 401

    def test_api_key_auth(self, client):
        # Register
        r = client.post("/v1/auth/register", json={
            "email": "apikey@test.com", "password": "securepass123",
        })
        token = r.json()["access_token"]

        # Create API key
        r = client.post("/v1/auth/keys", json={"name": "test-key"},
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        api_key = r.json()["key"]
        assert api_key.startswith("engram_sk_")

        # Use API key for memory operations
        r = client.post("/v1/memories", json={"content": "via api key"},
                        headers={"X-API-Key": api_key})
        assert r.status_code == 200

    def test_refresh_token(self, client):
        r = client.post("/v1/auth/register", json={
            "email": "refresh@test.com", "password": "securepass123",
        })
        refresh = r.json()["refresh_token"]

        r = client.post("/v1/auth/refresh", json={"refresh_token": refresh})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_tenant_isolation(self, client):
        # Register two users
        r1 = client.post("/v1/auth/register", json={
            "email": "user1@test.com", "password": "securepass123",
        })
        r2 = client.post("/v1/auth/register", json={
            "email": "user2@test.com", "password": "securepass123",
        })
        token1 = r1.json()["access_token"]
        token2 = r2.json()["access_token"]

        # User1 stores a memory
        client.post("/v1/memories", json={"content": "user1 secret"},
                    headers={"Authorization": f"Bearer {token1}"})

        # User2 should NOT see it
        r = client.get("/v1/memories",
                       headers={"Authorization": f"Bearer {token2}"})
        assert len(r.json()) == 0
