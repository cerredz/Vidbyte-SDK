"""Context Protocol Header

Description:
    Compatibility exports for source fetcher and cache contracts.
Purpose:
    Preserves draft import paths while the authoritative implementation lives under
    vidbyte.sources.fetches, vidbyte.sources.cache, and vidbyte.sources.security.
Architecture:
    - Re-exports fetchers, caches, UrlAllowlist, FetchResponse, and sha256_hex.
Relations:
    New code should import from vidbyte.sources.fetches or vidbyte.sources.cache directly.
"""

from __future__ import annotations

from vidbyte.sources.cache import (
    FileSnapshotCache,
    InMemorySnapshotCache,
    NullSnapshotCache,
    SnapshotCache,
)
from vidbyte.sources.fetches import (
    ChainedFetcher,
    Fetcher,
    FetchResponse,
    FileFetcher,
    HttpFetcher,
    InMemoryFetcher,
    sha256_hex,
)
from vidbyte.sources.security import UrlAllowlist

__all__ = [
    "ChainedFetcher",
    "FetchResponse",
    "Fetcher",
    "FileFetcher",
    "FileSnapshotCache",
    "HttpFetcher",
    "InMemoryFetcher",
    "InMemorySnapshotCache",
    "NullSnapshotCache",
    "SnapshotCache",
    "UrlAllowlist",
    "sha256_hex",
]
