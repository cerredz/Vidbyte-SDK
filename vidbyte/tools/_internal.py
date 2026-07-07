"""
FILE: vidbyte/tools/_internal.py

PURPOSE:
    Owns  internal behavior inside the vidbyte/tools layer.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/tools layer, which owns top-level tool contracts, catalogs, adapters, decorators, and execution helpers.
    It should be read with `vidbyte/tools/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.tools.base: imported by this file.
    - vidbyte.tools.catalog: imported by this file.
    - vidbyte.tools.types: imported by this file.

FUNCTION INVENTORY:
    - IsDoneTool (class): public or navigational symbol owned here.
    - with_internal_agent_tools (function): public or navigational symbol owned here.
    - IS_DONE_TOOL_NAME (export): public or navigational symbol owned here.
    - IsDoneTool (export): public or navigational symbol owned here.
    - with_internal_agent_tools (export): public or navigational symbol owned here.

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
    - None observed in this file; preserve this when adding new failure paths.

RELATED DOCS:
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/system_prompt.md: source prompt for the agentic-engineering principles applied to this file.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md: file-header anatomy used for this header.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/function_design.md: function design guidance for future edits.
    - docs/design/agentic-engineering-principles-agents-middleware-tools.md: design record for this documentation pass.

TESTS:
    - python -m compileall vidbyte; tests/test_custom_function_tools.py and tool-related scripts when changing tool behavior.

CONCURRENCY MODEL:
    - Review async/task state carefully; this file participates in agent, middleware, tool, or actor execution.
"""

from __future__ import annotations

from vidbyte.tools.base import BaseTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


IS_DONE_TOOL_NAME = "isDone"


class IsDoneTool(BaseTool):
    """Internal loop-control tool used by agents to stop runtime execution."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=IS_DONE_TOOL_NAME,
            description="Call this when you are done with the problem; this is how you stop the loop.",
            parameters=(
                ToolParameter(
                    name="final_answer",
                    type="string",
                    description="Final answer or completion message to return from the agent loop.",
                    required=False,
                    default="",
                ),
            ),
            permission=ToolPermission.SAFE,
            metadata={"internal": True},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        output = str(call.arguments.get("final_answer") or call.arguments.get("answer") or "Done.")
        return ToolResult.success(IS_DONE_TOOL_NAME, output, metadata={"done": True})


def with_internal_agent_tools(tools: Tools) -> Tools:
    """Return a runtime-only catalog with internal loop-control tools included."""
    return tools.add(IsDoneTool(), replace=True)


__all__ = [
    "IS_DONE_TOOL_NAME",
    "IsDoneTool",
    "with_internal_agent_tools",
]
