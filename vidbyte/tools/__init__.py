"""Context Protocol Header

Description:
    Exports the public tool contracts and namespace client.
Purpose:
    Gives SDK users stable imports for implementing, registering, and executing
    native or bridged tools.
Architecture:
    - BaseTool: Abstract tool contract.
    - ToolLike: Structural protocol for developer-provided tools.
    - Tools: Agent-local catalog for describing and formatting tools.
    - ToolRegistry and ToolExecutor: Compatibility registration and execution pipeline.
    - Tool dataclasses and enums from vidbyte.tools.types.
    - ToolsFormatter: Provider-specific schema formatting helper.
    - ToolsClient: Root namespace client exposed by VidbyteSDK.
Relations:
    Related to vidbyte.client and all vidbyte.tools.builtins packages.
"""

from __future__ import annotations

from vidbyte.tools.adapters import ToolInput, ensure_tool, ensure_tools
from vidbyte.tools.agent_tool import AgentTool
from vidbyte.tools.base import BaseTool, ToolLike
from vidbyte.tools.catalog import Tools
from vidbyte.tools.client import ToolsClient
from vidbyte.tools.decorators import tool, vidbyte_tool
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.function_tool import FunctionTool
from vidbyte.lib.tools import ToolsFormatter
from vidbyte.tools.strategy_tool import StrategyTool
from vidbyte.tools.mixins import ToolMixin
from vidbyte.tools.registry import ToolRegistry
from vidbyte.tools.types import (
    ToolCall,
    ToolCallContext,
    ToolCallState,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
    ToolStatus,
)

__all__ = [
    "AgentTool",
    "BaseTool",
    "FunctionTool",
    "ToolCall",
    "ToolCallContext",
    "ToolCallState",
    "ToolExecutor",
    "ToolInput",
    "ToolLike",
    "ToolMixin",
    "ToolParameter",
    "ToolPermission",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "ToolStatus",
    "StrategyTool",
    "ToolsClient",
    "ToolsFormatter",
    "Tools",
    "ensure_tool",
    "ensure_tools",
    "tool",
    "vidbyte_tool",
]
