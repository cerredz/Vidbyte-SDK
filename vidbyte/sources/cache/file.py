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

import contextlib
import os
import tempfile
from pathlib import Path


class FileSnapshotCache:
    """Vendored on-disk snapshot cache: one file per content hash under a root directory."""

    def __init__(self, root: str | Path) -> None:
        # Records the cache root; the directory is created lazily on the first put.
        self._root = Path(root)

    def get(self, content_hash: str) -> bytes | None:
        # @intent snapshot-cache-tolerates-concurrent-writers
        # Returns snapshot bytes for the hash, or None when absent or unreadable this instant (a miss).
        try:
            return (self._root / f"{content_hash}.bin").read_bytes()
        except OSError:
            return None

    def put(self, content_hash: str, data: bytes) -> None:
        # @intent snapshot-cache-tolerates-concurrent-writers
        # Content-addressed and shared by concurrent loads: an existing entry already holds these bytes.
        path = self._root / f"{content_hash}.bin"
        if path.exists():
            return
        # Write through a temp file unique to this writer, then replace atomically to avoid torn reads.
        self._root.mkdir(parents=True, exist_ok=True)
        handle, tmp = tempfile.mkstemp(dir=self._root, prefix=f"{content_hash}.", suffix=".tmp")
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(data)
            try:
                os.replace(tmp, path)
            except OSError:
                # Losing the race to another writer of the same hash is success.
                if not path.exists():
                    raise
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.remove(tmp)


__all__ = [
    "FileSnapshotCache",
]
