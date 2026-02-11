"""Authentication API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from server.auth import database as db
from server.auth.api_keys import generate_api_key
from server.auth.dependencies import AuthUser, require_auth
from server.auth.jwt_handler import create_access_token, create_refresh_token, decode_token
from server.auth.models import (
    ApiKeyInfo,
    ApiKeyResponse,
    CreateApiKeyRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserInfo,
    UserWithLimits,
)
from server.auth.passwords import hash_password, verify_password
from server.tiers import get_tier

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
def register(body: RegisterRequest):
    existing = db.get_user_by_email(body.email)
    if existing:
        raise HTTPException(409, "Email already registered")

    user_id = str(uuid.uuid4())
    pw_hash = hash_password(body.password)
    db.create_user(user_id, body.email, pw_hash)

    access_token, expires_in = create_access_token(user_id, "free")
    refresh_token = create_refresh_token(user_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    user = db.get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")

    db.update_last_login(user["id"])
    access_token, expires_in = create_access_token(user["id"], user["tier"])
    refresh_token = create_refresh_token(user["id"])

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(401, "Invalid refresh token")

    user = db.get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(401, "User not found")

    access_token, expires_in = create_access_token(user["id"], user["tier"])
    refresh_token = create_refresh_token(user["id"])

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


# ------------------------------------------------------------------
# User info
# ------------------------------------------------------------------

@router.get("/me", response_model=UserWithLimits)
def get_me(user: AuthUser = Depends(require_auth)):
    tier = get_tier(user.tier)
    return UserWithLimits(
        id=user.id,
        email=user.email,
        tier=user.tier,
        limits={
            "max_memories": tier.max_memories,
            "max_storage_mb": tier.max_storage_mb,
            "max_namespaces": tier.max_namespaces,
            "requests_per_second": tier.requests_per_second,
            "requests_per_month": tier.requests_per_month,
            "retention_days": tier.retention_days,
            "semantic_search": tier.semantic_search,
            "websocket": tier.websocket,
        },
    )


# ------------------------------------------------------------------
# API Keys
# ------------------------------------------------------------------

@router.post("/keys", response_model=ApiKeyResponse)
def create_key(body: CreateApiKeyRequest, user: AuthUser = Depends(require_auth)):
    tier = get_tier(user.tier)
    current_count = db.count_api_keys_for_user(user.id)

    if tier.max_api_keys > 0 and current_count >= tier.max_api_keys:
        raise HTTPException(
            403,
            f"API key limit reached ({tier.max_api_keys}). Upgrade your plan for more.",
        )

    key_id, full_key, key_hash = generate_api_key()
    key_prefix = full_key[:20]

    db.store_api_key(
        key_id=key_id,
        user_id=user.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=body.name,
        scopes=body.scopes,
    )

    return ApiKeyResponse(
        id=key_id,
        key=full_key,
        key_prefix=key_prefix,
        name=body.name,
        scopes=body.scopes,
        created_at=__import__("datetime").datetime.utcnow(),
    )


@router.get("/keys", response_model=list[ApiKeyInfo])
def list_keys(user: AuthUser = Depends(require_auth)):
    keys = db.get_api_keys_for_user(user.id)
    return [
        ApiKeyInfo(
            id=k["id"],
            key_prefix=k["key_prefix"],
            name=k["name"],
            scopes=k["scopes"],
            created_at=k["created_at"],
            last_used_at=k.get("last_used_at"),
        )
        for k in keys
    ]


@router.delete("/keys/{key_id}")
def delete_key(key_id: str, user: AuthUser = Depends(require_auth)):
    if not db.delete_api_key(key_id, user.id):
        raise HTTPException(404, "API key not found")
    return {"deleted": True}
