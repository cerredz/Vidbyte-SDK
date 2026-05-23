"""Context Protocol Header

Description:
    Implements the in-memory registry for Vidbyte SDK tools.
Purpose:
    Owns tool registration and lookup while leaving execution and security
    checks to ToolExecutor.
Architecture:
    - ToolRegistry: Stores tools by name and renders tool specs for prompts.
Relations:
    Related to vidbyte.tools.base, vidbyte.tools.executor, and vidbyte.tools.client.
"""

from __future__ import annotations

from threading import RLock

from collections.abc import Iterable
from typing import Any

from vidbyte.lib.errors import ToolRegistrationError, ToolRegistryError
from vidbyte.tools.adapters import ensure_tool
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolSpec


class ToolRegistry:
    """Thread-safe registry of named tools."""

    def __init__(self, tools: Iterable[Any] | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._lock = RLock()
        for tool in tools or ():
            self.register(tool)

    def register(self, tool: Any, *, replace: bool = False) -> None:
        """Register a tool; accepts BaseTool or raw callables. Raises ToolRegistrationError on duplicate."""
        normalized = ensure_tool(tool)
        name = normalized.name
        with self._lock:
            if name in self._tools and not replace:
                raise ToolRegistrationError(f"Tool already registered: {name}")
            self._tools[name] = normalized

    def register_many(self, tools: Iterable[Any], *, replace: bool = False) -> None:
        """Register multiple tools at once."""
        for tool in tools:
            self.register(tool, replace=replace)

    def get(self, name: str) -> BaseTool:
        """Return a registered tool by name or raise a registry error."""
        with self._lock:
            try:
                return self._tools[name]
            except KeyError as exc:
                raise ToolRegistryError(f"Tool not found in registry: '{name}'") from exc

    def all(self) -> tuple[BaseTool, ...]:
        """Return all registered tools as an immutable tuple."""
        with self._lock:
            return tuple(self._tools.values())

    def specs(self) -> tuple[ToolSpec, ...]:
        """Return tool specs for all registered tools."""
        return tuple(tool.spec() for tool in self.all())

    def specs_as_prompt_str(self) -> str:
        """Render all registered tool specs for model prompts."""
        return "\n\n".join(spec.to_prompt_str() for spec in self.specs())

    def __len__(self) -> int:
        with self._lock:
            return len(self._tools)

    def __contains__(self, name: str) -> bool:
        with self._lock:
            return name in self._tools
