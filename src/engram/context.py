"""Smart Context Builder — auto-select relevant memories for a prompt."""

from __future__ import annotations

from dataclasses import dataclass, field

from engram.core.types import MemoryEntry, SearchResult
from engram.storage.sqlite_backend import SQLiteBackend


@dataclass
class ContextResult:
    """Result from the context builder."""

    context: str
    memories_used: int
    token_count: int
    truncated: bool
    memory_ids: list[int] = field(default_factory=list)


def estimate_tokens(text: str) -> int:
    """Approximate token count (~4 chars/token for English)."""
    return max(1, len(text) // 4)


def _format_entry(entry: MemoryEntry) -> str:
    """Format a single memory as a compact line."""
    line = f"[{entry.memory_type.value}|imp:{entry.importance}] {entry.content}"
    if entry.tags:
        line += f"\n  tags: {', '.join(entry.tags)}"
    return line


def build_context(
    backend: SQLiteBackend,
    embedder: object | None,
    prompt: str,
    *,
    max_tokens: int = 2000,
    namespace: str = "default",
    min_importance: int = 3,
) -> ContextResult:
    """Build a token-budgeted context string from the most relevant memories.

    Combines FTS search, semantic search, and priority recall into a single
    deduplicated, ranked, and formatted context block.
    """
    candidates: dict[int, tuple[MemoryEntry, float]] = {}

    # --- 1. Gather candidates from multiple sources ---

    # FTS search
    if prompt.strip():
        fts_results: list[SearchResult] = backend.search_text(prompt, namespace=namespace, limit=50)
        _merge_search_results(candidates, fts_results, source="fts")

    # Semantic search (if embedder available)
    if prompt.strip() and embedder is not None:
        vec = embedder.embed(prompt)
        sem_results: list[SearchResult] = backend.search_vector(vec, namespace=namespace, limit=50)
        _merge_search_results(candidates, sem_results, source="semantic")

    # Priority recall (always — ensures high-importance memories are included)
    priority_entries: list[MemoryEntry] = backend.get_priority_memories(
        namespace=namespace, limit=30, min_importance=min_importance
    )
    for entry in priority_entries:
        if entry.id is None:
            continue
        importance_score = entry.importance / 10.0
        if entry.id in candidates:
            _, existing_score = candidates[entry.id]
            if importance_score > existing_score:
                candidates[entry.id] = (entry, importance_score)
        else:
            candidates[entry.id] = (entry, importance_score)

    # --- 2. Rank by combined score ---
    ranked = sorted(candidates.values(), key=lambda x: x[1], reverse=True)

    # --- 3. Accumulate within token budget ---
    header = ""
    header_tokens = 0
    selected: list[tuple[MemoryEntry, str]] = []
    total_tokens = 0

    for entry, _score in ranked:
        formatted = _format_entry(entry)
        entry_tokens = estimate_tokens(formatted + "\n")
        if total_tokens + entry_tokens + header_tokens > max_tokens and selected:
            # Build header now that we know count
            header = f"## Relevant Context ({len(selected)} memories, ~{total_tokens} tokens)\n\n"
            header_tokens = estimate_tokens(header)
            if total_tokens + entry_tokens + header_tokens > max_tokens:
                break
        total_tokens += entry_tokens
        selected.append((entry, formatted))

    # --- 4. Format output ---
    if not selected:
        return ContextResult(
            context="",
            memories_used=0,
            token_count=0,
            truncated=False,
            memory_ids=[],
        )

    header = f"## Relevant Context ({len(selected)} memories, ~{total_tokens} tokens)\n\n"
    header_tokens = estimate_tokens(header)
    body = "\n".join(fmt for _, fmt in selected)
    full_context = header + body
    final_tokens = header_tokens + total_tokens
    truncated = len(selected) < len(ranked)

    return ContextResult(
        context=full_context,
        memories_used=len(selected),
        token_count=final_tokens,
        truncated=truncated,
        memory_ids=[e.id for e, _ in selected if e.id is not None],
    )


def _merge_search_results(
    candidates: dict[int, tuple[MemoryEntry, float]],
    results: list[SearchResult],
    source: str,
) -> None:
    """Merge search results into candidates dict, keeping highest score per ID."""
    if not results:
        return

    for r in results:
        if r.memory.id is None:
            continue

        # Normalize score to 0-1
        if source == "semantic":
            norm_score = max(0.0, min(1.0, r.score))
        else:
            # FTS rank is negative (closer to 0 = better). Normalize to 0-1.
            norm_score = max(0.0, min(1.0, 1.0 / (1.0 + abs(r.score))))

        # Combined: 60% relevance + 40% importance
        importance_norm = r.memory.importance / 10.0
        combined = 0.6 * norm_score + 0.4 * importance_norm

        if r.memory.id in candidates:
            _, existing = candidates[r.memory.id]
            if combined > existing:
                candidates[r.memory.id] = (r.memory, combined)
        else:
            candidates[r.memory.id] = (r.memory, combined)
