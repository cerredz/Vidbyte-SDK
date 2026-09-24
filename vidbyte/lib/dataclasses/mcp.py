"""Context Protocol Header

Description:
    Defines small MCP protocol data contracts used by the SDK bridge.
Purpose:
    Keeps MCP discovery data separate from native ToolSpec conversion while
    allowing deterministic wrapping into SDK tools.
Architecture:
    - McpToolDefinition: Name, description, JSON Schema, and MCP annotations
      (readOnlyHint, destructiveHint, ...) for a remote tool.
Relations:
    Re-exported by vidbyte.tools.mcp.types.
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
    # MCP tool annotations as the server declared them; hints, not guarantees, per the MCP specification.
    annotations: Mapping[str, Any] = field(default_factory=dict)

    @property
    def read_only(self) -> bool | None:
        """Return the declared readOnlyHint, or None when the server did not declare one."""
        value = self.annotations.get("readOnlyHint")
        return value if isinstance(value, bool) else None

    @property
    def destructive(self) -> bool | None:
        """Return the declared destructiveHint, or None when the server did not declare one."""
        value = self.annotations.get("destructiveHint")
        return value if isinstance(value, bool) else None
