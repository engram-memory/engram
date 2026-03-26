"""Shared test configuration — auto-detect CI and use fake embeddings."""

import os

# On CI (no Ollama available), override embedding provider to "fake"
# This gives tests deterministic embeddings without requiring a GPU
if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
    os.environ.setdefault("ENGRAM_EMBEDDING_PROVIDER", "fake")
