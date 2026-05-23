"""Context Protocol Header

Description:
    Provides the SDK namespace client for tool operations.
Purpose:
    Owns the default registry and executor exposed from VidbyteSDK().tools
    without auto-registering potentially environment-specific tools.
Architecture:
    - ToolsClient: Holds ToolRegistry and ToolExecutor instances.
Relations:
    Related to vidbyte.client, vidbyte.tools.registry, and vidbyte.tools.executor.
"""

from __future__ import annotations

from typing import Any

from vidbyte.tools.adapters import ToolInput
from vidbyte.tools.base import BaseTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.registry import ToolRegistry
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolSpec


class ToolsClient:
    """Namespace client for tool registration and execution."""

    tool_spec_type = ToolSpec

    def __init__(self, *, permission_policy: PermissionPolicy | None = None) -> None:
        """Create a registry and executor for tool operations."""
        self.catalog = Tools()
        self.registry = ToolRegistry()
        self.executor = ToolExecutor(
            self.registry,
            permission_policy=permission_policy,
        )

    def register(self, tool: ToolInput) -> BaseTool:
        """Register a tool and return it for fluent setup in scripts."""
        self.registry.register(tool)
        self.catalog = self.catalog.add(tool)
        return self.registry.get(self.registry.all()[-1].name)

    def with_tools(self, tools: ToolInput | list[ToolInput] | tuple[ToolInput, ...]) -> "ToolsClient":
        """Attach tools to this namespace catalog and compatibility registry."""
        items = (tools,) if isinstance(tools, BaseTool) or callable(tools) else tuple(tools)
        self.registry.register_many(items)
        self.catalog = self.catalog.extend(items)
        return self
