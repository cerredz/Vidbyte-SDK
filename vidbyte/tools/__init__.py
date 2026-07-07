"""
FILE: vidbyte/tools/__init__.py

PURPOSE:
    Exports the public tool contracts and namespace client. Gives SDK users stable imports for implementing, registering, and executing native or bridged tools.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/tools layer, which owns top-level tool contracts, catalogs, adapters, decorators, and execution helpers.
    It should be read with `vidbyte/tools/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.lib.tools: imported by this file.
    - vidbyte.tools.adapters: imported by this file.
    - vidbyte.tools.agent_tool: imported by this file.
    - vidbyte.tools.base: imported by this file.
    - vidbyte.tools.catalog: imported by this file.
    - vidbyte.tools.client: imported by this file.
    - vidbyte.tools.decorators: imported by this file.
    - vidbyte.tools.executor: imported by this file.

FUNCTION INVENTORY:
    - AgentTool (export): public or navigational symbol owned here.
    - BaseTool (export): public or navigational symbol owned here.
    - FunctionTool (export): public or navigational symbol owned here.
    - ToolCall (export): public or navigational symbol owned here.
    - ToolCallContext (export): public or navigational symbol owned here.
    - ToolCallState (export): public or navigational symbol owned here.
    - ToolExecutor (export): public or navigational symbol owned here.
    - ToolInput (export): public or navigational symbol owned here.
    - ToolLike (export): public or navigational symbol owned here.
    - ToolMixin (export): public or navigational symbol owned here.
    - ToolParameter (export): public or navigational symbol owned here.
    - ToolPermission (export): public or navigational symbol owned here.
    - ToolRegistry (export): public or navigational symbol owned here.
    - ToolResult (export): public or navigational symbol owned here.
    - ToolSpec (export): public or navigational symbol owned here.
    - ToolStatus (export): public or navigational symbol owned here.
    - ToolsClient (export): public or navigational symbol owned here.
    - ToolsFormatter (export): public or navigational symbol owned here.
    - Tools (export): public or navigational symbol owned here.
    - ensure_tool (export): public or navigational symbol owned here.
    - ensure_tools (export): public or navigational symbol owned here.
    - tool (export): public or navigational symbol owned here.
    - vidbyte_tool (export): public or navigational symbol owned here.

COMMON MODIFICATION PATTERNS:
    - When adding or removing a public symbol, update this header, the local `__all__` if present, and the nearest folder README file index.
    - When changing runtime behavior, update related docs or examples that describe the same contract before opening a PR.
    - When adding a new failure path, keep the error message safe for logs and include enough context for a future agent to route the fix.

WHAT NOT TO DO IN THIS FILE:
    1. Do not move responsibilities across SDK layers without updating the corresponding folder README and public exports.
    2. Do not add provider credentials, API keys, or unredacted prompt payloads to errors, metadata, traces, or comments.
    3. Do not edit generated cache files or make unrelated refactors while touching this file.

KNOWN EDGE CASES:
    - This SDK is in alpha and several files preserve compatibility exports; check `README.md` and `vidbyte/__init__.py` before renaming public symbols.
    - Agentic headers are living documentation. Re-run a header/code cross-check after changing imports, exports, errors, or concurrency behavior.

COMMON ERRORS RAISED BY THIS FILE:
    - AttributeError: raised, returned, or imported by this file. Keep context safe and grepable.

RELATED DOCS:
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/system_prompt.md: source prompt for the agentic-engineering principles applied to this file.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md: file-header anatomy used for this header.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/function_design.md: function design guidance for future edits.
    - docs/design/agentic-engineering-principles-agents-middleware-tools.md: design record for this documentation pass.

TESTS:
    - python -m compileall vidbyte; tests/test_custom_function_tools.py and tool-related scripts when changing tool behavior.

CONCURRENCY MODEL:
    - No explicit concurrency primitive; keep future mutable state local to calls unless documented here.
"""
from __future__ import annotations

from typing import Any

from vidbyte.tools.adapters import ToolInput, ensure_tool, ensure_tools
from vidbyte.tools.agent_tool import AgentTool
from vidbyte.tools.base import BaseTool, ToolLike
from vidbyte.tools.catalog import Tools
from vidbyte.tools.client import ToolsClient
from vidbyte.tools.decorators import tool, vidbyte_tool
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.function_tool import FunctionTool
from vidbyte.lib.tools import ToolsFormatter
from vidbyte.tools.mixins import ToolMixin
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
    "ToolsClient",
    "ToolsFormatter",
    "Tools",
    "ensure_tool",
    "ensure_tools",
    "tool",
    "vidbyte_tool",
]


def __getattr__(name: str) -> Any:
    if name == "ToolRegistry":
        from vidbyte.lib.registries.tools import ToolRegistry

        return ToolRegistry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
