"""Context Protocol Header

Description:
    Implements ContextWindowFactory, the mount surface for context editing tools.
Purpose:
    Lets developers mount the full create and management tool family with one
    clean class interface while binding every tool to the same ContextManager.
Architecture:
    - ContextWindowFactory: constructs create tools plus optional management tools.
    - context_window_tools: thin convenience wrapper around ContextWindowFactory.build.
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
from vidbyte.tools.builtins.context_primitives.recite import ContextReciteTool
from vidbyte.tools.builtins.context_primitives.registry import CREATE_TOOL_REGISTRY
from vidbyte.tools.builtins.context_primitives.remove import ContextRemoveTool
from vidbyte.tools.builtins.context_primitives.stats import ContextStatsTool

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager


class ContextWindowFactory:
    """Builds the context-window create and management tool family for one manager.

    Bind the same ContextManager instance that is passed to BaseAgent(context_manager=...).
    Tools mutate that manager in place; the runtime re-renders the registry each loop.
    """

    def __init__(self, manager: ContextManager) -> None:
        """Store the live manager shared with AgentRuntime and every built tool."""
        self._manager = manager

    def build(self, *, include: Sequence[str] | None = None, management: bool = True) -> tuple[BaseTool, ...]:
        """Return create tools (optionally filtered by key) plus management tools when enabled.

        Args:
            include: Optional ordered sequence of primitive keys to mount as create tools.
                When None, all keys in CREATE_TOOL_REGISTRY are mounted.
            management: When True, append list/remove/stats/edit/recite/move tools after creates.

        Returns:
            A tuple of BaseTool instances ready for BaseAgent(tools=...).

        Raises:
            ValueError: If any include key is not present in CREATE_TOOL_REGISTRY.
        """
        keys = tuple(include) if include is not None else tuple(CREATE_TOOL_REGISTRY)
        unknown = tuple(key for key in keys if key not in CREATE_TOOL_REGISTRY)
        if unknown:
            known = ", ".join(CREATE_TOOL_REGISTRY)
            raise ValueError(f"Unknown context primitive key(s): {', '.join(unknown)}. Known keys: {known}.")
        creates: tuple[BaseTool, ...] = tuple(CreateContextPrimitiveTool(CREATE_TOOL_REGISTRY[key], self._manager) for key in keys)
        if not management:
            return creates
        return (
            *creates,
            ContextListTool(self._manager),
            ContextRemoveTool(self._manager),
            ContextStatsTool(self._manager),
            ContextEditTool(self._manager),
            ContextReciteTool(self._manager),
            ContextMoveTool(self._manager),
        )

    def create_tools(self, *, include: Sequence[str] | None = None) -> tuple[BaseTool, ...]:
        """Return only the per-primitive create tools for the requested keys."""
        return self.build(include=include, management=False)

    def management_tools(self) -> tuple[BaseTool, ...]:
        """Return only the management tools (list/remove/stats/edit/recite/move)."""
        return (
            ContextListTool(self._manager),
            ContextRemoveTool(self._manager),
            ContextStatsTool(self._manager),
            ContextEditTool(self._manager),
            ContextReciteTool(self._manager),
            ContextMoveTool(self._manager),
        )


def context_window_tools(manager: ContextManager, *, include: Sequence[str] | None = None, management: bool = True) -> tuple[BaseTool, ...]:
    """Convenience wrapper around ContextWindowFactory(manager).build(...)."""
    return ContextWindowFactory(manager).build(include=include, management=management)


__all__ = ["ContextWindowFactory", "context_window_tools"]
