"""Context Protocol Header

Description:
    Re-exports MCP data contracts from the SDK dataclass namespace.
Purpose:
    Preserves `vidbyte.tools.mcp.types` imports while keeping dataclass
    definitions under `vidbyte.lib.dataclasses`.
Architecture:
    - Compatibility shim for McpToolDefinition.
Relations:
    Related to vidbyte.lib.dataclasses.mcp.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.mcp import McpToolDefinition

__all__ = [
    "McpToolDefinition",
]
