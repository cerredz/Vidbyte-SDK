"""Context Protocol Header

Description:
    Enforces settings-driven universal tool-use constraints.
Purpose:
    Applies ToolSettings denied tools, call budgets, per-tool budgets, and
    model-visible result truncation without requiring manual middleware setup.
Architecture:
    - ToolSettingsMiddleware: Runtime enforcement middleware.
    - _ToolSettingsRunState: Per-run tool execution counters.
Relations:
    Auto-registered by BaseAgent when AgentLoopSettings.tool_settings is present.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vidbyte.agents.settings import ToolSettings
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision, MiddlewareTransform
from vidbyte.lib.dataclasses.tools import ToolResult
from vidbyte.middleware.base import AgentMiddleware
from vidbyte.tools._internal import IS_DONE_TOOL_NAME

_MIDDLEWARE_DENIED = "middleware_denied"


@dataclass
class _ToolSettingsRunState:
    # Tracks executed tool calls by tool name for one agent run.
    calls_by_tool: dict[str, int] = field(default_factory=dict)


class ToolSettingsMiddleware(AgentMiddleware):
    """Apply ToolSettings as deterministic runtime policy."""

    def __init__(self, settings: ToolSettings) -> None:
        # Stores validated settings; per-run counters live in MiddlewareContext.run_state.
        self.settings = settings

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Initializes fresh per-run counters for tool-settings enforcement.
        ctx.run_state[self.__class__] = _ToolSettingsRunState()
        return MiddlewareDecision.continue_()

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Blocks denied or over-budget tool calls before local execution.
        if ctx.tool_call is None:
            return MiddlewareDecision.continue_()
        name = ctx.tool_call.tool_name
        if self._is_internal_done(ctx):
            return MiddlewareDecision.continue_()
        if name in self.settings.denied_tools:
            return MiddlewareDecision.deny_tool("tool_settings_denied", metadata={"tool_name": name})
        if self.settings.max_calls is not None and ctx.tool_call_count >= self.settings.max_calls:
            return MiddlewareDecision.abort("tool_settings_max_calls", metadata={"tool_name": name, "max_calls": self.settings.max_calls})
        state = self._state_for(ctx)
        limit = self.settings.max_calls_per_tool.get(name)
        current = state.calls_by_tool.get(name, 0)
        if limit is not None and current >= limit:
            return MiddlewareDecision.deny_tool("tool_settings_max_calls_per_tool", metadata={"tool_name": name, "max_calls_per_tool": limit, "current_calls": current})
        return MiddlewareDecision.continue_()

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Records completed tool calls and optionally truncates their model-visible result.
        if ctx.tool_call is None or ctx.tool_result is None:
            return MiddlewareDecision.continue_()
        if not self._is_internal_done(ctx) and not self._is_middleware_denied(ctx.tool_result):
            self._record_completed_call(ctx)
        if self.settings.result_max_chars is None or ctx.tool_is_internal:
            return MiddlewareDecision.continue_()
        visible = self._truncated_result(ctx.tool_result)
        if visible is ctx.tool_result:
            return MiddlewareDecision.continue_()
        transform = MiddlewareTransform(model_visible_tool_result=visible, metadata={"tool_settings_truncated": True})
        return MiddlewareDecision.continue_(transform=transform)

    def _state_for(self, ctx: MiddlewareContext) -> _ToolSettingsRunState:
        # Returns the current run state or creates one for direct hook-level calls.
        state = ctx.run_state.get(self.__class__)
        if not isinstance(state, _ToolSettingsRunState):
            state = _ToolSettingsRunState()
            ctx.run_state[self.__class__] = state
        return state

    def _record_completed_call(self, ctx: MiddlewareContext) -> None:
        # Increments the per-tool counter after a call has reached a non-denied result.
        state = self._state_for(ctx)
        name = ctx.tool_call.tool_name if ctx.tool_call else ""
        state.calls_by_tool[name] = state.calls_by_tool.get(name, 0) + 1

    def _truncated_result(self, result: ToolResult) -> ToolResult:
        # Returns a model-visible result capped to result_max_chars, preserving raw runtime state.
        max_chars = self.settings.result_max_chars
        if max_chars is None or len(result.output) <= max_chars:
            return result
        omitted = len(result.output) - max_chars
        suffix = f"\n...[tool output truncated by ToolSettings: omitted {omitted} characters]"
        return ToolResult(
            tool_name=result.tool_name,
            status=result.status,
            output=result.output[:max_chars] + suffix,
            metadata={
                **dict(result.metadata),
                "tool_settings_truncated": True,
                "original_chars": len(result.output),
                "visible_chars": max_chars,
                "truncated_chars": omitted,
            },
        )

    @staticmethod
    def _is_internal_done(ctx: MiddlewareContext) -> bool:
        # Keeps the runtime completion tool available even if a denylist contains its name.
        return ctx.tool_is_internal and ctx.tool_call is not None and ctx.tool_call.tool_name == IS_DONE_TOOL_NAME

    @staticmethod
    def _is_middleware_denied(result: ToolResult) -> bool:
        # Detects middleware-denied results so denied attempts do not consume execution budgets.
        return str(dict(result.metadata).get("error", "")).strip().lower() == _MIDDLEWARE_DENIED


__all__ = ["ToolSettingsMiddleware"]
