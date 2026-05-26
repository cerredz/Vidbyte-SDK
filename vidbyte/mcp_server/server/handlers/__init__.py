"""Context Protocol Header

Description:
    Defines the _BaseHandler ABC that all JSON-RPC method handlers implement.
Purpose:
    Gives _dispatch() a typed contract so each handler can be swapped or
    extended independently without changing the dispatch logic.
Architecture:
    - _BaseHandler: Abstract base requiring a single handle(request_id, params) method.
Relations:
    Imported by core.py for type annotation and by each handler module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class _BaseHandler(ABC):
    """Abstract base for all JSON-RPC method handlers."""

    @abstractmethod
    async def handle(self, request_id: int | str | None, params: Any) -> dict[str, Any]:
        """Process a single JSON-RPC request and return a JSON-RPC response dict."""
