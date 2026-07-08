"""Context Protocol Header

Description:
    Defines simple universal settings for agent tool usage.
Purpose:
    Gives AgentLoopSettings a validated nested object for denied tools, tool-call
    budgets, per-tool budgets, and model-visible result bounds, and owns the pure
    decision logic the direct runtime calls to enforce them.
Architecture:
    - ToolSettings: Stateless settings + decision object (denial, truncate).
Relations:
    Used by vidbyte.agents.settings.loop, carried on AgentRuntimeConfig, and
    enforced inline by vidbyte.agents.runtime.AgentRuntime.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from vidbyte.lib.dataclasses.tools import ToolResult
from vidbyte.lib.errors import ConfigurationError

_ON_DENY_CHOICES = ("continue", "abort")


class ToolSettings:
    """Validated, stateless settings and decision logic for universal tool-use constraints."""

    def __init__(self, *, denied_tools: Iterable[str] = (), max_calls: int | None = None, max_calls_per_tool: Mapping[str, int] | None = None, result_max_chars: int | None = None, on_deny: str = "continue") -> None:
        # Normalizes developer-provided tool policy values before validation.
        self.denied_tools = self._normalize_tool_names(denied_tools, "denied_tools")
        self.max_calls = max_calls
        self.max_calls_per_tool = self._normalize_call_limits(max_calls_per_tool)
        self.result_max_chars = result_max_chars
        self.on_deny = on_deny
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

    @property
    def aborts_on_deny(self) -> bool:
        # Reports whether a denial should stop the run rather than continue in-context.
        return self.on_deny == "abort"

    def _validate(self) -> None:
        # Raises ConfigurationError for numeric and policy constraints that cannot be enforced.
        self.max_calls = self._normalize_int(self.max_calls, "max_calls", minimum=1)
        self.result_max_chars = self._normalize_int(self.result_max_chars, "result_max_chars", minimum=0)
        if self.on_deny not in _ON_DENY_CHOICES:
            raise ConfigurationError(f"ToolSettings.on_deny must be one of {_ON_DENY_CHOICES}, got {self.on_deny!r}.")

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
        pairs = ", ".join(f"{key}={value!r}" for key, value in fields.items())
        return f"ToolSettings({pairs})"


__all__ = ["ToolSettings"]
