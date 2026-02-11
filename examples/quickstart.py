"""Engram Quickstart — 5 lines to persistent agent memory."""

from engram import Memory

# 1. Create a memory instance (SQLite, zero config)
mem = Memory()

# 2. Store memories
mem.store("User prefers Python over JavaScript", type="preference", importance=8)
mem.store("Project uses FastAPI for the backend", type="fact", importance=7, tags=["stack"])
mem.store("Fixed import error by adding __init__.py", type="error_fix", importance=6)

# 3. Search
results = mem.search("programming language")
for r in results:
    print(f"[{r.match_type}] {r.memory.content} (score: {r.score:.2f})")

# 4. Recall high-priority context
context = mem.recall(min_importance=7)
print(f"\n--- Priority Context ({len(context)} memories) ---")
for entry in context:
    print(f"  [{entry.memory_type.value}] {entry.content}")

# 5. Stats
print(f"\n--- Stats ---")
print(mem.stats())
