"""Simple API-key authentication for the REST server."""

from __future__ import annotations

import os

from fastapi import HTTPException, Request

_API_KEY: str | None = os.environ.get("ENGRAM_API_KEY")


def verify_api_key(request: Request) -> None:
    """FastAPI dependency — checks ``X-API-Key`` header when a key is configured."""
    if _API_KEY is None:
        return  # no auth required in local mode

    provided = request.headers.get("X-API-Key")
    if provided != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def get_namespace(request: Request) -> str:
    """Read ``X-Namespace`` header, defaulting to ``"default"``."""
    return request.headers.get("X-Namespace", "default")
