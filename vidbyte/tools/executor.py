"""
FILE: vidbyte/tools/executor.py

PURPOSE:
    Implements the standard tool execution pipeline. Centralizes lookup, permission checks, call validation, async execution, and exception normalization so concrete tools stay focused on domain logic.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/tools layer, which owns top-level tool contracts, catalogs, adapters, decorators, and execution helpers.
    It should be read with `vidbyte/tools/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.lib.errors: imported by this file.
    - vidbyte.tools.catalog: imported by this file.
    - vidbyte.tools.security: imported by this file.
    - vidbyte.tools.types: imported by this file.

FUNCTION INVENTORY:
    - ToolExecutor (class): public or navigational symbol owned here.

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
    - JSONDecodeError: raised, returned, or imported by this file. Keep context safe and grepable.
    - ToolRegistryError: raised, returned, or imported by this file. Keep context safe and grepable.

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

import json
import re

from typing import TYPE_CHECKING
from vidbyte.lib.errors import ToolRegistryError
from vidbyte.tools.catalog import Tools
from vidbyte.tools.security import PermissionDecision, PermissionPolicy
from vidbyte.tools.types import ToolCall, ToolResult

if TYPE_CHECKING:
    from vidbyte.lib.registries.tools import ToolRegistry


class ToolExecutor:
    """Executes registered tool calls under a permission policy."""

    def __init__(
        self,
        registry: ToolRegistry | Tools,
        *,
        permission_policy: PermissionPolicy | None = None,
    ) -> None:
        """Store the registry and policy used for future calls."""
        self.registry = registry
        self.permission_policy = permission_policy or PermissionPolicy()

    async def execute_call(self, call: ToolCall) -> ToolResult:
        """Resolve, authorize, validate, and run one tool call."""
        try:
            get_tool = getattr(self.registry, "get", None)
            tool = get_tool(call.tool_name) if callable(get_tool) else self.registry._get(call.tool_name)
        except ToolRegistryError as exc:
            return ToolResult.error(call.tool_name, str(exc), metadata={"error": "unknown_tool"})

        spec = tool.spec()
        # Authorize before schema validation so denied calls cannot use validation messages as an oracle.
        decision = self.permission_policy.check(spec, call)
        if decision is PermissionDecision.DENY:
            return ToolResult.error(
                spec.name,
                f"Permission denied for tool '{spec.name}' requiring {spec.permission.value}",
                metadata={"error": "permission_denied", "permission": spec.permission.value},
            )

        validation_error = tool.validate_call(call)
        if validation_error:
            return ToolResult.error(
                spec.name,
                validation_error,
                metadata={"error": "validation_error"},
            )

        try:
            return await tool.execute(call)
        except Exception as exc:  # pragma: no cover - exact concrete failures vary.
            return ToolResult.error(
                spec.name,
                f"Tool execution failed: {exc}",
                metadata={"error": "execution_error", "error_type": type(exc).__name__},
            )

    async def execute(self, text: str) -> ToolResult:
        """Parse an Action/Action Input block from text and execute the named tool."""
        action_match = re.search(r"Action:\s*(\S+)", text)
        if not action_match:
            return ToolResult.error("unknown", "No Action block found in text.")
        tool_name = action_match.group(1).strip()

        input_match = re.search(r"Action Input:\s*(\{.*?\})", text, re.DOTALL)
        try:
            arguments = json.loads(input_match.group(1).strip()) if input_match else {}
        except json.JSONDecodeError:
            arguments = {}

        return await self.execute_call(ToolCall(tool_name=tool_name, arguments=arguments))
