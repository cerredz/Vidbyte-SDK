"""Context Protocol Header

Description:
    Defines a no-op source snapshot cache.
Purpose:
    Provides an explicit cache object for callers that want to disable cache behavior while
    still satisfying the SnapshotCache protocol.
Architecture:
    - NullSnapshotCache: Always misses and ignores writes.
Relations:
    Optional cache implementation re-exported from vidbyte.sources.cache.
"""

from __future__ import annotations


class NullSnapshotCache:
    """No-op snapshot cache."""

    def get(self, content_hash: str) -> bytes | None:
        # Always misses.
        return None

    def put(self, content_hash: str, data: bytes) -> None:
        # Intentionally ignores writes.
        del content_hash, data


__all__ = [
    "NullSnapshotCache",
]
