"""
FILE: vidbyte/tools/adapters.py

PURPOSE:
    Normalizes supported tool-like objects into BaseTool instances.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/tools layer, which owns top-level tool contracts, catalogs, adapters, decorators, and execution helpers.
    It should be read with `vidbyte/tools/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.tools.base: imported by this file.
    - vidbyte.tools.function_tool: imported by this file.

FUNCTION INVENTORY:
    - ensure_tool (function): public or navigational symbol owned here.
    - ensure_tools (function): public or navigational symbol owned here.

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
    - TypeError: raised, returned, or imported by this file. Keep context safe and grepable.

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

from collections.abc import Callable, Iterable
from typing import Any, TypeAlias

from vidbyte.tools.base import BaseTool
from vidbyte.tools.function_tool import FunctionTool

ToolInput: TypeAlias = BaseTool | Callable[..., Any]


def ensure_tool(tool: ToolInput) -> BaseTool:
    """Normalize native tools, decorated tools, and raw callables to BaseTool."""
    if isinstance(tool, BaseTool):
        return tool
    if callable(tool):
        return FunctionTool.from_function(tool)
    raise TypeError(f"Expected a BaseTool or callable, got {type(tool).__name__}.")


def ensure_tools(tools: Iterable[ToolInput]) -> tuple[BaseTool, ...]:
    return tuple(ensure_tool(tool) for tool in tools)

