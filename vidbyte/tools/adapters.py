from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, TypeAlias

from vidbyte.tools.base import BaseTool
from vidbyte.tools.function_tool import FunctionTool

ToolInput: TypeAlias = BaseTool | Callable[..., Any]


def ensure_tool(tool: ToolInput) -> BaseTool:
    """Normalize native tools, decorated tools, and raw callables to BaseTool."""
    if isinstance(tool, BaseTool):
        return tool
    if callable(tool):
        return FunctionTool.from_function(tool)
    raise TypeError(f"Expected a BaseTool or callable, got {type(tool).__name__}.")


def ensure_tools(tools: Iterable[ToolInput]) -> tuple[BaseTool, ...]:
    return tuple(ensure_tool(tool) for tool in tools)

