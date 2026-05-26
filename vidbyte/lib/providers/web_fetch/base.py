"""Context Protocol Header

Description:
    Defines the abstract base class and data transfer object for web fetch backends.
Purpose:
    Provides a typed contract that web fetch provider backends must implement,
    along with the shared FetchResult dataclass.
Architecture:
    - FetchResult: Dataclass with content, content_type, status_code, final_url.
    - BaseWebFetchBackend: ABC requiring async fetch().
Relations:
    Related to vidbyte.lib.providers.web_fetch and vidbyte.tools.builtins.web_fetch.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class FetchResult:
    content: str
    content_type: str
    status_code: int
    final_url: str


class BaseWebFetchBackend(ABC):
    @abstractmethod
    async def fetch(self, url: str, format: str, timeout_ms: int) -> FetchResult:
        ...


__all__ = [
    "BaseWebFetchBackend",
    "FetchResult",
]
