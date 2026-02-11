"""FastAPI REST server for Engram."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect

import engram
from engram.client import Memory
from engram.config import EngramConfig
from engram.exceptions import MemoryNotFound
from server.auth import get_namespace, verify_api_key
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

_config = EngramConfig()
_memories: dict[str, Memory] = {}


def _mem(namespace: str) -> Memory:
    """Return (or lazily create) a Memory client for *namespace*."""
    if namespace not in _memories:
        _memories[namespace] = Memory(config=_config, namespace=namespace)
    return _memories[namespace]


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------

@app.get("/v1/health", response_model=HealthResponse)
def health():
    m = _mem("default")
    s = m.stats()
    return HealthResponse(
        status="ok", version=engram.__version__, memories=s["total_memories"]
    )


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------

@app.post("/v1/memories", response_model=StoreResponse, dependencies=[Depends(verify_api_key)])
async def store_memory(body: StoreRequest, namespace: str = Depends(get_namespace)):
    mem = _mem(namespace)
    ns = body.namespace or namespace
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


@app.get("/v1/memories/{memory_id}", dependencies=[Depends(verify_api_key)])
def get_memory(memory_id: int, namespace: str = Depends(get_namespace)):
    try:
        return _mem(namespace).get(memory_id).model_dump(mode="json", exclude={"embedding"})
    except MemoryNotFound:
        raise HTTPException(404, "Memory not found")


@app.get("/v1/memories", dependencies=[Depends(verify_api_key)])
def list_memories(
    namespace: str = Depends(get_namespace),
    type: str | None = Query(None),
    min_importance: int | None = Query(None, ge=1, le=10),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    entries = _mem(namespace).list(
        type=type, min_importance=min_importance, limit=limit, offset=offset
    )
    return [e.model_dump(mode="json", exclude={"embedding"}) for e in entries]


@app.put("/v1/memories/{memory_id}", dependencies=[Depends(verify_api_key)])
async def update_memory(
    memory_id: int, body: UpdateRequest, namespace: str = Depends(get_namespace)
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
        entry = _mem(namespace).update(memory_id, **fields)
    except MemoryNotFound:
        raise HTTPException(404, "Memory not found")
    await manager.broadcast(namespace, "memory_updated", {"id": memory_id})
    return entry.model_dump(mode="json", exclude={"embedding"})


@app.delete("/v1/memories/{memory_id}", dependencies=[Depends(verify_api_key)])
async def delete_memory(memory_id: int, namespace: str = Depends(get_namespace)):
    if not _mem(namespace).delete(memory_id):
        raise HTTPException(404, "Memory not found")
    await manager.broadcast(namespace, "memory_deleted", {"id": memory_id})
    return {"deleted": True}


# ------------------------------------------------------------------
# Search / Recall
# ------------------------------------------------------------------

@app.post("/v1/search", dependencies=[Depends(verify_api_key)])
def search_memories(body: SearchRequest, namespace: str = Depends(get_namespace)):
    results = _mem(namespace).search(
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


@app.post("/v1/recall", dependencies=[Depends(verify_api_key)])
def recall_memories(body: RecallRequest, namespace: str = Depends(get_namespace)):
    entries = _mem(namespace).recall(
        limit=body.limit,
        namespace=body.namespace or namespace,
        min_importance=body.min_importance,
    )
    return [e.model_dump(mode="json", exclude={"embedding"}) for e in entries]


# ------------------------------------------------------------------
# Stats / Export / Import
# ------------------------------------------------------------------

@app.get("/v1/stats", response_model=StatsResponse, dependencies=[Depends(verify_api_key)])
def get_stats(namespace: str = Depends(get_namespace)):
    return _mem(namespace).stats()


@app.post("/v1/export", dependencies=[Depends(verify_api_key)])
def export_memories(body: ExportRequest, namespace: str = Depends(get_namespace)):
    data = _mem(namespace).export_memories(
        namespace=body.namespace or namespace,
        format=body.format,
    )
    return {"data": data, "format": body.format}


@app.post("/v1/import", dependencies=[Depends(verify_api_key)])
def import_memories(body: ImportRequest, namespace: str = Depends(get_namespace)):
    count = _mem(namespace).import_memories(body.data)
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
