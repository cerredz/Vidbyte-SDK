"""Context Protocol Header

Description:
    Re-exports public tool data contracts from the SDK dataclass namespace.
Purpose:
    Preserves existing `vidbyte.tools.types` imports while keeping dataclass
    definitions under `vidbyte.lib.dataclasses`.
Architecture:
    - Compatibility shim for ToolActivity, ToolCall, ToolCallActivity,
      ToolParameter, ToolSpec, ToolResult, ToolPermission, and ToolStatus.
Relations:
    Related to vidbyte.lib.dataclasses.tools.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.tools import (
    ToolActivity,
    ToolCall,
    ToolCallActivity,
    ToolCallContext,
    ToolCallState,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
    ToolStatus,
)

__all__ = [
    "ToolActivity",
    "ToolCall",
    "ToolCallActivity",
    "ToolCallContext",
    "ToolCallState",
    "ToolParameter",
    "ToolPermission",
    "ToolResult",
    "ToolSpec",
    "ToolStatus",
]
