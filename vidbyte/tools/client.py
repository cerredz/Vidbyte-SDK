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

from vidbyte.tools.base import BaseTool
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.registry import ToolRegistry
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolSpec


class ToolsClient:
    """Namespace client for tool registration and execution."""

    tool_spec_type = ToolSpec

    def __init__(self, *, permission_policy: PermissionPolicy | None = None) -> None:
        """Create a registry and executor for tool operations."""
        self.registry = ToolRegistry()
        self.executor = ToolExecutor(
            self.registry,
            permission_policy=permission_policy,
        )

    def register(self, tool: BaseTool) -> BaseTool:
        """Register a tool and return it for fluent setup in scripts."""
        self.registry.register(tool)
        return tool
