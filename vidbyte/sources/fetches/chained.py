"""Context Protocol Header

Description:
    Defines a fallback source fetcher.
Purpose:
    Allows callers to compose common fetch sources, such as memory overrides before HTTP,
    without baking fallback behavior into Source itself.
Architecture:
    - ChainedFetcher: Tries each fetcher in order until one succeeds.
Relations:
    Optional fetcher implementation re-exported from vidbyte.sources.fetches.
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.lib.dataclasses.sources import FetchResponse
from vidbyte.lib.errors import SourceFetchError
from vidbyte.sources.fetches.base import Fetcher


class ChainedFetcher:
    """Tries a sequence of fetchers in order."""

    def __init__(self, fetchers: Sequence[Fetcher]) -> None:
        # Stores the ordered fallback chain.
        self._fetchers = tuple(fetchers)

    def fetch(self, url: str) -> FetchResponse:
        # Returns the first successful fetch response, or raises the last SourceFetchError.
        last_error: SourceFetchError | None = None
        for fetcher in self._fetchers:
            try:
                return fetcher.fetch(url)
            except SourceFetchError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise SourceFetchError("No source fetchers are configured.", details={"url": url})


__all__ = [
    "ChainedFetcher",
]
