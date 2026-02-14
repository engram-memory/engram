"""FastAPI REST server for Engram."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import engram
import server.auth.dependencies as auth_deps
from engram.client import Memory
from engram.config import EngramConfig
from engram.exceptions import MemoryNotFoundError
from engram.sessions import SessionManager
from server.auth.database import init_admin_db
from server.auth.dependencies import AuthUser, get_namespace, require_auth
from server.auth.routes import router as auth_router
from server.billing.routes import router as billing_router
from server.demo_routes import router as demo_router
from server.models import (
    AnalyticsResponse,
    AutoSaveConfigRequest,
    CheckpointRequest,
    ContextRequest,
    ContextResponse,
    ExportRequest,
    GraphRequest,
    HealthResponse,
    ImportRequest,
    LinkRequest,
    RecallRequest,
    SearchRequest,
    SessionRecoverRequest,
    SessionSaveRequest,
    StatsResponse,
    StoreRequest,
    StoreResponse,
    UpdateRequest,
)
from server.synapse_routes import router as synapse_router
from server.websocket import manager

app = FastAPI(
    title="Engram",
    description="Memory that sticks. Universal memory layer for AI agents.",
    version=engram.__version__,
)

# CORS — allow landing page to call billing API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://engram-ai.dev",
        "https://www.engram-ai.dev",
        "http://localhost:3000",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Always register auth routes (they work in both modes).
# Cloud-specific middleware only loads when auth_deps.CLOUD_MODE is active.
init_admin_db()
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(synapse_router)
app.include_router(demo_router)

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
        config = EngramConfig(db_path=db_path, enable_embeddings=True)
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
            f"Upgrade your plan at https://engram-ai.dev/#pricing",
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
    if (
        auth_deps.CLOUD_MODE
        and not request.url.path.startswith("/v1/auth")
        and not request.url.path.startswith("/v1/demo")
        and request.url.path != "/v1/health"
    ):
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
    return HealthResponse(status="ok", version=engram.__version__, memories=s["total_memories"])


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
        ttl_days=body.ttl_days,
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
    except MemoryNotFoundError:
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
    except MemoryNotFoundError:
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
# Context Builder (Pro)
# ------------------------------------------------------------------


@app.post("/v1/context", response_model=ContextResponse)
def build_context_endpoint(
    body: ContextRequest,
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
):
    """Build a token-budgeted context from the most relevant memories."""
    _check_pro(user)
    result = _mem(user, namespace).context(
        body.prompt,
        max_tokens=body.max_tokens,
        namespace=body.namespace or namespace,
        min_importance=body.min_importance,
    )
    return ContextResponse(
        context=result.context,
        memories_used=result.memories_used,
        token_count=result.token_count,
        truncated=result.truncated,
        memory_ids=result.memory_ids,
    )


# ------------------------------------------------------------------
# Stats / Export / Import
# ------------------------------------------------------------------


@app.get("/v1/stats", response_model=StatsResponse)
def get_stats(
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
):
    return _mem(user, namespace).stats()


@app.get("/v1/usage")
def get_usage(
    user: AuthUser = Depends(require_auth),
):
    """Get current memory usage across all namespaces for the authenticated user."""
    import sqlite3

    limits = user.limits

    if auth_deps.CLOUD_MODE:
        db_path = _DATA_DIR / "tenants" / user.id / "memory.db"
    else:
        db_path = _DATA_DIR / "memory.db"

    total_memories = 0
    namespaces_used = 0
    by_namespace: dict[str, int] = {}

    try:
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT COUNT(*) FROM memories").fetchone()
        total_memories = row[0] if row else 0

        ns_rows = conn.execute(
            "SELECT namespace, COUNT(*) AS cnt FROM memories GROUP BY namespace"
        ).fetchall()
        namespaces_used = len(ns_rows)
        by_namespace = {r[0]: r[1] for r in ns_rows}
        conn.close()
    except sqlite3.OperationalError:
        pass  # DB doesn't exist yet

    return {
        "memories_used": total_memories,
        "memories_limit": limits.max_memories,
        "memories_pct": (
            round(total_memories / limits.max_memories * 100, 1)
            if limits.max_memories > 0
            else 0
        ),
        "namespaces_used": namespaces_used,
        "namespaces_limit": limits.max_namespaces,
        "by_namespace": by_namespace,
        "tier": user.tier,
    }


@app.get("/v1/analytics", response_model=AnalyticsResponse)
def get_analytics(
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
    days: int = Query(90, ge=7, le=365),
):
    """Pro analytics dashboard data."""
    if not user.limits.analytics:
        raise HTTPException(
            403, "Analytics is a Pro feature. Upgrade at https://engram-ai.dev/#pricing"
        )
    return _mem(user, namespace).analytics(namespace=namespace, days=days)


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
# Backfill & Cleanup (Pro)
# ------------------------------------------------------------------


@app.post("/v1/backfill-embeddings")
def backfill_embeddings(
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
):
    """Generate embeddings for memories that don't have them."""
    _check_semantic_search(user, True)
    count = _mem(user, namespace).backfill_embeddings(namespace=namespace)
    return {"backfilled": count}


@app.post("/v1/cleanup-expired")
def cleanup_expired(
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
):
    """Permanently remove expired memories."""
    count = _mem(user, namespace).cleanup_expired(namespace=namespace)
    return {"removed": count}


# ------------------------------------------------------------------
# Sessions (Pro)
# ------------------------------------------------------------------

_session_managers: dict[str, SessionManager] = {}


def _sess(user: AuthUser) -> SessionManager:
    """Return a SessionManager scoped to the user."""
    if auth_deps.CLOUD_MODE:
        db_path = _DATA_DIR / "tenants" / user.id / "memory.db"
    else:
        db_path = _DATA_DIR / "memory.db"
    if user.id not in _session_managers:
        _session_managers[user.id] = SessionManager(db_path=db_path)
    return _session_managers[user.id]


def _check_pro(user: AuthUser) -> None:
    """Raise 403 if user is not on Pro or Enterprise tier."""
    if user.tier not in ("pro", "enterprise"):
        raise HTTPException(
            403,
            "Sessions are a Pro feature. Upgrade at https://engram-ai.dev/#pricing",
        )


@app.post("/v1/sessions/save")
def session_save(
    body: SessionSaveRequest,
    user: AuthUser = Depends(require_auth),
):
    _check_pro(user)
    return _sess(user).save_checkpoint(
        project=body.project,
        summary=body.summary,
        key_facts=body.key_facts or None,
        open_tasks=body.open_tasks or None,
        files_modified=body.files_modified or None,
    )


@app.get("/v1/sessions/latest")
def session_load(
    user: AuthUser = Depends(require_auth),
    project: str | None = Query(None),
    session_id: str | None = Query(None),
):
    _check_pro(user)
    result = _sess(user).load_checkpoint(project=project, session_id=session_id)
    if result is None:
        raise HTTPException(404, "No checkpoint found. Save one first with POST /v1/sessions/save")
    return result


@app.get("/v1/sessions")
def session_list(
    user: AuthUser = Depends(require_auth),
    project: str | None = Query(None),
    limit: int = Query(10, ge=1, le=100),
):
    _check_pro(user)
    sessions = _sess(user).list_sessions(project=project, limit=limit)
    return {"sessions": sessions, "count": len(sessions)}


@app.post("/v1/sessions/recover")
def session_recover(
    body: SessionRecoverRequest,
    user: AuthUser = Depends(require_auth),
):
    _check_pro(user)
    return {"recovery": _sess(user).recover_context(project=body.project)}


# ------------------------------------------------------------------
# Memory Links (Pro — Phase 3B)
# ------------------------------------------------------------------


@app.post("/v1/links")
async def create_link(
    body: LinkRequest,
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
):
    """Create a directed link between two memories."""
    _check_pro(user)
    link_id = _mem(user, namespace).link(body.source_id, body.target_id, body.relation)
    if link_id is None:
        raise HTTPException(409, "Link already exists or invalid memory IDs")
    await manager.broadcast(
        namespace,
        "link_created",
        {
            "id": link_id,
            "source_id": body.source_id,
            "target_id": body.target_id,
            "relation": body.relation,
        },
    )
    return {"id": link_id, "status": "linked"}


@app.delete("/v1/links/{link_id}")
async def delete_link(
    link_id: int,
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
):
    """Remove a link between memories."""
    _check_pro(user)
    if not _mem(user, namespace).unlink(link_id):
        raise HTTPException(404, "Link not found")
    await manager.broadcast(namespace, "link_deleted", {"id": link_id})
    return {"deleted": True}


@app.get("/v1/memories/{memory_id}/links")
def get_memory_links(
    memory_id: int,
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
    direction: str = Query("both", pattern="^(outgoing|incoming|both)$"),
    relation: str | None = Query(None),
):
    """Get all links for a specific memory."""
    _check_pro(user)
    links = _mem(user, namespace).links(memory_id, direction=direction, relation=relation)
    return {"links": links, "count": len(links)}


@app.post("/v1/graph")
def traverse_graph(
    body: GraphRequest,
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
):
    """BFS graph traversal starting from a memory."""
    _check_pro(user)
    return _mem(user, namespace).graph(
        body.memory_id, max_depth=body.max_depth, relation=body.relation
    )


# ------------------------------------------------------------------
# Agent AutoSave (Pro — Phase 4)
# ------------------------------------------------------------------

_autosavers: dict[str, Any] = {}


def _get_autosaver(user: AuthUser, project: str | None = None) -> Any:
    from engram.autosave import AutoSave

    key = f"{user.id}:{project or '__default__'}"
    if key not in _autosavers:
        _autosavers[key] = AutoSave(_sess(user), project=project)
    return _autosavers[key]


@app.post("/v1/autosave/configure")
def configure_autosave(
    body: AutoSaveConfigRequest,
    user: AuthUser = Depends(require_auth),
):
    """Configure autosave triggers."""
    _check_pro(user)
    saver = _get_autosaver(user, body.project)
    cfg = saver.configure(
        enabled=body.enabled,
        interval_seconds=body.interval_minutes * 60,
        message_threshold=body.message_threshold,
        ram_threshold_pct=body.ram_threshold_pct,
    )
    return {"status": "configured", "config": cfg.to_dict()}


@app.get("/v1/autosave/status")
def autosave_status(
    user: AuthUser = Depends(require_auth),
    project: str | None = Query(None),
):
    """Get current autosave status."""
    _check_pro(user)
    key = f"{user.id}:{project or '__default__'}"
    if key not in _autosavers:
        return {
            "status": "not_configured",
            "hint": "Use POST /v1/autosave/configure to enable autosave",
        }
    return _autosavers[key].status()


@app.post("/v1/autosave/checkpoint")
async def create_checkpoint(
    body: CheckpointRequest,
    user: AuthUser = Depends(require_auth),
    namespace: str = Depends(get_namespace),
):
    """Create an incremental checkpoint with delta tracking."""
    _check_pro(user)
    key = f"{user.id}:{body.project or '__default__'}"
    if key in _autosavers:
        result = _autosavers[key].checkpoint(reason=body.reason)
    else:
        result = _sess(user).save_checkpoint(
            project=body.project,
            summary=body.summary or f"[checkpoint:{body.reason}]",
            key_facts=body.key_facts or None,
            open_tasks=body.open_tasks or None,
        )
        result["reason"] = body.reason
    await manager.broadcast(namespace, "checkpoint_created", {"reason": body.reason})
    return result


@app.post("/v1/autosave/restore")
def restore_checkpoint(
    user: AuthUser = Depends(require_auth),
    project: str | None = Query(None),
):
    """Restore from the latest checkpoint."""
    _check_pro(user)
    result = _sess(user).load_checkpoint(project=project)
    if result is None:
        raise HTTPException(404, "No checkpoint found")
    return result


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
