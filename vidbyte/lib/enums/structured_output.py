"""Context Protocol Header

Description:
    Defines structured output mode selection for agent final responses.
Purpose:
    Gives callers an explicit policy for native provider schemas versus prompt fallback.
Architecture:
    - StructuredOutputMode: Small enum with coercion for public agent configuration.
Relations:
    Used by BaseAgent and AgentRuntime when output_schema is declared.
"""

from __future__ import annotations

from enum import Enum

from vidbyte.lib.errors import ConfigurationError


class StructuredOutputMode(str, Enum):
    """Controls how agents request schema-conformant final outputs."""

    AUTO = "auto"
    NATIVE = "native"
    PROMPT = "prompt"

    @classmethod
    def coerce(cls, value: "StructuredOutputMode | str | None") -> "StructuredOutputMode":
        # Normalizes user input into a supported structured output mode.
        if value is None:
            return cls.AUTO
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value))
        except ValueError as exc:
            raise ConfigurationError(f"Unsupported structured output mode: {value!r}") from exc


__all__ = ["StructuredOutputMode"]
