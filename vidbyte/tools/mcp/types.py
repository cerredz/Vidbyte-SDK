"""Context Protocol Header

Description:
    Defines small MCP protocol data types used by the SDK bridge.
Purpose:
    Keeps MCP discovery data separate from the native ToolSpec contract while
    allowing deterministic conversion into SDK tools.
Architecture:
    - McpToolDefinition: Name, description, and JSON Schema for a remote tool.
Relations:
    Related to vidbyte.tools.mcp.client and vidbyte.tools.mcp.bridge.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class McpToolDefinition:
    """Remote MCP tool metadata returned by tools/list."""

    name: str
    description: str
    input_schema: Mapping[str, Any] = field(default_factory=dict)
