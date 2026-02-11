"""Password hashing using PBKDF2-SHA256 (stdlib, zero dependencies)."""

from __future__ import annotations

import hashlib
import os


_ITERATIONS = 600_000  # OWASP recommended minimum for PBKDF2-SHA256
_SALT_LENGTH = 32
_HASH_LENGTH = 32


def hash_password(password: str) -> str:
    """Hash a password. Returns 'salt_hex:hash_hex'."""
    salt = os.urandom(_SALT_LENGTH)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS, dklen=_HASH_LENGTH)
    return f"{salt.hex()}:{dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored hash."""
    try:
        salt_hex, hash_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS, dklen=_HASH_LENGTH)
        return dk == expected
    except (ValueError, AttributeError):
        return False
