"""JWT token creation and validation."""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import jwt

_SECRET = os.environ.get("ENGRAM_JWT_SECRET", "engram-dev-secret-change-in-production")
_ALGORITHM = "HS256"
_ACCESS_TTL = 900  # 15 minutes
_REFRESH_TTL = 604_800  # 7 days


def create_access_token(user_id: str, tier: str) -> tuple[str, int]:
    """Create a JWT access token. Returns (token, expires_in)."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "tier": tier,
        "type": "access",
        "iat": now,
        "exp": now + _ACCESS_TTL,
    }
    token = jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)
    return token, _ACCESS_TTL


def create_refresh_token(user_id: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + _REFRESH_TTL,
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def decode_token(token: str) -> Optional[dict[str, Any]]:
    """Decode and validate a JWT. Returns payload or None."""
    try:
        return jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
