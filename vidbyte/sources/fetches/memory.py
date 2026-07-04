"""Context Protocol Header

Description:
    Defines an in-memory source fetcher.
Purpose:
    Provides deterministic offline fetch responses for tests, examples, and scripted loads.
Architecture:
    - InMemoryFetcher: URL-to-bytes/FetchResponse mapping.
Relations:
    Used by source unit tests and verification scripts.
"""

from __future__ import annotations

from collections.abc import Mapping

from vidbyte.lib.dataclasses.sources import FetchResponse
from vidbyte.lib.errors import SourceFetchError


class InMemoryFetcher:
    """Deterministic offline fetcher backed by an in-memory URL mapping."""

    def __init__(self, responses: Mapping[str, bytes | FetchResponse]) -> None:
        # Stores a copy so caller mutation cannot affect future fetches.
        self._responses = dict(responses)

    def fetch(self, url: str) -> FetchResponse:
        # Returns the mapped response, wrapping raw bytes as a 200 text/markdown response.
        if url not in self._responses:
            raise SourceFetchError("No in-memory response registered for URL.", details={"url": url, "status_code": 404})
        value = self._responses[url]
        if isinstance(value, FetchResponse):
            return value
        return FetchResponse(status_code=200, body_bytes=value, content_type="text/markdown")


__all__ = [
    "InMemoryFetcher",
]
