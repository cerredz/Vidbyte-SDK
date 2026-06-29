"""Context Protocol Header

Description:
    Holds the injectable I/O seams and pure helpers shared by every artifact source.
Purpose:
    Centralizes the only network boundary (the Fetcher), the content-addressed snapshot
    cache, the URL allowlist trust gate, and the canonical content-hash helper, so loaders
    stay deterministic and fully testable offline.
Architecture:
    - sha256_hex: Canonical lowercase hex SHA-256 of raw bytes (the pin hash).
    - FetchResponse: Raw transport result (status, body bytes, content type).
    - Fetcher/InMemoryFetcher/HttpFetcher: Byte-level fetch seam + offline and default impls.
    - SnapshotCache/InMemorySnapshotCache/FileSnapshotCache: Content-addressed snapshot store.
    - UrlAllowlist: Scheme/host gate enforced before any network call.
Relations:
    Consumed by vidbyte.sources.base.Source; wraps vidbyte.lib.http.SyncHttpTransport.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from vidbyte.lib.errors import ProviderRequestError, SourceFetchError, SourceSecurityError


def sha256_hex(data: bytes) -> str:
    # Returns the lowercase hex SHA-256 digest of the given bytes (the canonical pin hash).
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class FetchResponse:
    """Raw transport result: status, body bytes, and optional content type."""

    status_code: int
    body_bytes: bytes
    content_type: str | None = None


def _header(headers: Mapping[str, str], name: str) -> str | None:
    # Case-insensitive header lookup (urllib preserves the server's original casing).
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None


class Fetcher(Protocol):
    """Injectable byte-level fetch seam; the only network boundary of the sources layer."""

    def fetch(self, url: str) -> FetchResponse:
        """Fetch the URL and return its raw bytes, or raise SourceFetchError."""


class InMemoryFetcher:
    """Deterministic offline fetcher backed by an in-memory url->bytes mapping (tests)."""

    def __init__(self, responses: Mapping[str, bytes | FetchResponse]) -> None:
        # Stores a copy of the url->response mapping so external mutation cannot affect fetches.
        self._responses = dict(responses)

    def fetch(self, url: str) -> FetchResponse:
        # Returns the mapped response, wrapping raw bytes as a 200 text/markdown response.
        if url not in self._responses:
            raise SourceFetchError("No in-memory response registered for URL.", details={"url": url, "status_code": 404})
        value = self._responses[url]
        if isinstance(value, FetchResponse):
            return value
        return FetchResponse(status_code=200, body_bytes=value, content_type="text/markdown")


class HttpFetcher:
    """Default fetcher wrapping the existing SyncHttpTransport.request_bytes."""

    def __init__(self, *, timeout_seconds: float = 30.0, user_agent: str = "vidbyte-sdk-sources/0.1") -> None:
        # Stores request configuration; the transport (and httpx) is imported lazily on fetch.
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent

    def fetch(self, url: str) -> FetchResponse:
        # Performs a blocking GET via SyncHttpTransport and normalizes failures to SourceFetchError.
        from vidbyte.lib.http.transport import SyncHttpTransport

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
        return FetchResponse(status_code=response.status_code, body_bytes=raw, content_type=_header(response.headers, "content-type"))


class SnapshotCache(Protocol):
    """Injectable content-addressed snapshot store keyed by SHA-256 hash."""

    def get(self, content_hash: str) -> bytes | None: ...

    def put(self, content_hash: str, data: bytes) -> None: ...


class InMemorySnapshotCache:
    """Dict-backed snapshot cache for tests and ephemeral runs."""

    def __init__(self) -> None:
        # Initializes an empty content-hash -> bytes store.
        self._store: dict[str, bytes] = {}

    def get(self, content_hash: str) -> bytes | None:
        # Returns the cached bytes for the hash, or None on a miss.
        return self._store.get(content_hash)

    def put(self, content_hash: str, data: bytes) -> None:
        # Stores bytes under their content hash (idempotent: identical content overwrites itself).
        self._store[content_hash] = data


class FileSnapshotCache:
    """Vendored on-disk snapshot cache: one file per content hash under a root directory."""

    def __init__(self, root: str | Path) -> None:
        # Records the cache root; the directory is created lazily on the first put.
        self._root = Path(root)

    def get(self, content_hash: str) -> bytes | None:
        # Returns the snapshot bytes for the hash, or None when the file is absent.
        path = self._root / f"{content_hash}.bin"
        if not path.exists():
            return None
        return path.read_bytes()

    def put(self, content_hash: str, data: bytes) -> None:
        # Writes the snapshot atomically (temp file then replace) to avoid torn reads.
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / f"{content_hash}.bin"
        tmp = self._root / f"{content_hash}.bin.tmp"
        tmp.write_bytes(data)
        os.replace(tmp, path)


@dataclass(frozen=True, slots=True)
class UrlAllowlist:
    """Scheme + optional host allowlist enforced before every network call."""

    allowed_schemes: tuple[str, ...] = ("https",)
    allowed_hosts: frozenset[str] | None = None

    def check(self, url: str) -> None:
        # Raises SourceSecurityError when scheme/host are not permitted; returns None when allowed.
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if not scheme or scheme not in self.allowed_schemes:
            raise SourceSecurityError(
                "URL scheme is not permitted by the allowlist.",
                details={"url": url, "scheme": scheme, "allowed_schemes": list(self.allowed_schemes)},
            )
        host = (parsed.hostname or "").lower()
        if not host:
            raise SourceSecurityError("URL is missing a host.", details={"url": url})
        if self.allowed_hosts is not None and host not in self.allowed_hosts:
            raise SourceSecurityError(
                "URL host is not in the allowlist.",
                details={"url": url, "host": host, "allowed_hosts": sorted(self.allowed_hosts)},
            )
