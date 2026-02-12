#!/usr/bin/env python3
"""
Auto Memory Recall — Claude Code SessionStart Hook for Engram.

Automatically injects your most important memories into every new Claude Code
session. No manual steps needed — just start a session and your AI remembers.

Setup:
    1. Copy this file to ~/.claude/hooks/auto-memory-recall.py
    2. Add the hook config to ~/.claude/settings.json (see README.md)
    3. Start a new Claude Code session — memories are injected automatically

How it works:
    - Fires on SessionStart (startup, compact, clear)
    - Skips on resume (context is still present)
    - Queries Engram for high-importance memories (>= 8)
    - Detects project from working directory
    - Outputs context to stdout → Claude sees it as session context
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

# Try to use Engram SDK first, fall back to direct SQLite
USE_SDK = False
try:
    from engram import Memory
    USE_SDK = True
except ImportError:
    import sqlite3


# === Configuration ===
MIN_IMPORTANCE = 8          # Only recall memories with importance >= this
MAX_MEMORIES = 15           # Maximum memories to inject
MAX_CONTENT_LENGTH = 200    # Truncate long memories
ENGRAM_DB = Path.home() / ".engram" / "memory.db"


def recall_via_sdk(namespace: str = "default") -> str:
    """Recall memories using the Engram Python SDK."""
    mem = Memory(namespace=namespace)
    entries = mem.recall(min_importance=MIN_IMPORTANCE, limit=MAX_MEMORIES)

    if not entries:
        return ""

    lines = ["## Engram Memory (auto-recalled)"]
    for entry in entries:
        content = entry.content
        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH] + "..."
        mtype = entry.memory_type.value if hasattr(entry.memory_type, 'value') else str(entry.memory_type)
        lines.append(f"- [{mtype}] {content}")

    return "\n".join(lines)


def recall_via_sqlite() -> str:
    """Recall memories directly from Engram's SQLite database."""
    if not ENGRAM_DB.exists():
        return ""

    try:
        with sqlite3.connect(ENGRAM_DB) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT content, importance, memory_type, tags
                FROM memories
                WHERE importance >= ?
                ORDER BY importance DESC, access_count DESC, created_at DESC
                LIMIT ?
            """, (MIN_IMPORTANCE, MAX_MEMORIES)).fetchall()

            if not rows:
                return ""

            lines = ["## Engram Memory (auto-recalled)"]
            for row in rows:
                content = row['content']
                if len(content) > MAX_CONTENT_LENGTH:
                    content = content[:MAX_CONTENT_LENGTH] + "..."
                mtype = row['memory_type'] or "fact"
                lines.append(f"- [{mtype}] {content}")

            # Update access counts
            conn.execute("""
                UPDATE memories
                SET access_count = access_count + 1, accessed_at = CURRENT_TIMESTAMP
                WHERE importance >= ?
            """, (MIN_IMPORTANCE,))
            conn.commit()

            return "\n".join(lines)
    except Exception as e:
        return f"<!-- Engram recall error: {e} -->"


def detect_project(cwd: str) -> str:
    """Detect project name from working directory. Customize for your setup."""
    if not cwd:
        return None
    cwd_lower = cwd.lower()
    # Add your project detection patterns here:
    # if "myproject" in cwd_lower:
    #     return "myproject"
    return os.path.basename(cwd)


def main():
    """Main entry point — called by Claude Code SessionStart hook."""
    # Read hook input from stdin
    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, Exception):
        hook_input = {}

    source = hook_input.get("source", "startup")
    cwd = hook_input.get("cwd", os.getcwd())

    # Only fire on startup, compact, clear — not on resume
    if source not in ("startup", "compact", "clear"):
        sys.exit(0)

    # Detect project
    project = detect_project(cwd)

    # Build output
    parts = []
    parts.append(f"# Auto-Memory Recall ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    if project:
        parts.append(f"**Project:** {project}")

    # Recall memories
    if USE_SDK:
        memories = recall_via_sdk()
    else:
        memories = recall_via_sqlite()

    if memories:
        parts.append(memories)
        print("\n".join(parts))
    else:
        print(f"# Session started ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
        print("No stored memories found. Use Engram to store important facts!")


if __name__ == "__main__":
    main()
