"""Search utilities shared across backends."""

from __future__ import annotations


def sanitize_fts_query(raw: str, max_words: int = 10) -> str | None:
    """Turn *raw* user input into a safe FTS5 MATCH expression.

    Returns ``None`` when the input is empty or has no usable words.
    """
    cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in raw)
    words = cleaned.split()[:max_words]
    if not words:
        return None
    return " OR ".join(f'"{w}"' for w in words)
