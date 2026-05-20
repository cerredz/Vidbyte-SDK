from __future__ import annotations

from collections.abc import Iterable
from typing import Self

from vidbyte.tools.adapters import ToolInput
from vidbyte.tools.base import BaseTool
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.registry import ToolRegistry


class ToolMixin:
    """Mixin for objects that own an instance-local tool registry."""

    _tool_registry: ToolRegistry | None = None
    _tool_executor: ToolExecutor | None = None

    def with_tools(self, tools: Iterable[ToolInput] | ToolInput) -> Self:
        if isinstance(tools, BaseTool) or callable(tools):
            tool_items = (tools,)
        else:
            tool_items = tuple(tools)
        self.tool_registry.register_many(tool_items)
        return self

    @property
    def tool_registry(self) -> ToolRegistry:
        if self._tool_registry is None:
            self._tool_registry = ToolRegistry()
        return self._tool_registry

    @property
    def tool_executor(self) -> ToolExecutor:
        if self._tool_executor is None:
            self._tool_executor = ToolExecutor(self.tool_registry)
        return self._tool_executor

    def _copy_tools_to(self, target: object) -> None:
        if not isinstance(target, ToolMixin) or len(self.tool_registry) == 0:
            return
        existing_names = {tool.name for tool in target.tool_registry.all()}
        for tool in self.tool_registry.all():
            if tool.name not in existing_names:
                target.tool_registry.register(tool)

