from __future__ import annotations

import hashlib
import secrets


def generate_key() -> str:
    """Generate a new API key with ml_ prefix + 32 hex chars."""
    return f"ml_{secrets.token_hex(16)}"


def hash_key(key: str) -> str:
    """SHA-256 hash of a key for storage."""
    return hashlib.sha256(key.encode()).hexdigest()


def key_prefix(key: str) -> str:
    """Extract display prefix (first 8 chars) from a key."""
    return key[:8] + "..."


def verify_key(key: str, key_hash: str) -> bool:
    """Check if a key matches a stored hash."""
    return hash_key(key) == key_hash
