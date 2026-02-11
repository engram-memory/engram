"""Engram exceptions."""


class EngramError(Exception):
    """Base exception for all Engram errors."""


class MemoryNotFound(EngramError):
    """Raised when a memory ID does not exist."""

    def __init__(self, memory_id: int):
        self.memory_id = memory_id
        super().__init__(f"Memory #{memory_id} not found")


class DuplicateMemory(EngramError):
    """Raised when storing a memory that already exists (content hash collision)."""

    def __init__(self, content_hash: str):
        self.content_hash = content_hash
        super().__init__(f"Duplicate memory (hash={content_hash})")


class StorageError(EngramError):
    """Raised on storage backend failures (I/O, corruption, etc.)."""


class ConfigError(EngramError):
    """Raised on invalid configuration."""
