"""API key generation and validation."""

from __future__ import annotations

import hashlib
import secrets
import uuid

from server.auth import database as db

_PREFIX = "engram_sk_"


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key. Returns (key_id, full_key, key_hash)."""
    key_id = str(uuid.uuid4())
    random_part = secrets.token_urlsafe(32)
    full_key = f"{_PREFIX}{random_part}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return key_id, full_key, key_hash


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def validate_api_key(key: str) -> dict | None:
    """Validate an API key. Returns the key record with user info, or None."""
    from datetime import datetime, timezone

    if not key.startswith(_PREFIX):
        return None
    key_h = hash_key(key)
    record = db.get_api_key_by_hash(key_h)
    if record is None:
        return None

    # Check expiry if set
    expires_at = record.get("expires_at")
    if expires_at:
        try:
            exp_dt = datetime.fromisoformat(expires_at)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) >= exp_dt:
                return None  # Key expired
        except (ValueError, TypeError):
            pass

    db.touch_api_key(record["id"])
    user = db.get_user_by_id(record["user_id"])
    if user is None:
        return None
    record["user"] = user
    return record
