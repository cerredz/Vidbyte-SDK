"""Context Protocol Header

Description:
    Agent-bound tool for attaching a new MCP server subprocess to the owning agent.
Purpose:
    Allows a model to dynamically expand its own tool set at runtime by issuing a
    structured attach_mcp_server tool call during an agentic loop iteration.
Architecture:
    - AttachMcpServerTool: BaseTool that calls agent.attach_mcp_server() via an
      injected agent reference bound at add_tool() time by BaseAgent.
Relations:
    Agent binding is wired in vidbyte.agents.base.BaseAgent._bind_agent_tool_context.
    Pairs with SearchMcpServersTool in vidbyte.tools.builtins.mcp.search.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from vidbyte.lib.errors import McpError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.mcp.types import McpToolPermission
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)

if TYPE_CHECKING:
    from vidbyte.agents.mixins import McpAttachableMixin

_PERMISSION_MAP: dict[str, McpToolPermission] = {
    "execute": McpToolPermission.EXECUTE,
    "readonly": McpToolPermission.READONLY,
    "disabled": McpToolPermission.DISABLED,
}


class AttachMcpServerTool(BaseTool):
    """Attaches a new MCP server subprocess to the owning agent at model request time."""

    def __init__(self) -> None:
        """Initialize with no bound agent; agent is injected via bind_agent()."""
        self._agent: McpAttachableMixin | None = None

    def bind_agent(self, agent: McpAttachableMixin) -> None:
        """Store a reference to the owning agent so execute() can call attach_mcp_server()."""
        self._agent = agent

    def clone_for_fork(self) -> AttachMcpServerTool:
        # Returns a fresh unbound MCP attach tool so dynamic attachments target the fork owner.
        return AttachMcpServerTool()

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for the attach_mcp_server tool."""
        return ToolSpec(
            name="attach_mcp_server",
            description=(
                "Attach a new MCP server subprocess to this agent. "
                "The server's tools will be available to this agent starting from the next tool call iteration. "
                "Use search_mcp_servers first to find the right server and its command."
            ),
            parameters=(
                ToolParameter(
                    name="command",
                    type="string",
                    description=(
                        "JSON-encoded array of command parts to launch the MCP server, "
                        "e.g. '[\"npx\", \"-y\", \"@modelcontextprotocol/server-filesystem\", \"/tmp\"]'. "
                        "Use the 'command' field returned by search_mcp_servers directly."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="name",
                    type="string",
                    description="Optional human-readable name for this server.",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="permission",
                    type="string",
                    description="Permission level for this server's tools: 'execute', 'readonly', or 'disabled'. Defaults to 'execute'.",
                    required=False,
                    default="execute",
                ),
                ToolParameter(
                    name="timeout",
                    type="number",
                    description="Seconds to wait for the MCP server handshake. Defaults to 30.0.",
                    required=False,
                    default=30.0,
                ),
            ),
            permission=ToolPermission.EXECUTE,
            metadata={"source": "mcp_attach"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Parse arguments, attach the MCP server, and return a summary of bridged tools."""
        if self._agent is None:
            return ToolResult.error(
                self.name,
                "No agent bound to this tool. Add it to an agent via agent.add_tool().",
                metadata={"source": "mcp_attach"},
            )

        raw_command = call.arguments.get("command", "")
        command = self._parse_command(str(raw_command))
        if command is None:
            return ToolResult.error(
                self.name,
                self._last_parse_error,
                metadata={"source": "mcp_attach"},
            )

        name: str | None = call.arguments.get("name") or None
        if name is not None:
            name = str(name).strip() or None

        raw_permission = str(call.arguments.get("permission", "execute")).lower().strip()
        permission = self._parse_permission(raw_permission)

        raw_timeout = call.arguments.get("timeout", 30.0)
        try:
            timeout = float(raw_timeout)
        except (TypeError, ValueError):
            timeout = 30.0

        try:
            await self._agent.attach_mcp_server(
                command=command,
                name=name,
                permission=permission,
                timeout=timeout,
            )
        except McpError as exc:
            return ToolResult.error(
                self.name,
                f"MCP server attachment failed: {exc}",
                metadata={"source": "mcp_attach"},
            )
        except Exception as exc:
            return ToolResult.error(
                self.name,
                f"Unexpected error during MCP attachment: {exc}",
                metadata={"source": "mcp_attach"},
            )

        handles = self._agent.mcp_servers()
        handle = handles[-1] if handles else None
        server_name = handle.name if handle else (name or " ".join(command[:2]))
        tool_names = handle.tool_names if handle else ()
        summary = self._format_summary(server_name, tool_names)
        return ToolResult.success(
            self.name,
            summary,
            metadata={"source": "mcp_attach", "tool_count": len(tool_names)},
        )

    def _parse_command(self, raw: str) -> list[str] | None:
        """Parse a JSON-encoded command string into a validated list of strings."""
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            self._last_parse_error = f"command is not valid JSON: {exc}"
            return None
        if not isinstance(parsed, list) or len(parsed) == 0:
            self._last_parse_error = "command must be a non-empty JSON array."
            return None
        if not all(isinstance(part, str) for part in parsed):
            self._last_parse_error = "command array must contain only strings."
            return None
        return parsed

    def _parse_permission(self, raw: str) -> McpToolPermission:
        """Map a permission string to McpToolPermission, defaulting to EXECUTE."""
        return _PERMISSION_MAP.get(raw, McpToolPermission.EXECUTE)

    def _format_summary(self, server_name: str, tool_names: tuple[str, ...]) -> str:
        """Serialize attachment result as JSON for model consumption."""
        return json.dumps(
            {
                "attached": True,
                "server_name": server_name,
                "tools_added": list(tool_names),
                "note": "New tools will be available starting from the next tool call iteration.",
            },
            indent=2,
        )


__all__ = ["AttachMcpServerTool"]
