"""Request/response models for the REST API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class StoreRequest(BaseModel):
    content: str
    type: str = "fact"
    importance: int = Field(default=5, ge=1, le=10)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    namespace: Optional[str] = None


class UpdateRequest(BaseModel):
    content: Optional[str] = None
    type: Optional[str] = None
    importance: Optional[int] = Field(default=None, ge=1, le=10)
    tags: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = None


class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=100)
    namespace: Optional[str] = None
    semantic: bool = False


class RecallRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    namespace: Optional[str] = None
    min_importance: int = Field(default=7, ge=1, le=10)


class ImportRequest(BaseModel):
    data: str  # JSON string


class ExportRequest(BaseModel):
    namespace: Optional[str] = None
    format: str = "json"


class StoreResponse(BaseModel):
    id: Optional[int]
    duplicate: bool = False


class StatsResponse(BaseModel):
    total_memories: int
    by_type: dict[str, int]
    average_importance: float
    db_size_mb: float
    namespace: Optional[str]


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    memories: int
