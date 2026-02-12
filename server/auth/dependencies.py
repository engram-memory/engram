"""FastAPI authentication dependencies."""

from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import HTTPException, Request

from server.auth.api_keys import validate_api_key
from server.auth.jwt_handler import decode_token
from server.tiers import TierLimits, get_tier

CLOUD_MODE = os.environ.get("ENGRAM_CLOUD_MODE", "").lower() in ("1", "true", "yes")

# Legacy single API key for local mode
_LEGACY_API_KEY: str | None = os.environ.get("ENGRAM_API_KEY")


@dataclass
class AuthUser:
    """Authenticated user context."""

    id: str
    email: str
    tier: str
    scopes: list[str]

    @property
    def limits(self) -> TierLimits:
        return get_tier(self.tier)


def require_auth(request: Request) -> AuthUser:
    """FastAPI dependency: require authentication. Returns AuthUser.

    In cloud mode: checks JWT Bearer token or API key.
    In local mode: checks legacy API key (or allows all if none set).
    """
    if not CLOUD_MODE:
        return _legacy_auth(request)

    # Try Bearer token first
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = decode_token(token)
        if payload and payload.get("type") == "access":
            from server.auth.database import get_user_by_id

            user = get_user_by_id(payload["sub"])
            if user:
                return AuthUser(
                    id=user["id"],
                    email=user["email"],
                    tier=user["tier"],
                    scopes=["memories:read", "memories:write", "memories:admin"],
                )
        raise HTTPException(401, "Invalid or expired token")

    # Try API key
    api_key = request.headers.get("X-API-Key", "")
    if api_key:
        record = validate_api_key(api_key)
        if record:
            user = record["user"]
            return AuthUser(
                id=user["id"],
                email=user["email"],
                tier=user["tier"],
                scopes=record["scopes"],
            )
        raise HTTPException(401, "Invalid API key")

    raise HTTPException(401, "Authentication required. Provide Bearer token or X-API-Key header.")


def get_current_user(request: Request) -> AuthUser:
    """Alias for require_auth."""
    return require_auth(request)


def get_namespace(request: Request) -> str:
    """Read X-Namespace header, defaulting to 'default'."""
    return request.headers.get("X-Namespace", "default")


def _legacy_auth(request: Request) -> AuthUser:
    """Legacy local-mode auth: single API key or open access."""
    if _LEGACY_API_KEY is not None:
        provided = request.headers.get("X-API-Key", "")
        if provided != _LEGACY_API_KEY:
            raise HTTPException(401, "Invalid or missing API key")

    return AuthUser(
        id="local",
        email="local@localhost",
        tier="enterprise",  # local mode = full access
        scopes=["memories:read", "memories:write", "memories:admin"],
    )
