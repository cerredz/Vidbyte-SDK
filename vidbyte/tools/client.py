from __future__ import annotations

from collections.abc import Iterable

from vidbyte.tools.adapters import ToolInput
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.mixins import ToolMixin
from vidbyte.tools.registry import ToolRegistry


class ToolsClient(ToolMixin):
    """Namespace client for tool operations."""

    def __init__(self, tools: Iterable[ToolInput] | None = None) -> None:
        self._tool_registry = ToolRegistry(tools)
        self._tool_executor = ToolExecutor(self._tool_registry)

    def register(self, tool: ToolInput) -> "ToolsClient":
        self.tool_registry.register(tool)
        return self
