"""Context Protocol Header

Description:
    Shared base helpers for provider operation tools.
Purpose:
    Converts provider method results and exceptions into ToolResult values while
    keeping provider-specific tools small and focused on their atomic operation.
Architecture:
    - ProviderOperationTool: BaseTool storing a provider object and JSON helpers.
Relations:
    Subclassed by MongoDB and row/table provider built-in tools.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from vidbyte.sessions.errors import SessionError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolResult


class ProviderOperationTool(BaseTool):
    """Base class for a store-bound provider operation tool."""

    def __init__(self, store: object, *, provider_name: str) -> None:
        self._store = store
        self._provider_name = provider_name

    def _result(self, tool_name: str, operation: Callable[[], Any]) -> ToolResult:
        # Convert provider output to JSON and provider errors to tool errors.
        try:
            return ToolResult.success(tool_name, json.dumps(operation(), default=str))
        except (SessionError, ValueError, TypeError) as exc:
            return ToolResult.error(tool_name, f"{type(exc).__name__}: {exc}")


__all__ = ["ProviderOperationTool"]
