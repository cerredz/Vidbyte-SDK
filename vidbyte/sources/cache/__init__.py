"""Context Protocol Header

Description:
    Public cache package for artifact sources.
Purpose:
    Groups source snapshot cache interfaces and implementations while keeping each concrete
    cache in its own module.
Architecture:
    - SnapshotCache protocol.
    - In-memory, file, and null cache implementations.
Relations:
    Re-exported by vidbyte.sources and consumed by Source.
"""

from __future__ import annotations

from vidbyte.sources.cache.base import SnapshotCache
from vidbyte.sources.cache.file import FileSnapshotCache
from vidbyte.sources.cache.memory import InMemorySnapshotCache
from vidbyte.sources.cache.null import NullSnapshotCache

__all__ = [
    "FileSnapshotCache",
    "InMemorySnapshotCache",
    "NullSnapshotCache",
    "SnapshotCache",
]
