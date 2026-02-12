# Auto Memory Recall — Claude Code Hook

**Give Claude Code automatic memory.** Every new session starts with your most important memories pre-loaded — no manual steps needed.

## The Problem

Engram stores memories perfectly, but Claude Code starts every session with a blank slate. You have to manually recall context every time. That's like having a brain that records everything but can't remember anything on its own.

## The Solution

A **SessionStart hook** that fires automatically when you open Claude Code and injects your high-importance memories into the conversation context.

```
You start Claude Code
    ↓
Hook fires automatically
    ↓
Queries Engram for important memories (importance >= 8)
    ↓
Injects them as session context
    ↓
Claude knows who you are, what you're working on, and what happened last time
```

## Setup (2 minutes)

### 1. Copy the hook script

```bash
mkdir -p ~/.claude/hooks
cp auto_memory_recall.py ~/.claude/hooks/
chmod +x ~/.claude/hooks/auto_memory_recall.py
```

### 2. Add hook config to `~/.claude/settings.json`

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|compact|clear",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/auto_memory_recall.py",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

### 3. Store some memories

```python
from engram import Memory

mem = Memory()
mem.store("User prefers concise responses", type="preference", importance=9)
mem.store("Project uses FastAPI + SQLite", type="fact", importance=8)
mem.store("Fixed auth bug by adding token refresh", type="error_fix", importance=8)
```

### 4. Start Claude Code

```bash
claude
```

You'll see your memories automatically injected:

```
# Auto-Memory Recall (2026-02-12 10:22)
**Project:** my-project

## Engram Memory (auto-recalled)
- [preference] User prefers concise responses
- [fact] Project uses FastAPI + SQLite
- [error_fix] Fixed auth bug by adding token refresh
```

## How It Works

| Event | Hook fires? | Why |
|-------|------------|-----|
| New session (`startup`) | Yes | Fresh start, needs context |
| After `/clear` (`clear`) | Yes | Context was cleared |
| After compaction (`compact`) | Yes | Old context compressed |
| Resume (`resume`) | No | Context still present |

The hook:
1. Reads JSON input from stdin (Claude Code provides session metadata)
2. Queries Engram for memories with `importance >= 8`
3. Truncates long memories to 200 chars
4. Outputs formatted context to stdout
5. Claude Code captures stdout and adds it to the conversation

## Configuration

Edit the constants at the top of `auto_memory_recall.py`:

```python
MIN_IMPORTANCE = 8          # Only recall memories with importance >= this
MAX_MEMORIES = 15           # Maximum memories to inject
MAX_CONTENT_LENGTH = 200    # Truncate long memories
```

## Customization

### Project Detection

The hook detects your project from the working directory. Customize `detect_project()`:

```python
def detect_project(cwd: str) -> str:
    cwd_lower = cwd.lower()
    if "my-api" in cwd_lower:
        return "backend"
    elif "my-frontend" in cwd_lower:
        return "frontend"
    return os.path.basename(cwd)
```

### Multiple Memory Sources

You can extend the hook to combine Engram with other sources (session checkpoints, project-specific databases, etc.). See the `main()` function for the pattern.

## Requirements

- Claude Code with hooks support
- Engram installed (`pip install engram-core`) or just the SQLite database at `~/.engram/memory.db`
- Python 3.10+

## What's Next

In a future Engram release, this will be a single command:

```bash
engram install-hook  # Coming in v0.3
```
