"""MCP tool definitions for Engram."""

TOOL_DEFINITIONS = [
    {
        "name": "memory_store",
        "description": "Store a memory. Deduplicates automatically via content hash.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The memory content to store",
                },
                "type": {
                    "type": "string",
                    "description": (
                        "Memory type: fact, preference, decision,"
                        " error_fix, pattern, workflow, summary, custom"
                    ),
                    "default": "fact",
                },
                "importance": {
                    "type": "integer",
                    "description": "Importance 1-10 (10 = critical)",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10,
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Searchable tags",
                    "default": [],
                },
                "namespace": {
                    "type": "string",
                    "description": "Memory namespace (default: 'default')",
                },
                "ttl_days": {
                    "type": "integer",
                    "description": "Auto-expire after N days (optional, null = never)",
                    "minimum": 1,
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "memory_search",
        "description": "Search memories using full-text search (FTS5).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 10,
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace to search in",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_recall",
        "description": "Retrieve highest-priority memories for context injection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max memories to recall",
                    "default": 20,
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace",
                },
                "min_importance": {
                    "type": "integer",
                    "description": "Minimum importance threshold",
                    "default": 7,
                },
            },
        },
    },
    {
        "name": "memory_delete",
        "description": "Delete a memory by its ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "integer",
                    "description": "The memory ID to delete",
                },
            },
            "required": ["memory_id"],
        },
    },
    {
        "name": "memory_stats",
        "description": "Get memory statistics (total count, by type, average importance).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to get stats for",
                },
            },
        },
    },
]

# ------------------------------------------------------------------
# Pro Tools — Sessions, Semantic Search, Context Recovery
# ------------------------------------------------------------------

PRO_TOOL_DEFINITIONS = [
    {
        "name": "memory_session_save",
        "description": (
            "Save a session checkpoint with summary, key facts, and open tasks."
            " Use this before ending a conversation to preserve state."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Summary of what was accomplished in this session",
                },
                "project": {
                    "type": "string",
                    "description": "Project name to group sessions",
                },
                "key_facts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Important facts from this session",
                },
                "open_tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tasks that still need to be done",
                },
                "files_modified": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files that were changed in this session",
                },
            },
            "required": ["summary"],
        },
    },
    {
        "name": "memory_session_load",
        "description": (
            "Load the most recent session checkpoint."
            " Use this at the start of a conversation to recover context."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {
                    "type": "string",
                    "description": "Load checkpoint for a specific project",
                },
                "session_id": {
                    "type": "string",
                    "description": "Load a specific session by ID",
                },
            },
        },
    },
    {
        "name": "memory_session_list",
        "description": "List recent sessions with their checkpoints and status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {
                    "type": "string",
                    "description": "Filter by project name",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max sessions to return",
                    "default": 10,
                },
            },
        },
    },
    {
        "name": "memory_semantic_search",
        "description": (
            "Search memories using semantic similarity (embeddings)."
            " Finds conceptually related memories even without exact keyword matches."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 10,
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace to search in",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_recover",
        "description": (
            "Recover context from the last session."
            " Returns a formatted summary of where you left off,"
            " including key facts and open tasks."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {
                    "type": "string",
                    "description": "Recover context for a specific project",
                },
            },
        },
    },
    {
        "name": "memory_backfill_embeddings",
        "description": (
            "Generate embeddings for memories stored before semantic search was enabled."
            " Run this once to enable semantic search on existing memories."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to backfill (default: 'default')",
                },
            },
        },
    },
    {
        "name": "memory_cleanup_expired",
        "description": "Permanently remove memories that have passed their expiry date.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to clean up",
                },
            },
        },
    },
    {
        "name": "memory_context",
        "description": (
            "Smart Context Builder — auto-select the most relevant memories"
            " for a given prompt and pack them into a token budget."
            " Combines text search, semantic search, and priority recall."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The prompt or topic to find relevant context for",
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Maximum token budget for the context",
                    "default": 2000,
                    "minimum": 100,
                    "maximum": 16000,
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace to search in",
                },
                "min_importance": {
                    "type": "integer",
                    "description": "Minimum importance threshold for priority recall",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["prompt"],
        },
    },
]
