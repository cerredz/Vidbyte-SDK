"""Context Protocol Header

Description:
    Defines the abstract Source[T] substrate and the immutable value types that flow
    through it.
Purpose:
    Owns the deterministic loader lifecycle (fetch -> pin -> parse -> filter/emit -> cache)
    and the shared trust handling (URL allowlist, size guard, untrusted-content labeling),
    delegating only the IR-specific parse and emit steps to concrete loaders.
Architecture:
    - PinPolicy/ArtifactRef/Selection/SourceSnapshot/SourceResult: Immutable request/result types.
    - Source[T]: Template-method ABC running the lifecycle; subclasses implement _parse/_emit.
    - wrap_untrusted_content/untrusted_metadata: Shared labeling for attacker-controlled bytes.
Relations:
    Uses vidbyte.sources._fetch seams; emits vidbyte.context.primitives.DocumentContextItem.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from fnmatch import fnmatch
from typing import Any, Generic, TypeVar

from vidbyte.context.primitives.documents import DocumentContextItem
from vidbyte.lib.errors import SourcePinMismatchError, SourceSecurityError
from vidbyte.sources._fetch import Fetcher, HttpFetcher, SnapshotCache, UrlAllowlist, sha256_hex

T = TypeVar("T")

DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB

UNTRUSTED_CONTENT_BEGIN = "----- BEGIN UNTRUSTED EXTERNAL CONTENT"
UNTRUSTED_CONTENT_END = "----- END UNTRUSTED EXTERNAL CONTENT -----"


def wrap_untrusted_content(body: str, origin: str) -> str:
    # Wraps fetched external text in a visible boundary so a model never treats it as instructions.
    return f"{UNTRUSTED_CONTENT_BEGIN} (source: {origin}) -----\n{body}\n{UNTRUSTED_CONTENT_END}"


def _is_textual(content_type: str) -> bool:
    # True for content types that plausibly carry text/markdown bodies.
    base = content_type.split(";")[0].strip().lower()
    return base.startswith("text/") or "markdown" in base or base in {"application/json", "application/xml"}


def untrusted_metadata(
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
        if not _is_textual(content_type):
            metadata["content_type_warning"] = True
    if extra:
        metadata.update(extra)
    return metadata


class PinPolicy(str, Enum):
    """Determines whether a load reuses a pinned snapshot or always re-fetches."""

    PINNED = "pinned"
    LIVE = "live"


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """Immutable description of a remote artifact to load."""

    url: str
    expected_hash: str | None = None
    pin: PinPolicy = PinPolicy.PINNED
    content_type_hint: str | None = None


@dataclass(frozen=True, slots=True)
class Selection:
    """Allow/deny globs plus the progressive-disclosure expand flag."""

    allow: tuple[str, ...] = ("*",)
    deny: tuple[str, ...] = ()
    expand: bool = False

    def selects(self, *names: str) -> bool:
        # True when any name matches an allow glob and no name matches a deny glob (case-insensitive).
        allowed = any(self._any(self.allow, name) for name in names)
        denied = any(self._any(self.deny, name) for name in names)
        return allowed and not denied

    def matches(self, name: str) -> bool:
        # Convenience single-name form of selects().
        return self.selects(name)

    @property
    def is_trivial(self) -> bool:
        # True when allow is the default "*" with no deny entries (no narrowing requested).
        return self.allow == ("*",) and not self.deny

    @staticmethod
    def _any(patterns: tuple[str, ...], name: str) -> bool:
        # True when name matches any glob in patterns (case-insensitive).
        lowered = name.lower()
        return any(fnmatch(lowered, pattern.lower()) for pattern in patterns)


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """Immutable record of fetched bytes and their content hash."""

    url: str
    raw_bytes: bytes
    content_hash: str
    content_type: str | None = None


@dataclass(frozen=True, slots=True)
class SourceResult(Generic[T]):
    """The full deterministic output of one load: snapshot, IR, and emitted primitives."""

    ref: ArtifactRef
    snapshot: SourceSnapshot
    ir: T
    items: tuple[DocumentContextItem, ...]

    @property
    def content_hash(self) -> str:
        # Convenience accessor for the pinned content hash of the loaded artifact.
        return self.snapshot.content_hash


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
        # Persists the snapshot under its content hash when a cache is configured (else a no-op).
        if self._cache is not None:
            self._cache.put(snapshot.content_hash, snapshot.raw_bytes)

    @abstractmethod
    def _parse(self, snapshot: SourceSnapshot) -> T:
        # Parses raw bytes into a validated IR; must raise SourceParseError on malformed input.
        ...

    @abstractmethod
    def _emit(self, ir: T, snapshot: SourceSnapshot, ref: ArtifactRef, selection: Selection) -> tuple[DocumentContextItem, ...]:
        # Turns the IR + selection into a deterministically ordered tuple of primitives.
        ...
