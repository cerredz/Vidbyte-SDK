"""Context Protocol Header

Description:
    Defines an on-disk source snapshot cache.
Purpose:
    Supports vendored content-addressed snapshots with one file per content hash.
Architecture:
    - FileSnapshotCache: Atomic put and byte read under a configured root directory.
Relations:
    Used by source cache tests and callers that want reusable local snapshots.
"""

from __future__ import annotations

import os
from pathlib import Path


class FileSnapshotCache:
    """Vendored on-disk snapshot cache: one file per content hash under a root directory."""

    def __init__(self, root: str | Path) -> None:
        # Records the cache root; the directory is created lazily on the first put.
        self._root = Path(root)

    def get(self, content_hash: str) -> bytes | None:
        # Returns snapshot bytes for the hash, or None when absent.
        path = self._root / f"{content_hash}.bin"
        if not path.exists():
            return None
        return path.read_bytes()

    def put(self, content_hash: str, data: bytes) -> None:
        # Writes the snapshot atomically to avoid torn reads.
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / f"{content_hash}.bin"
        tmp = self._root / f"{content_hash}.bin.tmp"
        tmp.write_bytes(data)
        os.replace(tmp, path)


__all__ = [
    "FileSnapshotCache",
]
