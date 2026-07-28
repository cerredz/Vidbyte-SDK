"""Context Protocol Header

Description:
    Provider-neutral payloads returned by the executing search and fetch clients.
Purpose:
    Carries normalized provider results plus the attempt and unit counts the
    runtime needs to price an operation, so applications consume typed data
    instead of vendor JSON.
Architecture:
    - SearchHit / SearchPayload: one normalized web-search result set.
    - FetchedPage / FetchPayload: one normalized page-content result set.
    - Every record keeps its undecoded vendor mapping under raw.
Relations:
    Produced by vidbyte.tools.builtins.operations.clients and attached to
    ToolResult metadata by vidbyte.tools.builtins.operations tools.
Similar Files:
    - vidbyte/lib/dataclasses/sources.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One normalized web-search result with its undecoded vendor record."""

    title: str
    url: str
    snippet: str | None = None
    published_at: str | None = None
    language: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SearchPayload:
    """One search provider's normalized hits plus its billing counts."""

    provider: str
    query: str
    hits: tuple[SearchHit, ...] = ()
    attempts: int = 1
    billable_units: int = 1


@dataclass(frozen=True, slots=True)
class FetchedPage:
    """One normalized page body with its undecoded vendor record."""

    url: str
    final_url: str
    content: str
    content_type: str
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FetchPayload:
    """One fetch provider's normalized pages plus its billing counts."""

    provider: str
    pages: tuple[FetchedPage, ...] = ()
    attempts: int = 1
    billable_units: int = 1


__all__ = [
    "FetchPayload",
    "FetchedPage",
    "SearchHit",
    "SearchPayload",
]
