"""Context Protocol Header

Description:
    Exports MCP discovery tools for dynamic agent-driven server attachment.
Purpose:
    Provides a stable import surface for the SearchMcpServersTool,
    AttachMcpServerTool, and the SmitheryRegistryClient they depend on.
Architecture:
    - SearchMcpServersTool: Queries the Smithery global MCP registry.
    - AttachMcpServerTool: Attaches a discovered server to the owning agent.
    - SmitheryRegistryClient: Low-level Smithery HTTP client (injectable in tests).
Relations:
    Re-exported by vidbyte.tools.builtins.
    AttachMcpServerTool binding is wired in vidbyte.agents.base.BaseAgent.
"""

from __future__ import annotations

from vidbyte.tools.builtins.mcp.attach_tool import AttachMcpServerTool
from vidbyte.tools.builtins.mcp.search import (
    SearchMcpServersTool,
    SmitheryRegistryClient,
    SmitheryServerResult,
)

__all__ = [
    "AttachMcpServerTool",
    "SearchMcpServersTool",
    "SmitheryRegistryClient",
    "SmitheryServerResult",
]
