from __future__ import annotations

from collections.abc import Callable
from typing import Any, overload

from vidbyte.tools.function_tool import FunctionTool
from vidbyte.tools.types import ToolPermission


@overload
def tool(func: Callable[..., Any]) -> FunctionTool: ...


@overload
def tool(
    *,
    name: str | None = None,
    description: str | None = None,
    permission: ToolPermission = ToolPermission.SAFE,
) -> Callable[[Callable[..., Any]], FunctionTool]: ...


def tool(
    func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    permission: ToolPermission = ToolPermission.SAFE,
) -> FunctionTool | Callable[[Callable[..., Any]], FunctionTool]:
    """Decorate a Python function and expose it as a Vidbyte tool."""

    def wrap(target: Callable[..., Any]) -> FunctionTool:
        return FunctionTool.from_function(target, name=name, description=description, permission=permission)

    if func is None:
        return wrap
    return wrap(func)


vidbyte_tool = tool


__all__ = ["tool", "vidbyte_tool"]

