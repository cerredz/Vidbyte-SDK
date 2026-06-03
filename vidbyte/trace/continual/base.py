"""Context Protocol Header

Description:
    Implements continual trace capture settings and lifecycle recording.
Purpose:
    Keeps continual tracing logic isolated for future memory/context feedback work.
Architecture:
    - ContinualTracer: DebugTracer subclass with validated continual memory settings.
Relations:
    Used by vidbyte.trace.Trace.continual.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from vidbyte.lib.errors import ConfigurationError
from vidbyte.trace.debug import DebugTracer

_SUPPORTED_CONTINUAL_MEMORY = frozenset(("model_calls", "tool_calls", "failures", "outputs", "decisions"))


class ContinualTracer(DebugTracer):
    """Configurable in-memory tracer for future continual context feedback."""

    def __init__(self, remember: Sequence[str], *, max_memory_chars: int = 1200, redact: bool = True, events: list[dict[str, Any]] | None = None) -> None:
        self.remember = _ContinualTraceSettings.validate_remember(remember)
        self.max_memory_chars = _ContinualTraceSettings.validate_max_memory_chars(max_memory_chars)
        self.redact = bool(redact)
        super().__init__(events=events)


class _ContinualTraceSettings:
    """Validation helpers for continual trace capture settings."""

    @staticmethod
    def validate_remember(remember: Sequence[str]) -> tuple[str, ...]:
        if isinstance(remember, str) or not remember:
            raise ConfigurationError("Trace.continual() requires a non-empty remember sequence.")
        normalized: list[str] = []
        for item in remember:
            if item not in _SUPPORTED_CONTINUAL_MEMORY:
                raise ConfigurationError(f"Unsupported continual trace memory category: {item}.")
            if item not in normalized:
                normalized.append(item)
        return tuple(normalized)

    @staticmethod
    def validate_max_memory_chars(max_memory_chars: int) -> int:
        if isinstance(max_memory_chars, bool) or not isinstance(max_memory_chars, int):
            raise ConfigurationError("Trace.continual() max_memory_chars must be an integer.")
        if max_memory_chars <= 0:
            raise ConfigurationError("Trace.continual() max_memory_chars must be greater than zero.")
        return max_memory_chars


__all__ = ["ContinualTracer"]
