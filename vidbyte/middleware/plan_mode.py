"""Context Protocol Header

Description:
    Middleware that blocks WRITE and EXECUTE tools when plan mode is active.
Purpose:
    Enforces read-only constraints during planning, allowing only READ and
    SAFE tool calls until plan mode is explicitly exited.
Architecture:
    - PlanModeMiddleware: Tracks plan_active state, denies blocked tools
      during before_tool_call hook.
Relations:
    Used through vidbyte.middleware.builtins and AgentRuntime before_tool_call.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware

_WRITE_TOOL_NAMES: frozenset[str] = frozenset({
    "bash",
    "edit",
    "write",
    "patch",
    "delete",
    "commit",
    "push",
    "clone",
    "shell",
    "git_commit",
    "git_push",
    "git_clone",
    "git_add",
    "git_branch_create",
    "git_checkout",
    "http_post",
    "http_put",
    "http_delete",
    "browser_click",
    "browser_type",
    "browser_act",
    "generate_image",
})


class PlanModeMiddleware(AgentMiddleware):
    """Blocks WRITE and EXECUTE tools when plan mode is active."""

    def __init__(self) -> None:
        self._plan_active = False

    @property
    def plan_active(self) -> bool:
        return self._plan_active

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        if ctx.tool_call is None:
            return MiddlewareDecision.continue_()

        tool_name = ctx.tool_call.tool_name

        if tool_name == "enter_plan_mode":
            self._plan_active = True
            return MiddlewareDecision.continue_()
        if tool_name == "exit_plan_mode":
            self._plan_active = False
            return MiddlewareDecision.continue_()

        if not self._plan_active:
            return MiddlewareDecision.continue_()

        if tool_name in _WRITE_TOOL_NAMES:
            return MiddlewareDecision.deny_tool(
                "Plan mode is active. Only READ and SAFE tools are allowed. Use exit_plan_mode to begin implementation.",
                metadata={"tool_name": tool_name},
            )

        return MiddlewareDecision.continue_()


__all__ = ["PlanModeMiddleware"]
