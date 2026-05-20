from __future__ import annotations

import threading
from collections.abc import Iterable

from vidbyte.lib.errors import ToolRegistrationError
from vidbyte.tools.adapters import ToolInput, ensure_tool
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolSpec


class ToolRegistry:
    """Thread-safe registry for native and function-backed tools."""

    def __init__(self, tools: Iterable[ToolInput] | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._lock = threading.RLock()
        if tools is not None:
            self.register_many(tools)

    def register(self, tool: ToolInput, *, replace: bool = False) -> "ToolRegistry":
        normalized = ensure_tool(tool)
        name = normalized.name
        with self._lock:
            if name in self._tools and not replace:
                raise ToolRegistrationError(f"Tool '{name}' is already registered.")
            self._tools[name] = normalized
        return self

    def register_many(self, tools: Iterable[ToolInput], *, replace: bool = False) -> "ToolRegistry":
        for tool in tools:
            self.register(tool, replace=replace)
        return self

    def merge(self, other: "ToolRegistry", *, replace: bool = False) -> "ToolRegistry":
        return self.register_many(other.all(), replace=replace)

    def get(self, name: str) -> BaseTool | None:
        with self._lock:
            return self._tools.get(name)

    def all(self) -> tuple[BaseTool, ...]:
        with self._lock:
            return tuple(self._tools.values())

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(tool.spec() for tool in self.all())

    def specs_as_prompt_str(self) -> str:
        specs = self.specs()
        if not specs:
            return "No tools are currently available."
        return "\n\n".join(spec.to_prompt_str() for spec in specs)

    def __len__(self) -> int:
        with self._lock:
            return len(self._tools)

