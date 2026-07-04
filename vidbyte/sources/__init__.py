"""Context Protocol Header

Description:
    Public surface for the artifact-source primitive layer.
Purpose:
    Compiles public, machine-readable documents into DocumentContextItem primitives
    deterministically and pinned-by-hash by default.
Architecture:
    - Source substrate with lib-owned dataclasses/enums/config.
    - Source loaders under vidbyte.sources.loaders.
    - Fetchers, caches, regex helpers, and security gates in dedicated subpackages.
Relations:
    Emits vidbyte.context.primitives.DocumentContextItem; errors live in vidbyte.lib.errors.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.sources import (
    ArtifactRef,
    FetchResponse,
    LlmsTxtDocument,
    LlmsTxtLink,
    LlmsTxtSection,
    MarkdownDocument,
    Selection,
    SourceResult,
    SourceSnapshot,
)
from vidbyte.lib.enums import PinPolicy
from vidbyte.sources.base import Source
from vidbyte.sources.cache import FileSnapshotCache, InMemorySnapshotCache, NullSnapshotCache, SnapshotCache
from vidbyte.sources.fetches import ChainedFetcher, Fetcher, FileFetcher, HttpFetcher, InMemoryFetcher, sha256_hex
from vidbyte.sources.llms_txt.parser import LlmsTxtParser, parse_llms_txt
from vidbyte.sources.loaders.document import DocumentSource
from vidbyte.sources.loaders.llms_txt import LlmsTxtSource
from vidbyte.sources.regex import DocumentRegex, LlmsTxtRegex, SourcesRegex
from vidbyte.sources.security import UrlAllowlist

__all__ = [
    "ArtifactRef",
    "ChainedFetcher",
    "DocumentRegex",
    "DocumentSource",
    "Fetcher",
    "FetchResponse",
    "FileFetcher",
    "FileSnapshotCache",
    "HttpFetcher",
    "InMemoryFetcher",
    "InMemorySnapshotCache",
    "LlmsTxtDocument",
    "LlmsTxtLink",
    "LlmsTxtParser",
    "LlmsTxtRegex",
    "LlmsTxtSection",
    "LlmsTxtSource",
    "MarkdownDocument",
    "NullSnapshotCache",
    "PinPolicy",
    "Selection",
    "SnapshotCache",
    "Source",
    "SourceResult",
    "SourceSnapshot",
    "SourcesRegex",
    "UrlAllowlist",
    "parse_llms_txt",
    "sha256_hex",
]
