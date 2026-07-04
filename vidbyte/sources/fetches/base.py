"""Context Protocol Header

Description:
    Defines the protocol for source fetchers.
Purpose:
    Provides the single byte-fetching interface used by Source loaders without coupling
    loaders to HTTP, test doubles, files, or fallback strategies.
Architecture:
    - Fetcher: Protocol returning FetchResponse for a URL-like location.
Relations:
    Implemented by memory, HTTP, file, and chained source fetchers.
"""

from __future__ import annotations

from typing import Protocol

from vidbyte.lib.dataclasses.sources import FetchResponse


class Fetcher(Protocol):
    """Injectable byte-level fetch seam for artifact sources."""

    def fetch(self, url: str) -> FetchResponse:
        """Fetch the URL and return raw bytes, or raise SourceFetchError."""


__all__ = [
    "Fetcher",
]
