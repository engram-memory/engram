"""Synapse proxy routes — Pro-gated access to the Synapse message bus."""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from server.auth.dependencies import AuthUser, require_auth

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/synapse", tags=["synapse"])

SYNAPSE_URL = os.environ.get("SYNAPSE_INTERNAL_URL", "http://localhost:8200")


# ------------------------------------------------------------------
# Gate
# ------------------------------------------------------------------


def _check_synapse(user: AuthUser) -> None:
    """Block Synapse features for Free tier."""
    if not user.limits.synapse_bus:
        raise HTTPException(
            403,
            "Synapse Message Bus is a Pro feature. Upgrade at https://engram-ai.dev/#pricing",
        )


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------


class PublishRequest(BaseModel):
    channel: str
    payload: dict
    type: str = "event"
    priority: int = 2


class RegisterAgentRequest(BaseModel):
    name: str
    capabilities: list[str] = []
    channels: list[str] = []


# ------------------------------------------------------------------
# Proxy helpers
# ------------------------------------------------------------------


async def _proxy_get(path: str, params: dict | None = None) -> dict:
    """Forward GET request to internal Synapse server."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{SYNAPSE_URL}{path}", params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(503, "Synapse bus is not reachable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text)


async def _proxy_post(path: str, data: dict) -> dict:
    """Forward POST request to internal Synapse server."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{SYNAPSE_URL}{path}", json=data)
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(503, "Synapse bus is not reachable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text)


async def _proxy_delete(path: str) -> dict:
    """Forward DELETE request to internal Synapse server."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.delete(f"{SYNAPSE_URL}{path}")
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(503, "Synapse bus is not reachable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text)


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post("/publish")
async def publish(body: PublishRequest, user: AuthUser = Depends(require_auth)):
    """Publish a message to a Synapse channel."""
    _check_synapse(user)
    return await _proxy_post(
        "/publish",
        {
            "channel": body.channel,
            "sender": f"pro:{user.id[:8]}",
            "payload": body.payload,
            "type": body.type,
            "priority": body.priority,
        },
    )


@router.get("/inbox")
async def inbox(
    user: AuthUser = Depends(require_auth),
    limit: int = Query(20, ge=1, le=100),
    channel: str | None = Query(None),
):
    """Read messages from the user's Synapse inbox."""
    _check_synapse(user)
    agent_name = f"pro:{user.id[:8]}"
    params: dict = {"limit": limit}
    if channel:
        params["channel"] = channel
    return await _proxy_get(f"/inbox/{agent_name}", params)


@router.delete("/inbox")
async def clear_inbox(user: AuthUser = Depends(require_auth)):
    """Clear the user's Synapse inbox."""
    _check_synapse(user)
    agent_name = f"pro:{user.id[:8]}"
    return await _proxy_delete(f"/inbox/{agent_name}")


@router.get("/channels")
async def list_channels(user: AuthUser = Depends(require_auth)):
    """List all Synapse channels."""
    _check_synapse(user)
    return await _proxy_get("/channels")


@router.get("/history/{channel:path}")
async def history(
    channel: str,
    user: AuthUser = Depends(require_auth),
    limit: int = Query(50, ge=1, le=200),
):
    """Get message history for a channel."""
    _check_synapse(user)
    return await _proxy_get(f"/history/{channel}", {"limit": limit})


@router.get("/agents")
async def list_agents(user: AuthUser = Depends(require_auth)):
    """List all registered agents."""
    _check_synapse(user)
    return await _proxy_get("/agents")


@router.post("/agents/register")
async def register_agent(body: RegisterAgentRequest, user: AuthUser = Depends(require_auth)):
    """Register an agent on the Synapse bus."""
    _check_synapse(user)
    return await _proxy_post(
        "/agents/register",
        {
            "name": body.name,
            "capabilities": body.capabilities,
            "channels": body.channels,
        },
    )


@router.get("/health")
async def synapse_health(user: AuthUser = Depends(require_auth)):
    """Get Synapse bus health status."""
    _check_synapse(user)
    return await _proxy_get("/health")
