# ENGRAM

[![PyPI version](https://img.shields.io/pypi/v/engram-core?color=6B46C1&style=flat-square)](https://pypi.org/project/engram-core/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-159%20passing-brightgreen?style=flat-square)](#)
[![Python](https://img.shields.io/pypi/pyversions/engram-core?style=flat-square&color=06B6D4)](https://pypi.org/project/engram-core/)

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

### Core

- **Zero config** — `pip install engram-core` and go. SQLite out of the box, no external services.
- **5-line API** — Store, search, recall, delete, stats. That's it.
- **Full-text search** — SQLite FTS5 for fast, typo-tolerant search.
- **Smart dedup** — SHA-256 content hashing prevents duplicate memories.
- **Memory TTL** — Set expiry on memories (`ttl_days=30`). Auto-cleanup removes expired entries.
- **Privacy-first** — Runs 100% locally. Your data never leaves your machine.

### Search & Retrieval

- **Semantic search** — Plug in `sentence-transformers` for embedding-based similarity search. Find conceptually related memories even without exact keyword matches.
- **Smart Context Builder** — Automatically selects the most relevant memories for a given prompt within a token budget. Combines text search, semantic search, and priority recall.
- **Memory Links & Graph** — Create directed relationships between memories (`caused_by`, `depends_on`, `related`, etc.) and traverse the knowledge graph with BFS.

### Agent Infrastructure

- **MCP Server** — First-class Model Context Protocol integration for Claude Code and other MCP clients.
- **REST API** — FastAPI server on port 8100 with full CRUD, search, and WebSocket real-time events.
- **Multi-agent** — Namespace isolation + cross-namespace search for agent teams.
- **Agent AutoSave** — Trigger-based automatic checkpointing. Configure by message count, time interval, or RAM threshold. Delta tracking saves only what changed.
- **Session Management** — Save/load/recover session checkpoints with key facts, open tasks, and project context.
- **Synapse Message Bus** — Real-time pub/sub channels for multi-agent communication.

### Cloud API

- **Managed hosting** — European servers (Germany), zero setup, 7-day free trial.
- **Tier system** — Free (self-hosted, unlimited) / Pro (cloud, 250K memories) / Enterprise.
- **Stripe billing** — Secure payments, 13+ payment methods, cancel anytime.

## Installation

```bash
pip install engram-core
```

With optional extras:

```bash
pip install engram-core[server]      # REST API + WebSocket
pip install engram-core[synapse]     # Synapse message bus
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
mem.store("Fixed bug by adding null check", type="error_fix", importance=7, ttl_days=90)

# Search
results = mem.search("dark mode")
for r in results:
    print(f"{r.memory.content} (score: {r.score:.2f})")

# Semantic search (requires embeddings extra)
results = mem.search("UI theme settings", semantic=True)

# Smart context — auto-select relevant memories within token budget
ctx = mem.context("User is asking about their editor preferences", max_tokens=500)
print(ctx.context)  # Ready-to-inject context string

# Recall priority context
for entry in mem.recall(min_importance=7):
    print(f"[{entry.memory_type.value}] {entry.content}")

# Memory links
bug_id = mem.store("Login fails on Safari", type="error_fix", importance=9)
fix_id = mem.store("Added WebKit prefix to CSS", type="error_fix", importance=8)
mem.link(bug_id, fix_id, "caused_by")

# Traverse the knowledge graph
graph = mem.graph(bug_id, max_depth=2)

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

# Smart context
curl -X POST http://localhost:8100/v1/context \
  -H "Content-Type: application/json" \
  -d '{"prompt": "current task", "max_tokens": 500}'
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
| Semantic Search | FTS5 + Embeddings | Embeddings only | Embeddings | Embeddings |
| Memory Links / Graph | Native | No | No | Yes |
| Context Builder | Token-budgeted | No | No | No |
| AutoSave / Checkpoints | Trigger-based | No | No | No |
| Memory TTL / Expiry | Native | No | No | Yes |
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
