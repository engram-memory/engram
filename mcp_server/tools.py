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
                    "description": "Memory type: fact, preference, decision, error_fix, pattern, workflow, summary, custom",
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
