"""Context Protocol Header

Description:
    Defines simple universal settings for agent tool usage.
Purpose:
    Gives AgentLoopSettings a validated nested object for denied tools, tool-call
    budgets, per-tool budgets, model-visible result bounds, thrash/failure budgets,
    per-call timeouts, and sliding-window limits, and owns the pure decision logic
    the direct runtime calls to enforce them.
Architecture:
    - ToolSettings: Stateless settings + decision object (denial, truncate, budgets).
Relations:
    Used by vidbyte.agents.settings.loop, carried on AgentRuntimeConfig, and
    enforced inline by vidbyte.agents.runtime.AgentRuntime.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from vidbyte.lib.dataclasses.tools import ToolCallContext, ToolCallState, ToolResult, fingerprint_tool_call
from vidbyte.lib.errors import ConfigurationError

_ON_DENY_CHOICES = ("continue", "abort")
_INTERNAL_DONE_TOOL_NAME = "isDone"
_BUDGET_REASON_MAX_CALLS_PER_ITERATION = "max_calls_per_iteration"
_BUDGET_REASON_MAX_IDENTICAL_CALLS = "max_identical_calls"
_BUDGET_REASON_SLIDING_WINDOW = "sliding_window_max_calls"
_BUDGET_REASON_MAX_CONSECUTIVE_FAILURES = "max_consecutive_failures"
_BUDGET_REASON_MAX_ERROR_CALLS = "max_error_calls"


class ToolSettings:
    """Validated, stateless settings and decision logic for universal tool-use constraints."""

    def __init__(self, *, denied_tools: Iterable[str] = (), max_calls: int | None = None, max_calls_per_tool: Mapping[str, int] | None = None, result_max_chars: int | None = None, on_deny: str = "continue", max_calls_per_iteration: int | None = None, max_identical_calls: int | None = None, max_consecutive_failures: int | None = None, max_error_calls: int | None = None, tool_timeout_seconds: float | None = None, sliding_window_max_calls: int | None = None, sliding_window_iterations: int | None = None) -> None:
        # Normalizes developer-provided tool policy values before validation.
        self.denied_tools = self._normalize_tool_names(denied_tools, "denied_tools")
        self.max_calls = max_calls
        self.max_calls_per_tool = self._normalize_call_limits(max_calls_per_tool)
        self.result_max_chars = result_max_chars
        self.on_deny = on_deny
        self.max_calls_per_iteration = max_calls_per_iteration
        self.max_identical_calls = max_identical_calls
        self.max_consecutive_failures = max_consecutive_failures
        self.max_error_calls = max_error_calls
        self.tool_timeout_seconds = tool_timeout_seconds
        self.sliding_window_max_calls = sliding_window_max_calls
        self.sliding_window_iterations = sliding_window_iterations
        self._validate()

    def denial(self, tool_name: str, executed_counts: Mapping[str, int]) -> tuple[str, dict] | None:
        # Returns (reason, metadata) when a call must be blocked, else None. Pure and stateless.
        if tool_name in self.denied_tools:
            return "tool_settings_denied", {"tool_name": tool_name}
        limit = self.max_calls_per_tool.get(tool_name)
        if limit is not None and executed_counts.get(tool_name, 0) >= limit:
            return "tool_settings_max_calls_per_tool", {"tool_name": tool_name, "max_calls_per_tool": limit, "current_calls": executed_counts.get(tool_name, 0)}
        return None

    def truncate(self, result: ToolResult) -> ToolResult:
        # Returns a model-visible result capped to result_max_chars; callers keep the raw ToolResult.
        if self.result_max_chars is None or len(result.output) <= self.result_max_chars:
            return result
        omitted = len(result.output) - self.result_max_chars
        suffix = f"\n...[tool output truncated by ToolSettings: omitted {omitted} characters]"
        return ToolResult(
            tool_name=result.tool_name,
            status=result.status,
            output=result.output[: self.result_max_chars] + suffix,
            metadata={
                **dict(result.metadata),
                "tool_settings_truncated": True,
                "original_chars": len(result.output),
                "visible_chars": self.result_max_chars,
                "truncated_chars": omitted,
            },
        )

    def fingerprint(self, tool_name: str, arguments: Mapping[str, object] | None) -> str:
        # Builds a stable tool-name + args fingerprint used by identical-call budgets.
        return fingerprint_tool_call(tool_name, dict(arguments or {}))

    def budget_stop(self, *, tool_name: str, arguments: Mapping[str, object] | None, call_contexts: Sequence[ToolCallContext], iteration_count: int) -> tuple[str, dict] | None:
        # Returns (reason, metadata) when a pre-exec hard budget is exceeded; pure and stateless.
        countable = self._countable_contexts(call_contexts)
        per_iteration = self._per_iteration_budget_stop(countable, iteration_count)
        if per_iteration is not None:
            return per_iteration
        sliding = self._sliding_window_budget_stop(countable, iteration_count)
        if sliding is not None:
            return sliding
        return self._identical_call_budget_stop(tool_name, arguments, countable)

    def failure_budget_stop(self, call_contexts: Sequence[ToolCallContext]) -> tuple[str, dict] | None:
        # Returns (reason, metadata) when consecutive or total failure budgets are exceeded.
        countable = self._countable_contexts(call_contexts)
        consecutive = self._consecutive_failure_budget_stop(countable)
        if consecutive is not None:
            return consecutive
        return self._total_error_budget_stop(countable)

    @property
    def aborts_on_deny(self) -> bool:
        # Reports whether a denial should stop the run rather than continue in-context.
        return self.on_deny == "abort"

    def _per_iteration_budget_stop(self, contexts: Sequence[ToolCallContext], iteration_count: int) -> tuple[str, dict] | None:
        # Hard-stops when non-denied non-internal calls in the current iteration already hit the cap.
        if self.max_calls_per_iteration is None:
            return None
        current = sum(1 for ctx in contexts if ctx.iteration_count == iteration_count)
        if current < self.max_calls_per_iteration:
            return None
        return (
            _BUDGET_REASON_MAX_CALLS_PER_ITERATION,
            {
                "max_calls_per_iteration": self.max_calls_per_iteration,
                "current_calls": current,
                "iteration_count": iteration_count,
            },
        )

    def _sliding_window_budget_stop(self, contexts: Sequence[ToolCallContext], iteration_count: int) -> tuple[str, dict] | None:
        # Hard-stops when non-denied non-internal calls in the last K iterations hit the window cap.
        if self.sliding_window_max_calls is None or self.sliding_window_iterations is None:
            return None
        window_start = max(1, iteration_count - self.sliding_window_iterations + 1)
        current = sum(
            1
            for ctx in contexts
            if ctx.iteration_count is not None and window_start <= ctx.iteration_count <= iteration_count
        )
        if current < self.sliding_window_max_calls:
            return None
        return (
            _BUDGET_REASON_SLIDING_WINDOW,
            {
                "sliding_window_max_calls": self.sliding_window_max_calls,
                "sliding_window_iterations": self.sliding_window_iterations,
                "current_calls": current,
                "iteration_count": iteration_count,
                "window_start": window_start,
            },
        )

    def _identical_call_budget_stop(self, tool_name: str, arguments: Mapping[str, object] | None, contexts: Sequence[ToolCallContext]) -> tuple[str, dict] | None:
        # Hard-stops when the same tool+args fingerprint already appears max_identical_calls times.
        if self.max_identical_calls is None:
            return None
        candidate = self.fingerprint(tool_name, arguments)
        current = sum(1 for ctx in contexts if self.fingerprint(ctx.tool_name, dict(ctx.arguments)) == candidate)
        if current < self.max_identical_calls:
            return None
        return (
            _BUDGET_REASON_MAX_IDENTICAL_CALLS,
            {
                "max_identical_calls": self.max_identical_calls,
                "current_calls": current,
                "tool_name": tool_name,
                "fingerprint": candidate,
            },
        )

    def _consecutive_failure_budget_stop(self, contexts: Sequence[ToolCallContext]) -> tuple[str, dict] | None:
        # Hard-stops when the trailing streak of FAILED (countable) contexts reaches the limit.
        if self.max_consecutive_failures is None:
            return None
        streak = 0
        for ctx in reversed(contexts):
            if ctx.state is not ToolCallState.FAILED:
                break
            streak += 1
        if streak < self.max_consecutive_failures:
            return None
        return (
            _BUDGET_REASON_MAX_CONSECUTIVE_FAILURES,
            {
                "max_consecutive_failures": self.max_consecutive_failures,
                "current_streak": streak,
            },
        )

    def _total_error_budget_stop(self, contexts: Sequence[ToolCallContext]) -> tuple[str, dict] | None:
        # Hard-stops when total FAILED (countable) contexts reach max_error_calls.
        if self.max_error_calls is None:
            return None
        total = sum(1 for ctx in contexts if ctx.state is ToolCallState.FAILED)
        if total < self.max_error_calls:
            return None
        return (
            _BUDGET_REASON_MAX_ERROR_CALLS,
            {
                "max_error_calls": self.max_error_calls,
                "current_errors": total,
            },
        )

    @classmethod
    def _countable_contexts(cls, call_contexts: Sequence[ToolCallContext]) -> list[ToolCallContext]:
        # Filters out denied and internal tool contexts so budgets only count real executions.
        return [ctx for ctx in call_contexts if not cls._is_excluded_context(ctx)]

    @staticmethod
    def _is_excluded_context(ctx: ToolCallContext) -> bool:
        # Returns True for denied calls and internal tools that must not consume budgets.
        if ctx.state is ToolCallState.DENIED:
            return True
        if ctx.tool_name == _INTERNAL_DONE_TOOL_NAME:
            return True
        metadata = dict(ctx.metadata or {})
        return bool(metadata.get("internal"))

    def _validate(self) -> None:
        # Raises ConfigurationError for numeric and policy constraints that cannot be enforced.
        self.max_calls = self._normalize_int(self.max_calls, "max_calls", minimum=1)
        self.result_max_chars = self._normalize_int(self.result_max_chars, "result_max_chars", minimum=0)
        self.max_calls_per_iteration = self._normalize_int(self.max_calls_per_iteration, "max_calls_per_iteration", minimum=1)
        self.max_identical_calls = self._normalize_int(self.max_identical_calls, "max_identical_calls", minimum=1)
        self.max_consecutive_failures = self._normalize_int(self.max_consecutive_failures, "max_consecutive_failures", minimum=1)
        self.max_error_calls = self._normalize_int(self.max_error_calls, "max_error_calls", minimum=1)
        self.sliding_window_max_calls = self._normalize_int(self.sliding_window_max_calls, "sliding_window_max_calls", minimum=1)
        self.sliding_window_iterations = self._normalize_int(self.sliding_window_iterations, "sliding_window_iterations", minimum=1)
        self.tool_timeout_seconds = self._normalize_timeout(self.tool_timeout_seconds)
        if self.on_deny not in _ON_DENY_CHOICES:
            raise ConfigurationError(f"ToolSettings.on_deny must be one of {_ON_DENY_CHOICES}, got {self.on_deny!r}.")
        self._validate_sliding_window_pair()

    def _validate_sliding_window_pair(self) -> None:
        # Requires both sliding-window fields together so the window size is always defined.
        has_max = self.sliding_window_max_calls is not None
        has_iterations = self.sliding_window_iterations is not None
        if has_max == has_iterations:
            return
        raise ConfigurationError(
            "ToolSettings.sliding_window_max_calls and ToolSettings.sliding_window_iterations must both be set or both be omitted."
        )

    @classmethod
    def _normalize_tool_names(cls, values: Iterable[str], field_name: str) -> frozenset[str]:
        # Converts tool-name iterables into immutable stripped names.
        if isinstance(values, (str, bytes)):
            raise ConfigurationError(f"ToolSettings.{field_name} must be an iterable of tool names, not a string.")
        normalized = []
        for value in values:
            name = str(value).strip()
            if not name:
                raise ConfigurationError(f"ToolSettings.{field_name} cannot include blank tool names.")
            normalized.append(name)
        return frozenset(normalized)

    @classmethod
    def _normalize_call_limits(cls, values: Mapping[str, int] | None) -> dict[str, int]:
        # Converts per-tool call limits into a validated plain dictionary.
        limits: dict[str, int] = {}
        for raw_name, raw_limit in dict(values or {}).items():
            name = str(raw_name).strip()
            if not name:
                raise ConfigurationError("ToolSettings.max_calls_per_tool cannot include blank tool names.")
            limits[name] = cls._normalize_int(raw_limit, f"max_calls_per_tool[{name!r}]", minimum=1)
        return limits

    @staticmethod
    def _normalize_int(value: object, field_name: str, *, minimum: int) -> int | None:
        # Accepts only integer configuration values and enforces the requested lower bound.
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigurationError(f"ToolSettings.{field_name} must be an integer.")
        if value < minimum:
            bound = "non-negative" if minimum == 0 else f"greater than or equal to {minimum}"
            raise ConfigurationError(f"ToolSettings.{field_name} must be {bound}.")
        return value

    @staticmethod
    def _normalize_timeout(value: object) -> float | None:
        # Accepts positive int/float timeout seconds and rejects non-numeric or non-positive values.
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigurationError("ToolSettings.tool_timeout_seconds must be a number.")
        timeout = float(value)
        if timeout <= 0:
            raise ConfigurationError("ToolSettings.tool_timeout_seconds must be greater than zero when provided.")
        return timeout

    def __repr__(self) -> str:
        # Returns a compact developer-readable string showing only active settings.
        fields: dict[str, object] = {}
        if self.denied_tools:
            fields["denied_tools"] = tuple(sorted(self.denied_tools))
        if self.max_calls is not None:
            fields["max_calls"] = self.max_calls
        if self.max_calls_per_tool:
            fields["max_calls_per_tool"] = dict(self.max_calls_per_tool)
        if self.result_max_chars is not None:
            fields["result_max_chars"] = self.result_max_chars
        if self.on_deny != "continue":
            fields["on_deny"] = self.on_deny
        if self.max_calls_per_iteration is not None:
            fields["max_calls_per_iteration"] = self.max_calls_per_iteration
        if self.max_identical_calls is not None:
            fields["max_identical_calls"] = self.max_identical_calls
        if self.max_consecutive_failures is not None:
            fields["max_consecutive_failures"] = self.max_consecutive_failures
        if self.max_error_calls is not None:
            fields["max_error_calls"] = self.max_error_calls
        if self.tool_timeout_seconds is not None:
            fields["tool_timeout_seconds"] = self.tool_timeout_seconds
        if self.sliding_window_max_calls is not None:
            fields["sliding_window_max_calls"] = self.sliding_window_max_calls
        if self.sliding_window_iterations is not None:
            fields["sliding_window_iterations"] = self.sliding_window_iterations
        pairs = ", ".join(f"{key}={value!r}" for key, value in fields.items())
        return f"ToolSettings({pairs})"


__all__ = ["ToolSettings"]
