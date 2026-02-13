"""Engram — Memory that sticks. For every AI agent."""

from engram.client import Memory
from engram.config import EngramConfig
from engram.core.types import MemoryEntry, MemoryType, SearchResult

__version__ = "0.3.0"
__all__ = ["Memory", "EngramConfig", "MemoryEntry", "MemoryType", "SearchResult"]
