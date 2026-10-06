"""Context Protocol Header

Description:
    Defines source content hashing helpers.
Purpose:
    Keeps the canonical source content hash helper near fetch I/O boundaries.
Architecture:
    - sha256_hex: Lowercase SHA-256 hex digest for raw artifact bytes.
Relations:
    Used by Source pinning, caches, tests, and public source exports.
"""

from __future__ import annotations

import hashlib


def sha256_hex(data: bytes) -> str:
    # Returns the lowercase hex SHA-256 digest of the given bytes.
    return hashlib.sha256(data).hexdigest()


__all__ = [
    "sha256_hex",
]
