"""Context Protocol Header

Description:
    Defines an in-memory source snapshot cache.
Purpose:
    Supports deterministic tests and process-local source snapshot reuse.
Architecture:
    - InMemorySnapshotCache: Dict-backed content hash to bytes store.
Relations:
    Used by source tests, verification scripts, and callers that want ephemeral caching.
"""

from __future__ import annotations


class InMemorySnapshotCache:
    """Dict-backed snapshot cache for tests and ephemeral runs."""

    def __init__(self) -> None:
        # Initializes an empty content-hash to bytes store.
        self._store: dict[str, bytes] = {}

    def get(self, content_hash: str) -> bytes | None:
        # Returns cached bytes for the hash, or None on a miss.
        return self._store.get(content_hash)

    def put(self, content_hash: str, data: bytes) -> None:
        # Stores bytes under their content hash.
        self._store[content_hash] = data


__all__ = [
    "InMemorySnapshotCache",
]
