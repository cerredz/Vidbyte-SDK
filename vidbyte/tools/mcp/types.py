"""Context Protocol Header

Description:
    Defines configurations, live connection handles, and tool permissions for MCP server attachment.
Purpose:
    Allows high-level mixins and free functions to configure and close MCP connections
    without knowing low-level transport and client mechanics.
Architecture:
    - McpToolPermission: Defines execution access levels for remote tools.
    - McpServerConfig: Immutable description of an MCP server connection.
    - McpServerHandle: Stateful record of a connected MCP server that owns subprocess lifetime.
Relations:
    Related to vidbyte.tools.mcp.client, vidbyte.tools.mcp.transport, and vidbyte.lib.dataclasses.mcp.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from vidbyte.lib.dataclasses.mcp import McpToolDefinition
from vidbyte.tools.base import BaseTool

if TYPE_CHECKING:
    from vidbyte.tools.mcp.client import McpClient
    from vidbyte.tools.mcp.transport import McpTransport


class McpToolPermission(str, Enum):
    """Permissions for execution of remote MCP tools."""

    EXECUTE = "execute"
    READONLY = "readonly"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class McpServerConfig:
    """Configuration required to start and initialize one Model Context Protocol (MCP) server subprocess."""

    command: tuple[str, ...]
    name: str | None = None
    permission: McpToolPermission = McpToolPermission.EXECUTE
    env: Mapping[str, str] | None = None
    timeout: float = 30.0


@dataclass(slots=True)
class McpServerHandle:
    """A live MCP server connection session attached to an agent or harness."""

    config: McpServerConfig
    client: McpClient
    transport: McpTransport
    bridged_tools: tuple[BaseTool, ...]

    async def close(self) -> None:
        """Close the underlying process transport and clean up subprocess streams."""
        await self.transport.close()

    @property
    def name(self) -> str:
        """Stable display name derived from config or command prefix."""
        return self.config.name or " ".join(self.config.command[:2])

    @property
    def tool_names(self) -> tuple[str, ...]:
        """Names of all tools bridged from this server."""
        return tuple(tool.spec().name for tool in self.bridged_tools)
