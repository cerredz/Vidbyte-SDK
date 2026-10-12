"""Context Protocol Header

Description:
    Defines the default HTTP source fetcher.
Purpose:
    Wraps the SDK's existing SyncHttpTransport with SourceFetchError normalization.
Architecture:
    - HttpFetcher: Blocking GET fetcher using SyncHttpTransport.request_bytes.
Relations:
    Used by Source as its default fetcher.
"""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlparse

from vidbyte.lib.dataclasses.sources import FetchResponse
from vidbyte.lib.errors import ProviderRequestError, SourceFetchError


def _header(headers: Mapping[str, str], name: str) -> str | None:
    # Case-insensitive header lookup.
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None


class HttpFetcher:
    """Default fetcher wrapping SyncHttpTransport.request_bytes."""

    def __init__(self, *, timeout_seconds: float = 30.0, user_agent: str = "vidbyte-sdk-sources/0.1") -> None:
        # Stores request configuration; transport and httpx are imported lazily.
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent

    def fetch(self, url: str) -> FetchResponse:
        # Performs a blocking GET and normalizes provider failures to SourceFetchError.
        from vidbyte.lib.http.transport import SyncHttpTransport

        # @intent http-fetcher-refuses-non-http-schemes
        # Refuse anything but http/https before any request, because the transport would
        # otherwise open file:// paths or fail on a missing scheme with a non-fetch error.
        scheme = urlparse(url).scheme.lower()
        if scheme not in ("http", "https"):
            raise SourceFetchError("Only http and https URLs can be fetched.", details={"url": url, "scheme": scheme})
        transport = SyncHttpTransport()
        try:
            response = transport.request_bytes(
                method="GET",
                url=url,
                headers={"user-agent": self._user_agent},
                timeout_seconds=self._timeout_seconds,
            )
        except ProviderRequestError as exc:
            raise SourceFetchError(
                "Failed to fetch remote artifact.",
                details={"url": url, "status_code": exc.status_code, "excerpt": exc.response_excerpt},
            ) from exc
        raw = response.raw_bytes if response.raw_bytes is not None else response.body.encode("utf-8")
        return FetchResponse(status_code=response.status_code, body_bytes=raw, content_type=_header(response.headers, "content-type"), url=response.url)


__all__ = [
    "HttpFetcher",
]
