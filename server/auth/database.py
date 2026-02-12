"""Admin database for users and API keys."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

_DB_PATH = Path.home() / ".engram" / "admin.db"


def set_admin_db_path(path: Path | str) -> None:
    global _DB_PATH
    _DB_PATH = Path(path)


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_admin_db() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                tier TEXT NOT NULL DEFAULT 'free',
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login_at TIMESTAMP
            )
        """)
        # Add Stripe columns if upgrading from older schema
        try:
            c.execute("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        try:
            c.execute("ALTER TABLE users ADD COLUMN stripe_subscription_id TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        c.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                key_hash TEXT NOT NULL,
                key_prefix TEXT NOT NULL,
                name TEXT DEFAULT 'default',
                scopes TEXT DEFAULT '["memories:read","memories:write"]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP,
                expires_at TIMESTAMP
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix)")
        c.commit()


# ------------------------------------------------------------------
# Users
# ------------------------------------------------------------------


def create_user(user_id: str, email: str, password_hash: str, tier: str = "free") -> dict:
    with _conn() as c:
        c.execute(
            "INSERT INTO users (id, email, password_hash, tier) VALUES (?, ?, ?, ?)",
            (user_id, email, password_hash, tier),
        )
        c.commit()
    return get_user_by_id(user_id)


def get_user_by_email(email: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def update_last_login(user_id: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?",
            (user_id,),
        )
        c.commit()


def update_user_tier(user_id: str, tier: str) -> None:
    with _conn() as c:
        c.execute("UPDATE users SET tier = ? WHERE id = ?", (tier, user_id))
        c.commit()


def update_stripe_customer_id(user_id: str, customer_id: str) -> None:
    with _conn() as c:
        c.execute("UPDATE users SET stripe_customer_id = ? WHERE id = ?", (customer_id, user_id))
        c.commit()


def update_stripe_subscription_id(user_id: str, subscription_id: str | None) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE users SET stripe_subscription_id = ? WHERE id = ?", (subscription_id, user_id)
        )
        c.commit()


def get_user_by_stripe_customer_id(customer_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM users WHERE stripe_customer_id = ?", (customer_id,)
        ).fetchone()
        return dict(row) if row else None


# ------------------------------------------------------------------
# API Keys
# ------------------------------------------------------------------


def store_api_key(
    key_id: str,
    user_id: str,
    key_hash: str,
    key_prefix: str,
    name: str = "default",
    scopes: list[str] | None = None,
) -> None:
    scopes_str = json.dumps(scopes or ["memories:read", "memories:write"])
    with _conn() as c:
        c.execute(
            "INSERT INTO api_keys (id, user_id, key_hash, key_prefix, name, scopes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (key_id, user_id, key_hash, key_prefix, name, scopes_str),
        )
        c.commit()


def get_api_key_by_hash(key_hash: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["scopes"] = json.loads(result["scopes"])
        return result


def get_api_keys_for_user(user_id: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM api_keys WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["scopes"] = json.loads(d["scopes"])
            results.append(d)
        return results


def count_api_keys_for_user(user_id: str) -> int:
    with _conn() as c:
        row = c.execute(
            "SELECT COUNT(*) AS cnt FROM api_keys WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["cnt"]


def touch_api_key(key_id: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?",
            (key_id,),
        )
        c.commit()


def delete_api_key(key_id: str, user_id: str) -> bool:
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM api_keys WHERE id = ? AND user_id = ?",
            (key_id, user_id),
        )
        c.commit()
        return cur.rowcount > 0
