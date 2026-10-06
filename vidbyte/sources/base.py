"""Context Protocol Header

Description:
    Defines the abstract Source[T] lifecycle substrate.
Purpose:
    Owns the deterministic loader lifecycle (fetch -> pin -> parse -> emit -> cache) and
    shared trust handling while dataclasses, enums, constants, fetchers, and caches live in
    their dedicated packages.
Architecture:
    - Source[T]: Template-method ABC running the shared source lifecycle.
    - Protected trust helpers: _wrap_untrusted_content and _untrusted_metadata.
Relations:
    Uses vidbyte.lib source contracts, vidbyte.sources.fetches, vidbyte.sources.cache, and
    emits vidbyte.context.primitives.DocumentContextItem.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from vidbyte.context.primitives.documents import DocumentContextItem
from vidbyte.lib.config.sources import (
    DEFAULT_SOURCE_MAX_BYTES,
    TEXTUAL_SOURCE_CONTENT_TYPES,
    UNTRUSTED_CONTENT_BEGIN,
    UNTRUSTED_CONTENT_END,
)
from vidbyte.lib.dataclasses.sources import ArtifactRef, Selection, SourceResult, SourceSnapshot
from vidbyte.lib.enums import PinPolicy
from vidbyte.lib.errors import SourcePinMismatchError, SourceSecurityError
from vidbyte.sources.cache import SnapshotCache
from vidbyte.sources.fetches import Fetcher, HttpFetcher, sha256_hex
from vidbyte.sources.security import UrlAllowlist

T = TypeVar("T")

DEFAULT_MAX_BYTES = DEFAULT_SOURCE_MAX_BYTES


class Source(ABC, Generic[T]):
    """Abstract substrate that compiles a remote artifact into context primitives."""

    def __init__(
        self,
        *,
        fetcher: Fetcher | None = None,
        cache: SnapshotCache | None = None,
        allowlist: UrlAllowlist | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        label_untrusted: bool = True,
    ) -> None:
        # Stores injectable seams; defaults to an HttpFetcher, no cache, and an https-only allowlist.
        self._fetcher = fetcher if fetcher is not None else HttpFetcher()
        self._cache = cache
        self._allowlist = allowlist if allowlist is not None else UrlAllowlist()
        self._max_bytes = max_bytes
        self._label_untrusted = label_untrusted

    def load(self, ref: ArtifactRef, *, selection: Selection | None = None) -> SourceResult[T]:
        # Runs fetch -> pin -> parse -> filter/emit -> cache and returns the deterministic result.
        selection = selection or Selection()
        snapshot = self._fetch_snapshot(ref)
        snapshot = self._pin(snapshot, ref)
        ir = self._parse(snapshot)
        items = self._emit(ir, snapshot, ref, selection)
        self._store(snapshot)
        return SourceResult(ref=ref, snapshot=snapshot, ir=ir, items=items)

    def _fetch_snapshot(self, ref: ArtifactRef) -> SourceSnapshot:
        # Guards the URL, serves a pinned warm cache hit without network, else fetches under the size cap.
        self._allowlist.check(ref.url)
        if ref.pin is PinPolicy.PINNED and ref.expected_hash and self._cache is not None:
            cached = self._cache.get(ref.expected_hash)
            if cached is not None:
                return SourceSnapshot(url=ref.url, raw_bytes=cached, content_hash=ref.expected_hash)
        response = self._fetcher.fetch(ref.url)
        if len(response.body_bytes) > self._max_bytes:
            raise SourceSecurityError(
                "Fetched artifact exceeds the maximum allowed size.",
                details={"url": ref.url, "size_bytes": len(response.body_bytes), "max_bytes": self._max_bytes},
            )
        return SourceSnapshot(
            url=ref.url,
            raw_bytes=response.body_bytes,
            content_hash=sha256_hex(response.body_bytes),
            content_type=response.content_type,
        )

    def _pin(self, snapshot: SourceSnapshot, ref: ArtifactRef) -> SourceSnapshot:
        # Verifies the content hash against any expected_hash and fails closed on mismatch.
        actual = sha256_hex(snapshot.raw_bytes)
        if ref.expected_hash and actual != ref.expected_hash:
            raise SourcePinMismatchError(
                "Fetched content hash does not match the pinned expected hash.",
                details={"url": ref.url, "expected": ref.expected_hash, "actual": actual},
            )
        if actual != snapshot.content_hash:
            return SourceSnapshot(url=snapshot.url, raw_bytes=snapshot.raw_bytes, content_hash=actual, content_type=snapshot.content_type)
        return snapshot

    def _store(self, snapshot: SourceSnapshot) -> None:
        # Persists the snapshot under its content hash when a cache is configured.
        if self._cache is not None:
            self._cache.put(snapshot.content_hash, snapshot.raw_bytes)

    def _wrap_untrusted_content(self, body: str, origin: str) -> str:
        # Wraps fetched external text in a visible boundary so a model never treats it as instructions.
        return f"{UNTRUSTED_CONTENT_BEGIN} (source: {origin}) -----\n{body}\n{UNTRUSTED_CONTENT_END}"

    def _untrusted_metadata(
        self,
        *,
        origin: str,
        content_hash: str,
        source_kind: str,
        content_type: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Builds the provenance/trust metadata stamped on every emitted primitive.
        metadata: dict[str, Any] = {
            "trust": "untrusted-external",
            "origin": origin,
            "content_sha256": content_hash,
            "source_kind": source_kind,
        }
        if content_type is not None:
            metadata["content_type"] = content_type
            if not self._is_textual(content_type):
                metadata["content_type_warning"] = True
        if extra:
            metadata.update(extra)
        return metadata

    def _is_textual(self, content_type: str) -> bool:
        # True for content types that plausibly carry text or markdown bodies.
        base = content_type.split(";")[0].strip().lower()
        return base.startswith("text/") or "markdown" in base or base in TEXTUAL_SOURCE_CONTENT_TYPES

    @abstractmethod
    def _parse(self, snapshot: SourceSnapshot) -> T:
        # Parses raw bytes into a validated IR; must raise SourceParseError on malformed input.
        ...

    @abstractmethod
    def _emit(self, ir: T, snapshot: SourceSnapshot, ref: ArtifactRef, selection: Selection) -> tuple[DocumentContextItem, ...]:
        # Turns the IR + selection into a deterministically ordered tuple of primitives.
        ...


__all__ = [
    "ArtifactRef",
    "DEFAULT_MAX_BYTES",
    "PinPolicy",
    "Selection",
    "Source",
    "SourceResult",
    "SourceSnapshot",
]
