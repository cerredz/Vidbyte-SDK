"""Context Protocol Header

Description:
    Public surface for the artifact-source (Source/loader) primitive layer.
Purpose:
    Compiles public, machine-readable remote documents into the SDK's existing
    DocumentContextItem context primitive, deterministically and pinned-by-hash by default.
Architecture:
    - Source[T] substrate + ArtifactRef/PinPolicy/Selection/SourceSnapshot/SourceResult value types.
    - DocumentSource (single-document base case) and LlmsTxtSource (llms.txt index + expansion).
    - Fetch/cache/allowlist seams for offline-testable, trust-gated network access.
Relations:
    Emits vidbyte.context.primitives.DocumentContextItem; errors live in vidbyte.lib.errors.
"""

from __future__ import annotations

from vidbyte.sources._fetch import (
    FetchResponse,
    Fetcher,
    FileSnapshotCache,
    HttpFetcher,
    InMemoryFetcher,
    InMemorySnapshotCache,
    SnapshotCache,
    UrlAllowlist,
    sha256_hex,
)
from vidbyte.sources.base import (
    ArtifactRef,
    PinPolicy,
    Selection,
    Source,
    SourceResult,
    SourceSnapshot,
)
from vidbyte.sources.document import DocumentSource, MarkdownDocument
from vidbyte.sources.llms_txt import (
    LlmsTxtDocument,
    LlmsTxtLink,
    LlmsTxtSection,
    LlmsTxtSource,
    parse_llms_txt,
)

__all__ = [
    "ArtifactRef",
    "DocumentSource",
    "FetchResponse",
    "Fetcher",
    "FileSnapshotCache",
    "HttpFetcher",
    "InMemoryFetcher",
    "InMemorySnapshotCache",
    "LlmsTxtDocument",
    "LlmsTxtLink",
    "LlmsTxtSection",
    "LlmsTxtSource",
    "MarkdownDocument",
    "PinPolicy",
    "Selection",
    "SnapshotCache",
    "Source",
    "SourceResult",
    "SourceSnapshot",
    "UrlAllowlist",
    "parse_llms_txt",
    "sha256_hex",
]
