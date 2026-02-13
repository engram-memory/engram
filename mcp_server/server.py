"""Engram MCP Server — exposes memory tools to Claude Code and other MCP clients."""

from __future__ import annotations

import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool

from engram.client import Memory
from engram.config import EngramConfig
from engram.sessions import SessionManager
from mcp_server.tools import PRO_TOOL_DEFINITIONS, TOOL_DEFINITIONS

app = Server("engram")
_config = EngramConfig()
_memories: dict[str, Memory] = {}
_sessions: SessionManager | None = None


def _mem(namespace: str = "default") -> Memory:
    if namespace not in _memories:
        _memories[namespace] = Memory(config=_config, namespace=namespace)
    return _memories[namespace]


def _sess() -> SessionManager:
    global _sessions
    if _sessions is None:
        _sessions = SessionManager(db_path=_config.db_path)
    return _sessions


# ------------------------------------------------------------------
# Tools
# ------------------------------------------------------------------

@app.list_tools()
async def list_tools() -> list[Tool]:
    all_tools = TOOL_DEFINITIONS + PRO_TOOL_DEFINITIONS
    return [Tool(**td) for td in all_tools]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = _dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, default=str))]
    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


def _dispatch(name: str, args: dict) -> dict:
    ns = args.get("namespace", "default")
    mem = _mem(ns)

    if name == "memory_store":
        mid = mem.store(
            args["content"],
            type=args.get("type", "fact"),
            importance=args.get("importance", 5),
            tags=args.get("tags", []),
            namespace=ns,
        )
        return {"id": mid, "duplicate": mid is None, "status": "stored"}

    if name == "memory_search":
        results = mem.search(args["query"], limit=args.get("limit", 10), namespace=ns)
        return {
            "results": [
                {
                    "content": r.memory.content,
                    "type": r.memory.memory_type.value,
                    "importance": r.memory.importance,
                    "score": r.score,
                    "id": r.memory.id,
                }
                for r in results
            ],
            "count": len(results),
        }

    if name == "memory_recall":
        entries = mem.recall(
            limit=args.get("limit", 20),
            namespace=ns,
            min_importance=args.get("min_importance", 7),
        )
        return {
            "memories": [
                {
                    "content": e.content,
                    "type": e.memory_type.value,
                    "importance": e.importance,
                    "id": e.id,
                }
                for e in entries
            ],
            "count": len(entries),
        }

    if name == "memory_delete":
        deleted = mem.delete(args["memory_id"])
        return {"deleted": deleted, "memory_id": args["memory_id"]}

    if name == "memory_stats":
        return mem.stats(namespace=ns)

    # -- Pro Tools: Sessions --

    if name == "memory_session_save":
        return _sess().save_checkpoint(
            project=args.get("project"),
            summary=args["summary"],
            key_facts=args.get("key_facts"),
            open_tasks=args.get("open_tasks"),
            files_modified=args.get("files_modified"),
        )

    if name == "memory_session_load":
        result = _sess().load_checkpoint(
            project=args.get("project"),
            session_id=args.get("session_id"),
        )
        if result is None:
            return {
                "error": "No checkpoint found",
                "hint": "Save a checkpoint first with memory_session_save",
            }
        return result

    if name == "memory_session_list":
        sessions = _sess().list_sessions(
            project=args.get("project"),
            limit=args.get("limit", 10),
        )
        return {"sessions": sessions, "count": len(sessions)}

    # -- Pro Tools: Semantic Search --

    if name == "memory_semantic_search":
        results = mem.search(
            args["query"],
            limit=args.get("limit", 10),
            namespace=ns,
            semantic=True,
        )
        return {
            "results": [
                {
                    "content": r.memory.content,
                    "type": r.memory.memory_type.value,
                    "importance": r.memory.importance,
                    "score": r.score,
                    "id": r.memory.id,
                }
                for r in results
            ],
            "count": len(results),
            "method": "semantic",
        }

    # -- Pro Tools: Context Recovery --

    if name == "memory_recover":
        return {"recovery": _sess().recover_context(project=args.get("project"))}

    return {"error": f"Unknown tool: {name}"}


# ------------------------------------------------------------------
# Resources
# ------------------------------------------------------------------

@app.list_resources()
async def list_resources() -> list[Resource]:
    return [
        Resource(
            uri="engram://memories/default",
            name="All memories (default namespace)",
            mimeType="application/json",
        )
    ]


@app.read_resource()
async def read_resource(uri: str) -> str:
    # engram://memories/{namespace}
    parts = str(uri).replace("engram://", "").split("/")
    namespace = parts[1] if len(parts) > 1 else "default"
    entries = _mem(namespace).list(limit=1000)
    data = [
        {
            "id": e.id,
            "content": e.content,
            "type": e.memory_type.value,
            "importance": e.importance,
            "tags": e.tags,
        }
        for e in entries
    ]
    return json.dumps(data, default=str)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
