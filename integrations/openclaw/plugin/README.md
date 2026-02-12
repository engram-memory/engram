# Engram for OpenClaw

**Local-first persistent memory for OpenClaw agents. Your data stays yours.**

Unlike cloud-based memory solutions, Engram stores everything on your machine. No API keys to third-party services, no data leaving your network, no subscription required for basic use.

## Why Engram?

| Feature | Cloud Memory (Mem0 etc.) | Engram |
|---------|-------------------------|--------|
| Data location | Their servers | **Your machine** |
| Offline support | No | **Yes** |
| API keys needed | Yes (+ OpenAI key) | **No** |
| Privacy | Trust them | **Zero trust needed** |
| Setup time | Sign up, get keys | **pip install, done** |
| Cost | Pay per API call | **Free (local)** |

After the [Moltbook data breach](https://www.wiz.io/blog/exposed-moltbook-database-reveals-millions-of-api-keys) exposed 1.5M API keys, you might want to think twice about where your agent's memories live.

## Quick Start

### 1. Install Engram

```bash
pip install engram-core[server]
```

### 2. Start the server

```bash
engram-server
# Runs on http://localhost:8100
```

### 3. Install the OpenClaw plugin

```bash
# From npm (when published)
openclaw plugins install @engram/openclaw

# Or manually: copy to ~/.openclaw/skills/engram-memory/
```

### 4. Configure (optional)

Add to your `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "entries": {
      "engram-memory": {
        "enabled": true,
        "config": {
          "host": "http://localhost:8100",
          "namespace": "openclaw",
          "autoRecall": true,
          "autoCapture": true,
          "minImportance": 5,
          "maxRecallResults": 10
        }
      }
    }
  }
}
```

All settings are optional — defaults work out of the box.

## How It Works

### Auto-Recall (before each response)

When you send a message, Engram searches for relevant memories and injects them into the agent's context. The agent sees what it learned in previous sessions without you having to repeat yourself.

### Auto-Capture (after each response)

After the agent responds, Engram analyzes the conversation for important facts, decisions, and preferences. These are automatically stored with appropriate importance levels.

### Agent Tools

The agent also has direct access to memory tools:

| Tool | Description |
|------|-------------|
| `memory_store` | Explicitly save a memory with type and importance |
| `memory_search` | Search memories by natural language query |
| `memory_recall` | Get highest-priority memories |
| `memory_forget` | Delete a specific memory |
| `memory_stats` | View memory statistics |

## Multi-Agent Isolation

Each agent can use its own namespace:

```json
{
  "config": {
    "namespace": "agent-alice"
  }
}
```

Memories in different namespaces are completely isolated.

## Architecture

```
OpenClaw Agent
    │
    ├── Auto-Recall (pre-response)
    │   └── GET /v1/search → inject context
    │
    ├── Auto-Capture (post-response)
    │   └── POST /v1/memories → store facts
    │
    └── Agent Tools
        └── memory_store / memory_search / memory_recall / memory_forget
    │
    ▼
Engram Server (localhost:8100)
    │
    ▼
SQLite + FTS5 (~/.engram/memory.db)
    │
    ▼
Your Machine. Your Data. Period.
```

## Comparison with Mem0

| | Mem0 | Engram |
|---|---|---|
| Architecture | Cloud-first | **Local-first** |
| Data storage | Their servers | **~/.engram/memory.db** |
| Requires | MEM0_API_KEY + OPENAI_API_KEY | **Nothing** |
| Offline | No | **Yes** |
| Cost | Usage-based pricing | **Free (open source)** |
| Deduplication | Yes | **Yes (SHA-256)** |
| Search | Semantic (cloud) | **FTS5 + Semantic (local)** |
| Sessions | No | **Yes (Pro)** |
| Checkpoints | No | **Yes (Pro)** |

## Requirements

- Python 3.10+ (for Engram server)
- Node.js 18+ (for OpenClaw)
- ~10 MB disk space

## Links

- [Engram on GitHub](https://github.com/engram-memory/engram)
- [Engram on PyPI](https://pypi.org/project/engram-core/)
- [OpenClaw Documentation](https://docs.openclaw.ai)

## License

MIT
