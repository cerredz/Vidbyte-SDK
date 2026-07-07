"""Context Protocol Header

Description:
    Defines simple universal settings for agent tool usage.
Purpose:
    Gives AgentLoopSettings a validated nested object for denied tools, tool-call
    budgets, per-tool budgets, and model-visible result bounds.
Architecture:
    - ToolSettings: Plain class with eager normalization and validation.
Relations:
    Used by vidbyte.agents.settings.loop and ToolSettingsMiddleware.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from vidbyte.lib.errors import ConfigurationError


class ToolSettings:
    """Validated settings for simple universal tool-use constraints."""

    def __init__(self, *, denied_tools: Iterable[str] = (), max_calls: int | None = None, max_calls_per_tool: Mapping[str, int] | None = None, result_max_chars: int | None = None) -> None:
        # Normalizes developer-provided tool policy values before validation.
        self.denied_tools = self._normalize_tool_names(denied_tools, "denied_tools")
        self.max_calls = max_calls
        self.max_calls_per_tool = self._normalize_call_limits(max_calls_per_tool)
        self.result_max_chars = result_max_chars
        self._validate()

    def _validate(self) -> None:
        # Raises ConfigurationError for numeric constraints that would be impossible to enforce.
        self.max_calls = self._normalize_int(self.max_calls, "max_calls", minimum=1)
        self.result_max_chars = self._normalize_int(self.result_max_chars, "result_max_chars", minimum=0)

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
            limit = cls._normalize_int(raw_limit, f"max_calls_per_tool[{name!r}]", minimum=1)
            limits[name] = limit
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
        pairs = ", ".join(f"{key}={value!r}" for key, value in fields.items())
        return f"ToolSettings({pairs})"


__all__ = ["ToolSettings"]
