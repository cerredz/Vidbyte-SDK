"""Context Protocol Header

Description:
    Public fetcher package for artifact sources.
Purpose:
    Groups source fetch interfaces and implementations while keeping each concrete fetcher
    in its own module.
Architecture:
    - Fetcher protocol, FetchResponse dataclass, content hash helper.
    - HTTP, in-memory, file, and chained fetcher implementations.
Relations:
    Re-exported by vidbyte.sources and consumed by Source.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.sources import FetchResponse
from vidbyte.sources.fetches.base import Fetcher
from vidbyte.sources.fetches.chained import ChainedFetcher
from vidbyte.sources.fetches.file import FileFetcher
from vidbyte.sources.fetches.hash import sha256_hex
from vidbyte.sources.fetches.http import HttpFetcher
from vidbyte.sources.fetches.memory import InMemoryFetcher

__all__ = [
    "ChainedFetcher",
    "FetchResponse",
    "Fetcher",
    "FileFetcher",
    "HttpFetcher",
    "InMemoryFetcher",
    "sha256_hex",
]
