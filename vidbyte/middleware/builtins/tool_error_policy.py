"""Context Protocol Header

Description:
    Provides retry, circuit-break, and rendering policy for failed tool calls.
Purpose:
    Lets agent loops silently retry transient idempotent tool errors while
    surfacing terminal errors with policy-selected provider render options.
Architecture:
    - ToolErrorPolicyMiddleware: Classifies tool errors and returns retry,
      abort, or continue decisions.
    - _ToolErrorPolicyRunState: Per-run counters stored in MiddlewareContext.run_state.
Relations:
    Used by BaseAgent when AgentLoopSettings.tool_error_policy is configured.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.agents.settings import ToolErrorPolicy, UnrecoverableAction
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision, MiddlewareTransform
from vidbyte.lib.dataclasses.tools import ToolStatus
from vidbyte.middleware.base import AgentMiddleware

_DENIED_ERROR_KINDS = frozenset(("middleware_denied", "permission_denied"))
_IDEMPOTENT_PERMISSIONS = frozenset(("safe", "read"))


@dataclass
class _ToolErrorPolicyRunState:
    # Tracks failed tool-call counts within a single agent run.
    retry_attempts: dict[str, int] = field(default_factory=dict)
    total_errors: int = 0


class ToolErrorPolicyMiddleware(AgentMiddleware):
    """Apply retry, abort, and render-option policy to failed tool calls."""

    def __init__(self, policy: ToolErrorPolicy) -> None:
        # Stores the validated policy; per-run counters live in ctx.run_state.
        self.policy = policy

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Initializes fresh counters for one run.
        ctx.run_state[self.__class__] = _ToolErrorPolicyRunState()
        return MiddlewareDecision.continue_()

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Chooses whether a failed tool call should retry, abort, or continue to the model.
        if ctx.tool_call is None or ctx.tool_result is None or ctx.tool_result.status is not ToolStatus.ERROR:
            return MiddlewareDecision.continue_()
        state = self._state_for(ctx)
        kind = self._error_kind(ctx.tool_result.metadata)
        retryable = self._retryable(ctx.tool_result.metadata)
        state.total_errors += 1
        if self._circuit_breaker_tripped(state):
            return self._abort_for_circuit(ctx, kind, state)
        if self._should_retry(ctx, kind, retryable, state):
            return self._retry_decision(ctx, kind, state)
        if self.policy.on_unrecoverable is UnrecoverableAction.ABORT_RUN:
            return self._abort_for_unrecoverable(ctx, kind, state)
        return self._continue_with_render_options(kind, state)

    def _state_for(self, ctx: MiddlewareContext) -> _ToolErrorPolicyRunState:
        # Returns existing run state or creates it for direct hook-level tests.
        state = ctx.run_state.get(self.__class__)
        if not isinstance(state, _ToolErrorPolicyRunState):
            state = _ToolErrorPolicyRunState()
            ctx.run_state[self.__class__] = state
        return state

    def _should_retry(self, ctx: MiddlewareContext, kind: str, retryable: bool | None, state: _ToolErrorPolicyRunState) -> bool:
        # Checks kind, retryable flag, idempotency, and remaining budget.
        if self.policy.max_retries_per_tool_call <= 0:
            return False
        if kind in _DENIED_ERROR_KINDS:
            return False
        if kind not in self.policy.retry_on:
            return False
        if retryable is False:
            return False
        if not self._tool_permission_allows_retry(ctx):
            return False
        return state.retry_attempts.get(self._call_key(ctx), 0) < self.policy.max_retries_per_tool_call

    def _retry_decision(self, ctx: MiddlewareContext, kind: str, state: _ToolErrorPolicyRunState) -> MiddlewareDecision:
        # Increments attempt state and returns a retry decision with backoff metadata.
        key = self._call_key(ctx)
        attempt = state.retry_attempts.get(key, 0) + 1
        state.retry_attempts[key] = attempt
        delay = self._compute_delay(attempt)
        return MiddlewareDecision.retry(
            "tool_error_retry",
            sleep_seconds=delay,
            metadata={
                "tool_name": ctx.tool_call.tool_name if ctx.tool_call else None,
                "error": kind,
                "attempt": attempt,
                "max_retries_per_tool_call": self.policy.max_retries_per_tool_call,
                "delay_seconds": delay,
            },
        )

    def _continue_with_render_options(self, kind: str, state: _ToolErrorPolicyRunState) -> MiddlewareDecision:
        # Continues the run while handing formatter options to the runtime.
        return MiddlewareDecision.continue_(
            metadata={"tool_error": kind, "total_tool_errors": state.total_errors},
            transform=MiddlewareTransform(metadata={"tool_error_render_options": self.policy.to_render_options()}),
        )

    def _abort_for_circuit(self, ctx: MiddlewareContext, kind: str, state: _ToolErrorPolicyRunState) -> MiddlewareDecision:
        # Aborts once the configured total tool-error circuit breaker trips.
        return MiddlewareDecision.abort(
            "tool_error_circuit_break",
            metadata={
                "tool_name": ctx.tool_call.tool_name if ctx.tool_call else None,
                "error": kind,
                "total_tool_errors": state.total_errors,
                "max_total_tool_errors": self.policy.max_total_tool_errors,
            },
        )

    def _abort_for_unrecoverable(self, ctx: MiddlewareContext, kind: str, state: _ToolErrorPolicyRunState) -> MiddlewareDecision:
        # Aborts on terminal errors when the policy says not to continue.
        return MiddlewareDecision.abort(
            "tool_error_unrecoverable",
            metadata={
                "tool_name": ctx.tool_call.tool_name if ctx.tool_call else None,
                "error": kind,
                "total_tool_errors": state.total_errors,
            },
        )

    def _circuit_breaker_tripped(self, state: _ToolErrorPolicyRunState) -> bool:
        # Returns True when cumulative tool errors reach the configured limit.
        return self.policy.max_total_tool_errors is not None and state.total_errors >= self.policy.max_total_tool_errors

    def _tool_permission_allows_retry(self, ctx: MiddlewareContext) -> bool:
        # Enforces the idempotency gate using runtime-provided tool permission metadata.
        if not self.policy.retry_only_idempotent:
            return True
        permission = str(dict(ctx.metadata or {}).get("tool_permission", "")).lower()
        return permission in _IDEMPOTENT_PERMISSIONS

    def _compute_delay(self, attempt: int) -> float:
        # Computes capped exponential backoff for the retry attempt number.
        raw = self.policy.retry_backoff_base_seconds * (self.policy.retry_backoff_multiplier ** max(0, attempt - 1))
        return min(self.policy.retry_backoff_cap_seconds, raw)

    def _call_key(self, ctx: MiddlewareContext) -> str:
        # Builds a stable per-tool-call key from id when present, otherwise name and arguments.
        if ctx.tool_call is None:
            return "unknown"
        if ctx.tool_call.call_id:
            return ctx.tool_call.call_id
        try:
            args = json.dumps(dict(ctx.tool_call.arguments), sort_keys=True, default=str)
        except TypeError:
            args = str(dict(ctx.tool_call.arguments))
        return f"{ctx.tool_call.tool_name}:{args}"

    @staticmethod
    def _error_kind(metadata: object) -> str:
        # Reads the structured error kind with compatibility fallbacks for current metadata strings.
        data = dict(metadata or {}) if isinstance(metadata, Mapping) else {}
        raw = str(data.get("error") or data.get("error_type") or "execution_error").strip().lower()
        aliases = {"validation": "invalid_arguments", "validation_error": "invalid_arguments"}
        return aliases.get(raw, raw or "execution_error")

    @staticmethod
    def _retryable(metadata: object) -> bool | None:
        # Converts retryable metadata into a bool while preserving unspecified values.
        data = dict(metadata or {}) if isinstance(metadata, Mapping) else {}
        raw = data.get("retryable")
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            lowered = raw.strip().lower()
            if lowered in {"true", "1", "yes"}:
                return True
            if lowered in {"false", "0", "no"}:
                return False
        return None


__all__ = ["ToolErrorPolicyMiddleware"]
