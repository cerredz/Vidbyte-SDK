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

from vidbyte.lib.errors import ToolRegistryError
from vidbyte.tools.registry import ToolRegistry
from vidbyte.tools.security import PermissionDecision, PermissionPolicy
from vidbyte.tools.types import ToolCall, ToolResult


class ToolExecutor:
    """Executes registered tool calls under a permission policy."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        permission_policy: PermissionPolicy | None = None,
    ) -> None:
        """Store the registry and policy used for future calls."""
        self.registry = registry
        self.permission_policy = permission_policy or PermissionPolicy()

    async def execute_call(self, call: ToolCall) -> ToolResult:
        """Resolve, authorize, validate, and run one tool call."""
        try:
            tool = self.registry.get(call.tool_name)
        except ToolRegistryError as exc:
            return ToolResult.error(call.tool_name, str(exc), metadata={"error": "unknown_tool"})

        spec = tool.spec()
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
