"""Context Protocol Header

Description:
    Defines dataclass contracts for artifact sources.
Purpose:
    Centralizes immutable request, snapshot, result, fetch response, and parsed IR
    contracts while source modules provide stable re-export shims.
Architecture:
    - FetchResponse: Raw transport result returned by source fetchers.
    - ArtifactRef/Selection/SourceSnapshot/SourceResult: Source lifecycle value types.
    - MarkdownDocument and LlmsTxt* dataclasses: Parsed document IR contracts.
Relations:
    Imported by vidbyte.sources, vidbyte.sources.base, loaders, parsers, fetchers, and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Generic, TypeVar

from vidbyte.context.primitives.documents import DocumentContextItem
from vidbyte.lib.enums import PinPolicy

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class FetchResponse:
    """Raw transport result: status, body bytes, and optional content type."""

    status_code: int
    body_bytes: bytes
    content_type: str | None = None


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
        # True when any name matches an allow glob and no name matches a deny glob.
        allowed = any(self._any(self.allow, name) for name in names)
        denied = any(self._any(self.deny, name) for name in names)
        return allowed and not denied

    def matches(self, name: str) -> bool:
        # Convenience single-name form of selects().
        return self.selects(name)

    @property
    def is_trivial(self) -> bool:
        # True when no allow/deny narrowing was requested.
        return self.allow == ("*",) and not self.deny

    @staticmethod
    def _any(patterns: tuple[str, ...], name: str) -> bool:
        # True when name matches any glob in patterns, case-insensitively.
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


@dataclass(frozen=True, slots=True)
class MarkdownDocument:
    """Minimal IR for a single fetched document: a title and its raw body text."""

    title: str
    body: str
    url: str


@dataclass(frozen=True, slots=True)
class LlmsTxtLink:
    """A single markdown link inside an llms.txt section."""

    title: str
    url: str
    note: str | None = None


@dataclass(frozen=True, slots=True)
class LlmsTxtSection:
    """A named H2 section of an llms.txt file containing zero or more links."""

    name: str
    links: tuple[LlmsTxtLink, ...]
    optional: bool = False


@dataclass(frozen=True, slots=True)
class LlmsTxtDocument:
    """Validated IR of a parsed llms.txt file."""

    title: str
    summary: str | None
    details: str | None
    sections: tuple[LlmsTxtSection, ...]


__all__ = [
    "ArtifactRef",
    "FetchResponse",
    "LlmsTxtDocument",
    "LlmsTxtLink",
    "LlmsTxtSection",
    "MarkdownDocument",
    "Selection",
    "SourceResult",
    "SourceSnapshot",
]
