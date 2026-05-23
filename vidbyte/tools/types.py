"""Context Protocol Header

Description:
    Re-exports public tool data contracts from the SDK dataclass namespace.
Purpose:
    Preserves existing `vidbyte.tools.types` imports while keeping dataclass
    definitions under `vidbyte.lib.dataclasses`.
Architecture:
    - Compatibility shim for ToolCall, ToolParameter, ToolSpec, ToolResult,
      ToolPermission, and ToolStatus.
Relations:
    Related to vidbyte.lib.dataclasses.tools.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.tools import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
    ToolStatus,
)

__all__ = [
    "ToolCall",
    "ToolParameter",
    "ToolPermission",
    "ToolResult",
    "ToolSpec",
    "ToolStatus",
]
