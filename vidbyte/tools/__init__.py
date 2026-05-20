"""Context Protocol Header

Description:
    Exports the public tool contracts and namespace client.
Purpose:
    Gives SDK users stable imports for implementing, registering, and executing
    native or bridged tools.
Architecture:
    - BaseTool: Abstract tool contract.
    - ToolRegistry and ToolExecutor: Registration and execution pipeline.
    - Tool dataclasses and enums from vidbyte.tools.types.
    - ToolsFormatter: Provider-specific schema formatting helper.
    - ToolsClient: Root namespace client exposed by VidbyteSDK.
Relations:
    Related to vidbyte.client and all vidbyte.tools.builtins packages.
"""

from __future__ import annotations

from vidbyte.tools.base import BaseTool
from vidbyte.tools.client import ToolsClient
from vidbyte.tools.executor import ToolExecutor
from vidbyte.lib.tools import ToolsFormatter
from vidbyte.tools.registry import ToolRegistry
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
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
    "ToolsFormatter",
    "ToolsClient",
]
