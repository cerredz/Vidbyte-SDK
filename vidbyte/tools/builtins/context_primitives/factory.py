"""Context Protocol Header

Description:
    Implements context_window_tools(), the factory for context editing tools.
Purpose:
    Lets developers mount the full create and management tool family with one
    call while binding every tool to the same ContextManager instance.
Architecture:
    - context_window_tools: returns generated create tools plus management tools.
Relations:
    Used by developers through vidbyte.tools.builtins.context_primitives.
    Depends on the create registry and management tool classes.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.context_primitives.create import CreateContextPrimitiveTool
from vidbyte.tools.builtins.context_primitives.edit import ContextEditTool
from vidbyte.tools.builtins.context_primitives.list_tool import ContextListTool
from vidbyte.tools.builtins.context_primitives.move import ContextMoveTool
from vidbyte.tools.builtins.context_primitives.registry import CREATE_TOOL_REGISTRY
from vidbyte.tools.builtins.context_primitives.remove import ContextRemoveTool
from vidbyte.tools.builtins.context_primitives.stats import ContextStatsTool
from vidbyte.tools.builtins.context_primitives.view import ContextViewTool

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager


def context_window_tools(manager: ContextManager, *, include: Sequence[str] | None = None, management: bool = True) -> tuple[BaseTool, ...]:
    """Return context primitive create tools and optional management tools."""
    keys = tuple(include) if include is not None else tuple(CREATE_TOOL_REGISTRY)
    unknown = tuple(key for key in keys if key not in CREATE_TOOL_REGISTRY)
    if unknown:
        known = ", ".join(CREATE_TOOL_REGISTRY)
        raise ValueError(f"Unknown context primitive key(s): {', '.join(unknown)}. Known keys: {known}.")
    creates: tuple[BaseTool, ...] = tuple(CreateContextPrimitiveTool(CREATE_TOOL_REGISTRY[key], manager) for key in keys)
    if not management:
        return creates
    return (
        *creates,
        ContextListTool(manager),
        ContextRemoveTool(manager),
        ContextViewTool(manager),
        ContextStatsTool(manager),
        ContextEditTool(manager),
        ContextMoveTool(manager),
    )


__all__ = ["context_window_tools"]
