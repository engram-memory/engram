"""Multi-agent memory sharing via namespaces."""

from engram import Memory

# Agent 1: Research agent
researcher = Memory(namespace="researcher")
researcher.store("GPT-4 has 1.76T parameters (rumored)", type="fact", importance=7)
researcher.store("Claude uses constitutional AI training", type="fact", importance=8)

# Agent 2: Coding agent
coder = Memory(namespace="coder")
coder.store("Use async/await for all I/O operations", type="pattern", importance=9)
coder.store("SQLite FTS5 is faster than LIKE queries", type="fact", importance=7)

# Each agent sees only its own memories
print("Researcher memories:", len(researcher.list()))
print("Coder memories:", len(coder.list()))

# Cross-namespace search: coder can query researcher's findings
shared = Memory(namespace="researcher")
results = shared.search("Claude")
print(f"\nCross-namespace search found {len(results)} results:")
for r in results:
    print(f"  {r.memory.content}")
