# ENGRAM

**Memory that sticks. For every AI agent.**

Universal memory layer for AI agents — persistent, searchable, zero-config.

```python
from engram import Memory

mem = Memory()
mem.store("User prefers Python", type="preference", importance=8)
results = mem.search("programming language")
context = mem.recall(limit=10)
```

## Features

- **Zero config** — `pip install engram-core` and go. SQLite out of the box, no external services.
- **5-line API** — Store, search, recall. That's it.
- **MCP Server** — First-class Model Context Protocol integration for Claude Code and other MCP clients.
- **REST API** — FastAPI server with WebSocket real-time updates.
- **Multi-agent** — Namespace isolation + cross-namespace search for agent teams.
- **Privacy-first** — Runs 100% locally. Your data never leaves your machine.
- **Smart dedup** — SHA-256 content hashing prevents duplicate memories.
- **Full-text search** — SQLite FTS5 for fast, typo-tolerant search.
- **Optional embeddings** — Plug in `sentence-transformers` for semantic search.
- **Memory decay** — Automatic forgetting curve for stale memories.

## Installation

```bash
pip install engram-core
```

With optional extras:

```bash
pip install engram-core[server]      # REST API + WebSocket
pip install engram-core[mcp]         # MCP server
pip install engram-core[embeddings]  # Semantic search
pip install engram-core[all]         # Everything
```

## Quick Start

### Python SDK

```python
from engram import Memory

mem = Memory()

# Store
mem.store("User prefers dark mode", type="preference", importance=8)
mem.store("Fixed bug by adding null check", type="error_fix", importance=7)

# Search
results = mem.search("dark mode")
for r in results:
    print(f"{r.memory.content} (score: {r.score:.2f})")

# Recall priority context
for entry in mem.recall(min_importance=7):
    print(f"[{entry.memory_type.value}] {entry.content}")

# Multi-agent namespaces
agent1 = Memory(namespace="researcher")
agent2 = Memory(namespace="coder")
```

### REST API

```bash
# Start server
engram-server

# Store
curl -X POST http://localhost:8100/v1/memories \
  -H "Content-Type: application/json" \
  -d '{"content": "Important fact", "importance": 8}'

# Search
curl -X POST http://localhost:8100/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "fact"}'
```

### MCP Server (Claude Code)

Add to your MCP config:

```json
{
  "mcpServers": {
    "engram": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/engram"
    }
  }
}
```

**Want automatic memory recall?** Check out the [Claude Code Hook example](examples/claude-code-hook/) — every new session starts with your important memories pre-loaded, zero manual steps.

### Docker

```bash
docker compose -f docker/docker-compose.yml up
```

## Comparison

| Feature | Engram | Mem0 | Letta | Zep |
|---------|--------|------|-------|-----|
| Self-hosted (Zero Infra) | SQLite out-of-box | Cloud-only | Complex setup | Graph DB needed |
| pip install + 5 lines | Yes | ~10 lines + API key | ~20 lines setup | SDK + config |
| MCP Server | First-class | No | No | No |
| Open Source | MIT | Partial | Apache 2.0 | BSL |
| Multi-Agent Namespaces | Native | User/Session/Agent | Single Agent | User-level |
| Privacy-First | Local by default | Cloud by default | Local possible | Cloud-focused |
| Cost | Free (self-hosted) | $0.01+/memory | Free | Enterprise pricing |

## Community

- [Discord](https://discord.gg/Kba2bGbZt5) — Chat, support, feature requests
- [GitHub Issues](https://github.com/engram-memory/engram/issues) — Bug reports & feature requests
- [Email](mailto:support@engram-ai.dev) — support@engram-ai.dev

## License

MIT
