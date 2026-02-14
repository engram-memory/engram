"""Demo playground routes — no auth, rate-limited per IP, shared demo namespace."""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from engram.client import Memory
from engram.config import EngramConfig

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/demo", tags=["demo"])

_DATA_DIR = Path(os.environ.get("ENGRAM_DATA_DIR", str(Path.home() / ".engram")))
DEMO_MAX_MEMORIES = 500
DEMO_MAX_CONTENT_LEN = 200

# ------------------------------------------------------------------
# Rate limiter (10 req/min per IP)
# ------------------------------------------------------------------

_ip_hits: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 10
RATE_WINDOW = 60  # seconds


def _check_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    cutoff = now - RATE_WINDOW
    hits = _ip_hits[ip] = [t for t in _ip_hits[ip] if t > cutoff]
    if len(hits) >= RATE_LIMIT:
        raise HTTPException(429, "Rate limit exceeded. Try again in a minute.")
    hits.append(now)


# ------------------------------------------------------------------
# Demo Memory instance (shared, single namespace)
# ------------------------------------------------------------------

_demo_mem: Memory | None = None
_seeded = False

SEED_MEMORIES = [
    ("User prefers dark mode and compact layout", "preference", 8, ["ui", "preference"]),
    ("Project deadline is March 15, 2026", "fact", 9, ["project", "deadline"]),
    ("Fixed login bug by adding null check to auth middleware", "error_fix", 7, ["bug", "auth"]),
    (
        "Team uses PostgreSQL for production, SQLite for development",
        "fact",
        6,
        ["database", "stack"],
    ),
    ("User timezone is Europe/Vienna (CET/CEST)", "preference", 7, ["locale", "preference"]),
    (
        "API rate limit should be 100 req/s for pro tier",
        "decision",
        8,
        ["api", "architecture"],
    ),
    ("React 19 breaks useEffect cleanup in strict mode", "error_fix", 6, ["react", "bug"]),
    (
        "Always use parameterized queries to prevent SQL injection",
        "pattern",
        9,
        ["security", "sql"],
    ),
]


def _get_demo_mem() -> Memory:
    global _demo_mem, _seeded
    if _demo_mem is None:
        db_path = _DATA_DIR / "demo" / "playground.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        config = EngramConfig(db_path=db_path)
        _demo_mem = Memory(config=config, namespace="playground")
    if not _seeded:
        _seeded = True
        stats = _demo_mem.stats()
        if stats["total_memories"] == 0:
            for content, mtype, importance, tags in SEED_MEMORIES:
                _demo_mem.store(content, type=mtype, importance=importance, tags=tags)
            log.info("Seeded %d demo memories", len(SEED_MEMORIES))
    return _demo_mem


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------


class DemoStoreRequest(BaseModel):
    content: str = Field(..., max_length=DEMO_MAX_CONTENT_LEN)
    type: str = "fact"
    importance: int = Field(5, ge=1, le=10)
    tags: list[str] = []


class DemoSearchRequest(BaseModel):
    query: str = Field(..., max_length=100)
    limit: int = Field(5, ge=1, le=10)


class DemoRecallRequest(BaseModel):
    limit: int = Field(10, ge=1, le=20)
    min_importance: int = Field(5, ge=1, le=10)


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post("/store")
def demo_store(body: DemoStoreRequest, request: Request):
    """Store a memory in the demo playground. No auth required."""
    _check_rate_limit(request)
    mem = _get_demo_mem()

    # Cap total demo memories
    stats = mem.stats()
    if stats["total_memories"] >= DEMO_MAX_MEMORIES:
        raise HTTPException(400, "Demo limit reached. Sign up for unlimited memories!")

    mid = mem.store(
        body.content,
        type=body.type,
        importance=body.importance,
        tags=body.tags,
    )
    return {"id": mid, "stored": True}


@router.post("/search")
def demo_search(body: DemoSearchRequest, request: Request):
    """Search demo memories. No auth required."""
    _check_rate_limit(request)
    mem = _get_demo_mem()
    results = mem.search(body.query, limit=body.limit)
    return [
        {
            "content": r.memory.content,
            "type": (
                r.memory.memory_type.value
                if hasattr(r.memory.memory_type, "value")
                else str(r.memory.memory_type)
            ),
            "importance": r.memory.importance,
            "tags": r.memory.tags,
            "score": round(r.score, 2),
        }
        for r in results
    ]


@router.post("/recall")
def demo_recall(body: DemoRecallRequest, request: Request):
    """Recall top demo memories by importance. No auth required."""
    _check_rate_limit(request)
    mem = _get_demo_mem()
    entries = mem.recall(limit=body.limit, min_importance=body.min_importance)
    return [
        {
            "content": e.content,
            "type": e.memory_type.value if hasattr(e.memory_type, "value") else str(e.memory_type),
            "importance": e.importance,
            "tags": e.tags,
        }
        for e in entries
    ]


@router.get("/stats")
def demo_stats(request: Request):
    """Get demo playground stats. No auth required."""
    _check_rate_limit(request)
    mem = _get_demo_mem()
    stats = mem.stats()
    return {
        "total_memories": stats["total_memories"],
        "by_type": stats.get("by_type", {}),
    }
