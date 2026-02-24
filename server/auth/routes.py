"""Authentication API routes."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

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
    UserWithLimits,
)
from server.auth.passwords import hash_password, verify_password
from server.tiers import get_tier

router = APIRouter(prefix="/v1/auth", tags=["auth"])


TRIAL_DAYS = 7

# ------------------------------------------------------------------
# Rate limiting for auth endpoints (per IP)
# ------------------------------------------------------------------

_register_hits: dict[str, list[float]] = defaultdict(list)
_REGISTER_LIMIT = 10  # max registrations per IP per window
_REGISTER_WINDOW = 600  # 10 minutes

_login_failures: dict[str, list[float]] = defaultdict(list)
_LOGIN_FAIL_LIMIT = 5  # max failed attempts per email
_LOGIN_LOCKOUT = 900  # 15 minutes


def reset_auth_rate_limits() -> None:
    """Clear all rate limit state. Used in tests."""
    _register_hits.clear()
    _login_failures.clear()


def _check_register_rate(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    cutoff = now - _REGISTER_WINDOW
    hits = _register_hits[ip] = [t for t in _register_hits[ip] if t > cutoff]
    if len(hits) >= _REGISTER_LIMIT:
        raise HTTPException(429, "Too many registrations. Try again later.")
    hits.append(now)


def _check_login_lockout(email: str) -> None:
    now = time.monotonic()
    cutoff = now - _LOGIN_LOCKOUT
    failures = _login_failures[email] = [t for t in _login_failures[email] if t > cutoff]
    if len(failures) >= _LOGIN_FAIL_LIMIT:
        raise HTTPException(
            429,
            "Account temporarily locked due to too many failed attempts. Try again in 15 minutes.",
        )


def _record_login_failure(email: str) -> None:
    _login_failures[email].append(time.monotonic())


def _clear_login_failures(email: str) -> None:
    _login_failures.pop(email, None)


@router.post("/register", response_model=TokenResponse)
def register(body: RegisterRequest, request: Request):
    _check_register_rate(request)

    existing = db.get_user_by_email(body.email)
    if existing:
        raise HTTPException(409, "Email already registered")

    user_id = str(uuid.uuid4())
    pw_hash = hash_password(body.password)
    trial_end = (datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS)).isoformat()
    db.create_user(user_id, body.email, pw_hash, tier="pro", trial_end=trial_end)

    access_token, expires_in = create_access_token(user_id, "pro")
    refresh_token = create_refresh_token(user_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    _check_login_lockout(body.email)

    user = db.get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        _record_login_failure(body.email)
        raise HTTPException(401, "Invalid email or password")

    _clear_login_failures(body.email)
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
    user_record = db.get_user_by_id(user.id)
    trial_end = user_record.get("trial_end") if user_record else None

    # Calculate days remaining
    trial_days_remaining = None
    if trial_end:
        try:
            end_dt = datetime.fromisoformat(trial_end)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            remaining = (end_dt - datetime.now(timezone.utc)).days
            trial_days_remaining = max(0, remaining)
        except (ValueError, TypeError):
            pass

    return UserWithLimits(
        id=user.id,
        email=user.email,
        tier=user.tier,
        trial_end=trial_end,
        trial_days_remaining=trial_days_remaining,
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
        created_at=datetime.now(timezone.utc),
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
