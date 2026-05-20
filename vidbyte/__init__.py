"""Context Protocol Header

Description:
    Exports the root Vidbyte SDK client and top-level public tool contracts.
Purpose:
    Keeps common SDK imports concise while leaving specialized built-in tools in
    their category packages.
Architecture:
    - VidbyteSDK: Root namespace client.
    - Tool contract exports: BaseTool, ToolSpec, ToolCall, ToolResult, ToolRegistry, ToolExecutor.
Relations:
    Related to vidbyte.client and vidbyte.tools.
"""

from __future__ import annotations

from vidbyte.client import VidbyteSDK
from vidbyte.tools import (
    BaseTool,
    ToolCall,
    ToolExecutor,
    ToolParameter,
    ToolPermission,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    ToolStatus,
)

__all__ = [
    "BaseTool",
    "ToolCall",
    "ToolExecutor",
    "ToolParameter",
    "ToolPermission",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "ToolStatus",
    "VidbyteSDK",
]
