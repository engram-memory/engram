"""Example: Using Engram as MCP server with Claude Code.

To configure, add to ~/.claude/settings.json or .mcp.json:

{
  "mcpServers": {
    "engram": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/engram"
    }
  }
}

Then Claude Code can use these tools:
- memory_store: Save important facts, decisions, preferences
- memory_search: Find relevant memories
- memory_recall: Get priority context for injection
- memory_delete: Remove outdated memories
- memory_stats: Check memory statistics
"""

# You can also use Engram programmatically alongside Claude API:

from engram import Memory

mem = Memory(namespace="claude-assistant")

# Before each conversation, inject priority context
context = mem.recall(min_importance=7)
system_prompt_addition = "\n".join(f"- [{e.memory_type.value}] {e.content}" for e in context)
print("Context to inject into system prompt:")
print(system_prompt_addition or "(no memories yet)")

# After conversation, store key facts
mem.store("User's project is called Engram", type="fact", importance=8)
mem.store("User prefers concise responses", type="preference", importance=9)
