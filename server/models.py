"""Request/response models for the REST API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StoreRequest(BaseModel):
    content: str
    type: str = "fact"
    importance: int = Field(default=5, ge=1, le=10)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    namespace: str | None = None


class UpdateRequest(BaseModel):
    content: str | None = None
    type: str | None = None
    importance: int | None = Field(default=None, ge=1, le=10)
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=100)
    namespace: str | None = None
    semantic: bool = False


class RecallRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    namespace: str | None = None
    min_importance: int = Field(default=7, ge=1, le=10)


class ImportRequest(BaseModel):
    data: str  # JSON string


class ExportRequest(BaseModel):
    namespace: str | None = None
    format: str = "json"


class StoreResponse(BaseModel):
    id: int | None
    duplicate: bool = False


class StatsResponse(BaseModel):
    total_memories: int
    by_type: dict[str, int]
    average_importance: float
    db_size_mb: float
    namespace: str | None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    memories: int
