"""Context Protocol Header

Description:
    Implements the standard tool execution pipeline.
Purpose:
    Centralizes lookup, permission checks, call validation, async execution, and
    exception normalization so concrete tools stay focused on domain logic.
Architecture:
    - ToolExecutor: Resolves ToolCall objects and returns ToolResult objects.
Relations:
    Related to vidbyte.tools.registry, vidbyte.tools.security, and built-in tools.
"""

from __future__ import annotations

import json
import re

from typing import TYPE_CHECKING
from vidbyte.lib.dataclasses.tools import ToolErrorKind
from vidbyte.lib.errors import McpToolExecutionError, ToolRegistryError
from vidbyte.tools.catalog import Tools
from vidbyte.tools.errors import ToolError, ToolErrorNormalizer
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
            return ToolResult.error(call.tool_name, str(exc), metadata={"error": ToolErrorKind.UNKNOWN_TOOL.value})

        spec = tool.spec()
        normalizer = ToolErrorNormalizer(spec)
        decision = self.permission_policy.check(spec, call)
        if decision is PermissionDecision.DENY:
            return ToolResult.error(
                spec.name,
                f"Permission denied for tool '{spec.name}' requiring {spec.permission.value}",
                metadata={"error": ToolErrorKind.PERMISSION_DENIED.value, "permission": spec.permission.value},
            )

        validation_error = tool.validate_call(call)
        if validation_error:
            return normalizer.from_validation_error(spec.name, validation_error)

        try:
            return await tool.execute(call)
        except ToolError as exc:
            return normalizer.from_tool_error(spec.name, exc)
        except McpToolExecutionError as exc:
            return normalizer.from_mcp_tool_execution_error(spec.name, exc)
        except Exception as exc:  # pragma: no cover - exact concrete failures vary.
            return normalizer.from_plain_exception(spec.name, exc)

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
