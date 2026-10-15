"""Context Protocol Header

Description:
    Provides the compatibility registry wrapper for Vidbyte SDK tools.
Purpose:
    Preserves old ToolRegistry imports while the public model moves to the
    agent-local Tools catalog.
Architecture:
    - ToolRegistry: Mutable compatibility wrapper around Tools.
Relations:
    Related to vidbyte.tools.catalog, vidbyte.tools.executor, and ToolsClient.
"""

from __future__ import annotations

from collections.abc import Iterable
from threading import RLock
from typing import Any

from vidbyte.tools.catalog import Tools
from vidbyte.tools.types import ToolSpec


class ToolRegistry(Tools):
    """Thread-safe mutable compatibility wrapper around Tools."""

    def __init__(self, tools: Iterable[Any] | None = None) -> None:
        self._lock = RLock()
        super().__init__(tools)

    def register(self, tool: Any, *, replace: bool = False) -> None:
        """Register a tool in this compatibility registry."""
        with self._lock:
            updated = self.add(tool, replace=replace)
            self._tools = updated.all()
            self._by_name = {tool.name: tool for tool in self._tools}

    def register_many(self, tools: Iterable[Any], *, replace: bool = False) -> None:
        """Register multiple tools at once, or none of them when one is refused."""
        # @intent refused-batch-registers-nothing
        # The whole batch is built into a new catalog before it replaces this one, so a duplicate
        # late in the batch leaves the registry as it was, the way Tools.extend does.
        with self._lock:
            updated = self.extend(tools, replace=replace)
            self._tools = updated.all()
            self._by_name = {tool.name: tool for tool in self._tools}

    def get(self, name: str):
        """Return a registered tool by name or raise a registry error."""
        with self._lock:
            return self._get(name)

    def all(self):
        """Return all registered tools as an immutable tuple."""
        with self._lock:
            return super().all()

    # @intent registry-readers-never-see-a-half-registered-tool
    # register() replaces _tools and _by_name one after the other under the lock,
    # so any reader that consults both indexes must hold the same lock.
    def subset(self, names: Iterable[str]) -> Tools:
        """Return a new catalog with exactly the requested names, read under the lock."""
        with self._lock:
            return super().subset(names)

    def add(self, tool: Any, *, replace: bool = False) -> Tools:
        """Return a new catalog with one tool added, read under the lock."""
        with self._lock:
            return super().add(tool, replace=replace)

    def specs(self) -> tuple[ToolSpec, ...]:
        """Return tool specs for all registered tools."""
        return tuple(tool.spec() for tool in self.all())

    def specs_as_prompt_str(self) -> str:
        """Render all registered tool specs for model prompts."""
        return self.describe()

    def __len__(self) -> int:
        with self._lock:
            return super().__len__()

    def __contains__(self, name: object) -> bool:
        with self._lock:
            return super().__contains__(name)


__all__ = ["ToolRegistry"]
