"""Context Protocol Header

Description:
    Re-exports web fetch backend implementations.
Purpose:
    Provides a stable import surface for web fetch provider backends without
    exposing internal implementation details.
Architecture:
    - BaseWebFetchBackend: Abstract contract.
    - HttpxFetchBackend: HTTP-based fetch implementation.
    - FetchResult: Data transfer object for fetch responses.
Relations:
    Related to vidbyte.tools.builtins.web_fetch.
"""

from __future__ import annotations

from vidbyte.lib.providers.web_fetch.base import BaseWebFetchBackend, FetchResult
from vidbyte.lib.providers.web_fetch.httpx_backend import HttpxFetchBackend

__all__ = [
    "BaseWebFetchBackend",
    "FetchResult",
    "HttpxFetchBackend",
]
