"""SHA-256 content deduplication."""

import hashlib


def content_hash(text: str) -> str:
    """Return the first 16 hex characters of the SHA-256 digest of *text*."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]
