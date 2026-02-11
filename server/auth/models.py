"""Pydantic models for authentication."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class CreateApiKeyRequest(BaseModel):
    name: str = "default"
    scopes: list[str] = Field(default_factory=lambda: ["memories:read", "memories:write"])


class ApiKeyResponse(BaseModel):
    id: str
    key: str  # only returned once at creation
    key_prefix: str
    name: str
    scopes: list[str]
    created_at: datetime


class ApiKeyInfo(BaseModel):
    id: str
    key_prefix: str
    name: str
    scopes: list[str]
    created_at: datetime
    last_used_at: Optional[datetime] = None


class UserInfo(BaseModel):
    id: str
    email: str
    tier: str
    created_at: datetime


class UserWithLimits(BaseModel):
    id: str
    email: str
    tier: str
    limits: dict
