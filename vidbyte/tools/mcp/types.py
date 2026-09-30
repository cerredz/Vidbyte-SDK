"""Context Protocol Header

Description:
    Defines configurations, live connection handles, and tool permissions for MCP server attachment.
Purpose:
    Allows high-level mixins and free functions to configure and close MCP connections
    without knowing low-level transport and client mechanics.
Architecture:
    - McpToolPermission: Defines execution access levels for remote tools.
    - McpServerConfig: Immutable description of an MCP server connection: a stdio
      command or a Streamable HTTP url with headers, plus an optional tool
      allowlist and name prefix for bridging.
    - McpServerHandle: Stateful record of a connected MCP server that owns subprocess lifetime.
Relations:
    Related to vidbyte.tools.mcp.client, vidbyte.tools.mcp.transport, and vidbyte.lib.dataclasses.mcp.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from vidbyte.lib.dataclasses.mcp import McpToolDefinition
from vidbyte.lib.errors import ConfigurationError
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
    """Configuration for one MCP server connection: a stdio subprocess or a remote Streamable HTTP endpoint."""

    command: tuple[str, ...] = ()
    name: str | None = None
    permission: McpToolPermission = McpToolPermission.EXECUTE
    env: Mapping[str, str] | None = None
    timeout: float = 30.0
    # Remote servers: the Streamable HTTP endpoint and the headers every request carries (often a credential).
    url: str | None = None
    headers: Mapping[str, str] | None = field(default=None, repr=False)
    # Bridging: None bridges every discovered tool; a tuple bridges only those names (empty bridges none).
    tool_allowlist: tuple[str, ...] | None = None
    # Prefix added to each bridged tool's model-facing name so two servers' tools cannot collide.
    tool_prefix: str = ""

    def __post_init__(self) -> None:
        # Requires exactly one connection target so attach never guesses between a process and a URL.
        object.__setattr__(self, "command", tuple(self.command))
        if bool(self.command) == bool(self.url):
            raise ConfigurationError("McpServerConfig needs exactly one of command (stdio) or url (Streamable HTTP).")
        if self.tool_allowlist is not None:
            object.__setattr__(self, "tool_allowlist", tuple(self.tool_allowlist))

    @property
    def target(self) -> str:
        """Return the command or URL this configuration connects to, for display and errors."""
        return self.url or " ".join(self.command)


@dataclass(slots=True)
class McpServerHandle:
    """A live MCP server connection session attached to an agent or harness."""

    config: McpServerConfig
    client: McpClient
    transport: McpTransport
    bridged_tools: tuple[BaseTool, ...]
    # Every tool the server listed at connect time, including tools the allowlist did not bridge.
    definitions: tuple[McpToolDefinition, ...] = ()

    async def close(self) -> None:
        """Close the underlying process transport and clean up subprocess streams."""
        await self.transport.close()

    @property
    def name(self) -> str:
        """Stable display name derived from config or command prefix."""
        return self.config.name or (self.config.url or " ".join(self.config.command[:2]))

    @property
    def tool_names(self) -> tuple[str, ...]:
        """Names of all tools bridged from this server."""
        return tuple(tool.spec().name for tool in self.bridged_tools)
