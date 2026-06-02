"""Context Protocol Header

Description:
    Defines the public Tools catalog for agent-local tool inspection and lookup.
Purpose:
    Replaces registry-first public usage with a lightweight catalog that can
    describe tools, expose provider schemas, and support internal agent lookup.
Architecture:
    - Tools: Sequence-like immutable-ish catalog of normalized BaseTool objects.
Relations:
    Related to vidbyte.tools.adapters, vidbyte.tools.registry, and BaseAgent.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import Any, overload

from vidbyte.lib.errors import ToolRegistrationError, ToolRegistryError
from vidbyte.lib.tools import ToolsFormatter
from vidbyte.tools.adapters import ToolInput, ensure_tool
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolSpec


class Tools(Sequence[BaseTool]):
    """Catalog of tools available to an agent or SDK namespace."""

    def __init__(self, tools: Iterable[ToolInput | "Tools"] | None = None) -> None:
        normalized: list[BaseTool] = []
        by_name: dict[str, BaseTool] = {}
        for item in tools or ():
            items = item.all() if isinstance(item, Tools) else (item,)
            for raw_tool in items:
                tool = _ensure_catalog_tool(raw_tool)
                if tool.name in by_name:
                    raise ToolRegistrationError(f"Tool already exists: {tool.name}")
                normalized.append(tool)
                by_name[tool.name] = tool
        self._tools = tuple(normalized)
        self._by_name = dict(by_name)

    def all(self) -> tuple[BaseTool, ...]:
        """Return every tool in deterministic insertion order."""
        return self._tools

    def names(self) -> tuple[str, ...]:
        """Return every tool name in deterministic insertion order."""
        return tuple(tool.name for tool in self._tools)

    def specs(self) -> tuple[ToolSpec, ...]:
        """Return model-facing specs for all tools."""
        return tuple(tool.spec() for tool in self._tools)

    def describe(self) -> str:
        """Render tool instructions for prompts or developer inspection."""
        specs = self.specs()
        if not specs:
            return "No tools available."
        return "\n\n".join(spec.to_prompt_str() for spec in specs)

    def provider_schemas(self, provider_or_model: str, *, strict: bool = False) -> tuple[dict[str, Any], ...]:
        # Returns provider-native tool declarations for this catalog.
        return ToolsFormatter.format_tools(self, provider_or_model, strict=strict)

    def add(self, tool: ToolInput, *, replace: bool = False) -> "Tools":
        """Return a new catalog with one tool added."""
        normalized = _ensure_catalog_tool(tool)
        if normalized.name in self._by_name and not replace:
            raise ToolRegistrationError(f"Tool already exists: {normalized.name}")
        tools = tuple(existing for existing in self._tools if existing.name != normalized.name)
        return Tools((*tools, normalized))

    def extend(self, tools: Iterable[ToolInput], *, replace: bool = False) -> "Tools":
        """Return a new catalog with multiple tools added."""
        catalog: Tools = self
        for tool in tools:
            catalog = catalog.add(tool, replace=replace)
        return catalog

    def without(self, tools: Iterable[BaseTool]) -> "Tools":
        """Return a new catalog without the exact tool objects supplied."""
        removed = set(tools)
        return Tools(tool for tool in self._tools if tool not in removed)

    def _get(self, name: str) -> BaseTool:
        """Return a tool by name for internal agent execution."""
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise ToolRegistryError(f"Tool not found in registry: '{name}'") from exc

    @overload
    def __getitem__(self, index: int) -> BaseTool: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[BaseTool, ...]: ...

    def __getitem__(self, index: int | slice) -> BaseTool | tuple[BaseTool, ...]:
        return self._tools[index]

    def __iter__(self) -> Iterator[BaseTool]:
        return iter(self._tools)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, item: object) -> bool:
        if isinstance(item, str):
            return item in self._by_name
        return item in self._tools


__all__ = ["Tools"]


def _ensure_catalog_tool(tool: ToolInput | object) -> BaseTool:
    try:
        return ensure_tool(tool)  # type: ignore[arg-type]
    except TypeError:
        spec = getattr(tool, "spec", None)
        if callable(spec):
            return _SpecOnlyTool(tool)
        raise


class _SpecOnlyTool(BaseTool):
    """Compatibility adapter for legacy objects that only expose spec()."""

    def __init__(self, tool: object) -> None:
        self._tool = tool

    def spec(self) -> ToolSpec:
        raw_spec = self._tool.spec()  # type: ignore[attr-defined]
        if isinstance(raw_spec, ToolSpec):
            return raw_spec
        return ToolSpec(
            name=str(getattr(raw_spec, "name", self._tool.__class__.__name__)),
            description=str(getattr(raw_spec, "description", self._tool.__class__.__name__)),
        )

    async def execute(self, call):
        del call
        from vidbyte.tools.types import ToolResult

        return ToolResult.error(self.name, "This tool only exposes a spec and cannot execute.")
