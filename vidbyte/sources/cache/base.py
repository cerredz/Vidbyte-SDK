"""Context Protocol Header

Description:
    Defines the protocol for source snapshot caches.
Purpose:
    Provides the content-addressed cache interface used by Source without coupling loaders
    to memory, disk, or null-cache implementations.
Architecture:
    - SnapshotCache: get/put protocol keyed by content hash.
Relations:
    Implemented by memory, file, and null source caches.
"""

from __future__ import annotations

from typing import Protocol


class SnapshotCache(Protocol):
    """Injectable content-addressed snapshot store keyed by SHA-256 hash."""

    def get(self, content_hash: str) -> bytes | None: ...

    def put(self, content_hash: str, data: bytes) -> None: ...


__all__ = [
    "SnapshotCache",
]
