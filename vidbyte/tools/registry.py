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

from vidbyte.lib.errors import ToolRegistryError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolSpec


class ToolRegistry:
    """Thread-safe registry of named tools."""

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._tools: dict[str, BaseTool] = {}
        self._lock = RLock()

    def register(self, tool: BaseTool) -> None:
        """Register a tool and reject duplicate names."""
        name = tool.name
        with self._lock:
            if name in self._tools:
                raise ToolRegistryError(f"Tool already registered: {name}")
            self._tools[name] = tool

    def get(self, name: str) -> BaseTool:
        """Return a registered tool by name or raise a registry error."""
        with self._lock:
            try:
                return self._tools[name]
            except KeyError as exc:
                raise ToolRegistryError(f"Unknown tool: {name}") from exc

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
