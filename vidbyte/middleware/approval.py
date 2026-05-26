"""Context Protocol Header

Description:
    Approval-gating middleware that blocks high-risk tool calls until
    a human explicitly approves them.
Purpose:
    Lets developers require manual approval for destructive or expensive
    tool calls (e.g. git push, shell, browser_act) before execution.
Architecture:
    - Approvals are tracked per tool name in a pending dict.
    - before_tool_call checks the set of approval-required tool names.
    - approve() and deny() set the pending flag for the next call.
    - Default approval list covers EXECUTE-level tools by name pattern.
Relations:
    Extends vidbyte.middleware.base.AgentMiddleware.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware


class ApprovalMiddleware(AgentMiddleware):
    """Gates tool execution behind human approval for high-risk operations."""

    DEFAULT_APPROVAL_TOOLS: frozenset[str] = frozenset({
        "git_push",
        "git_clone",
        "shell",
        "monitor_start",
        "browser_act",
        "generate_image",
        "verify_run_tests",
        "verify_run_lint",
    })

    def __init__(self, require_approval_for: set[str] | None = None) -> None:
        self._approve_tools = require_approval_for or self.DEFAULT_APPROVAL_TOOLS
        self._pending_approvals: dict[str, bool] = {}

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Check if the current tool requires approval and has been granted."""
        if ctx.tool_call is None:
            return MiddlewareDecision.continue_()

        name = ctx.tool_call.tool_name
        if name not in self._approve_tools:
            return MiddlewareDecision.continue_()

        approved = self._pending_approvals.pop(name, None)
        if approved:
            return MiddlewareDecision.continue_(metadata={"approved": True})

        return MiddlewareDecision.deny_tool(
            f"Tool '{name}' requires human approval. Call approve('{name}') first.",
            metadata={"tool_name": name, "requires_approval": True},
        )

    def approve(self, tool_name: str) -> None:
        """Pre-approve the next call to a given tool name."""
        self._pending_approvals[tool_name] = True

    def deny(self, tool_name: str) -> None:
        """Explicitly deny the next call to a given tool name."""
        self._pending_approvals[tool_name] = False


__all__ = ["ApprovalMiddleware"]
