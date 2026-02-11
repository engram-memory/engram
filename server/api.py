"""FastAPI REST server for Engram."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

import engram
from engram.client import Memory
from engram.config import EngramConfig
from engram.exceptions import MemoryNotFound
import server.auth.dependencies as auth_deps
from server.auth.dependencies import AuthUser, get_namespace, require_auth
from server.models import (
    ExportRequest,
    HealthResponse,
    ImportRequest,
    RecallRequest,
    SearchRequest,
    StatsResponse,
    StoreRequest,
    StoreResponse,
    UpdateRequest,
)
from server.websocket import manager

app = FastAPI(
    title="Engram",
    description="Memory that sticks. Universal memory layer for AI agents.",
    version=engram.__version__,
)

# Always register auth routes (they work in both modes).
# Cloud-specific middleware only loads when auth_deps.CLOUD_MODE is active.
from server.auth.database import init_admin_db
from server.auth.routes import router as auth_router

init_admin_db()
app.include_router(auth_router)

if auth_deps.CLOUD_MODE:
    from server.middleware import RateLimitMiddleware

    app.add_middleware(RateLimitMiddleware)

# ------------------------------------------------------------------
# Tenant-aware Memory factory
# ------------------------------------------------------------------

_DATA_DIR = Path(os.environ.get("ENGRAM_DATA_DIR", str(Path.home() / ".engram")))
_memories: dict[str, Memory] = {}


def _mem(user: AuthUser, namespace: str) -> Memory:
    """Return (or lazily create) a Memory client scoped to user + namespace."""
    if auth_deps.CLOUD_MODE:
        # Each user gets their own SQLite database
        db_path = _DATA_DIR / "tenants" / user.id / "memory.db"
    else:
        # Local mode: single shared database (backwards compatible)
        db_path = _DATA_DIR / "memory.db"

    cache_key = f"{user.id}:{namespace}"
    if cache_key not in _memories:
        config = EngramConfig(db_path=db_path)
        _memories[cache_key] = Memory(config=config, namespace=namespace)
    return _memories[cache_key]


def _check_memory_limit(user: AuthUser, mem: Memory) -> None:
    """Raise 403 if user has hit their memory limit."""
    limits = user.limits
    if limits.max_memories <= 0:  # unlimited
        return
    stats = mem.stats()
    if stats["total_memories"] >= limits.max_memories:
        raise HTTPException(
            403,
            f"Memory limit reached ({limits.max_memories}). "
            f"Upgrade your plan at https://engram.dev/pricing",
        )


def _check_namespace_limit(user: AuthUser, namespace: str, mem: Memory) -> None:
    """Raise 403 if user has hit their namespace limit."""
    limits = user.limits
    if limits.max_namespaces <= 0:  # unlimited
        return
    # Quick check: count distinct namespaces in the user's DB
    import sqlite3
    try:
        conn = sqlite3.connect(str(mem._config.db_path))
        row = conn.execute("SELECT COUNT(DISTINCT namespace) AS cnt FROM memories").fetchone()
        conn.close()
        if row and row[0] >= limits.max_namespaces:
            # Only block if the namespace is new
            row2 = conn if False else None  # already closed
            conn2 = sqlite3.connect(str(mem._config.db_path))
            exists = conn2.execute(
                "SELECT 1 FROM memories WHERE namespace = ? LIMIT 1", (namespace,)
            ).fetchone()
            conn2.close()
            if not exists:
                raise HTTPException(
                    403,
                    f"Namespace limit reached ({limits.max_namespaces}). "
                    f"Upgrade your plan for more.",
                )
    except sqlite3.OperationalError:
        pass  # DB doesn't exist yet, no limit hit


def _check_semantic_search(user: AuthUser, semantic: bool) -> None:
    if semantic and not user.limits.semantic_search:
        raise HTTPException(
            403,
            "Semantic search is not available on your plan. Upgrade to Pro.",
        )


def _check_websocket(user: AuthUser) -> None:
    if not user.limits.websocket:
        raise HTTPException(
            403,
            "WebSocket events are not available on your plan. Upgrade to Pro.",
        )


# ------------------------------------------------------------------
# Inject auth user into request state for middleware
# ------------------------------------------------------------------

@app.middleware("http")
async def inject_auth_user(request: Request, call_next):
    """Make auth user available in request.state for rate limit middleware."""
    if auth_deps.CLOUD_MODE and not request.url.path.startswith("/v1/auth") and request.url.path != "/v1/health":
        try:
            user = require_auth(request)
            request.state.auth_user = user
        except HTTPException:
            pass  # will be caught by the dependency
    response = await call_next(request)
    return response


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------

@app.get("/v1/health", response_model=HealthResponse)
def health():
    m = Memory(config=EngramConfig(db_path=_DATA_DIR / "memory.db"), namespace="default")
    s = m.stats()
    return HealthResponse(
        status="ok", version=engram.__version__, memories=s["total_memories"]
    )


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------

@app.post("/v1/memories", response_model=StoreResponse)
async def store_memory(
    body: StoreRequest,
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
):
    ns = body.namespace or namespace
    mem = _mem(user, ns)
    _check_memory_limit(user, mem)
    mid = mem.store(
        body.content,
        type=body.type,
        importance=body.importance,
        tags=body.tags,
        metadata=body.metadata,
        namespace=ns,
    )
    await manager.broadcast(ns, "memory_stored", {"id": mid})
    return StoreResponse(id=mid, duplicate=mid is None)


@app.get("/v1/memories/{memory_id}")
def get_memory(
    memory_id: int,
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
):
    try:
        return _mem(user, namespace).get(memory_id).model_dump(mode="json", exclude={"embedding"})
    except MemoryNotFound:
        raise HTTPException(404, "Memory not found")


@app.get("/v1/memories")
def list_memories(
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
    type: str | None = Query(None),
    min_importance: int | None = Query(None, ge=1, le=10),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    entries = _mem(user, namespace).list(
        type=type, min_importance=min_importance, limit=limit, offset=offset
    )
    return [e.model_dump(mode="json", exclude={"embedding"}) for e in entries]


@app.put("/v1/memories/{memory_id}")
async def update_memory(
    memory_id: int,
    body: UpdateRequest,
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
):
    fields: dict[str, Any] = {}
    if body.content is not None:
        fields["content"] = body.content
    if body.type is not None:
        fields["memory_type"] = body.type
    if body.importance is not None:
        fields["importance"] = body.importance
    if body.tags is not None:
        fields["tags"] = body.tags
    if body.metadata is not None:
        fields["metadata"] = body.metadata
    try:
        entry = _mem(user, namespace).update(memory_id, **fields)
    except MemoryNotFound:
        raise HTTPException(404, "Memory not found")
    await manager.broadcast(namespace, "memory_updated", {"id": memory_id})
    return entry.model_dump(mode="json", exclude={"embedding"})


@app.delete("/v1/memories/{memory_id}")
async def delete_memory(
    memory_id: int,
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
):
    if not _mem(user, namespace).delete(memory_id):
        raise HTTPException(404, "Memory not found")
    await manager.broadcast(namespace, "memory_deleted", {"id": memory_id})
    return {"deleted": True}


# ------------------------------------------------------------------
# Search / Recall
# ------------------------------------------------------------------

@app.post("/v1/search")
def search_memories(
    body: SearchRequest,
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
):
    _check_semantic_search(user, body.semantic)
    results = _mem(user, namespace).search(
        body.query,
        limit=body.limit,
        namespace=body.namespace or namespace,
        semantic=body.semantic,
    )
    return [
        {
            "memory": r.memory.model_dump(mode="json", exclude={"embedding"}),
            "score": r.score,
            "match_type": r.match_type,
        }
        for r in results
    ]


@app.post("/v1/recall")
def recall_memories(
    body: RecallRequest,
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
):
    entries = _mem(user, namespace).recall(
        limit=body.limit,
        namespace=body.namespace or namespace,
        min_importance=body.min_importance,
    )
    return [e.model_dump(mode="json", exclude={"embedding"}) for e in entries]


# ------------------------------------------------------------------
# Stats / Export / Import
# ------------------------------------------------------------------

@app.get("/v1/stats", response_model=StatsResponse)
def get_stats(
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
):
    return _mem(user, namespace).stats()


@app.post("/v1/export")
def export_memories(
    body: ExportRequest,
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
):
    data = _mem(user, namespace).export_memories(
        namespace=body.namespace or namespace,
        format=body.format,
    )
    return {"data": data, "format": body.format}


@app.post("/v1/import")
def import_memories(
    body: ImportRequest,
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
):
    count = _mem(user, namespace).import_memories(body.data)
    return {"imported": count}


# ------------------------------------------------------------------
# WebSocket
# ------------------------------------------------------------------

@app.websocket("/v1/ws/{namespace}")
async def ws_endpoint(websocket: WebSocket, namespace: str):
    await manager.connect(websocket, namespace)
    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        manager.disconnect(websocket, namespace)


# ------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------

def run():
    import uvicorn

    uvicorn.run("server.api:app", host="0.0.0.0", port=8100, reload=True)


if __name__ == "__main__":
    run()
