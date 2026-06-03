"""Context Protocol Header

Description:
    Defines user-visible continual trace schema and configuration contracts.
Purpose:
    Keeps trace artifact configuration separate from observability tracers while
    giving agents a stable option object for continual trace updates.
Architecture:
    - TraceMode: Supported trace execution modes.
    - TraceSchema: Ordered field descriptions for JSON-like trace artifacts.
    - TraceOption: Agent constructor option for continual tracing.
Relations:
    Re-exported by vidbyte.trace and consumed by vidbyte.agents runtime wiring.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TraceMode(str, Enum):
    """Supported trace execution modes."""

    CONTINUAL = "continual"


@dataclass(frozen=True, slots=True)
class TraceSchema:
    """Ordered schema for a JSON-like continual trace artifact."""

    name: str
    fields: Mapping[str, str] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        # Validates and normalizes schema names and field descriptions.
        normalized_name = self.name.strip() if isinstance(self.name, str) else ""
        if not normalized_name:
            raise ValueError("TraceSchema.name cannot be empty")
        normalized_fields = self._normalized_fields(self.fields)
        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "fields", normalized_fields)
        object.__setattr__(self, "description", self.description.strip())

    @classmethod
    def coerce(cls, raw: "TraceSchema | Mapping[str, str]") -> "TraceSchema":
        # Converts mapping schemas into named TraceSchema instances.
        if isinstance(raw, TraceSchema):
            return raw
        if isinstance(raw, Mapping):
            return cls(name="custom_trace", fields=raw, description="Custom continual trace schema.")
        raise TypeError("trace schema must be a TraceSchema or a mapping of field names to descriptions")

    def initial_artifact(self) -> dict[str, Any]:
        # Returns a complete empty artifact keyed by every declared schema field.
        return {field_name: None for field_name in self.fields}

    def describe_fields(self) -> str:
        # Renders field descriptions for trace-agent prompts.
        return "\n".join(f"- {name}: {description}" for name, description in self.fields.items())

    @staticmethod
    def _normalized_fields(fields: Mapping[str, str]) -> dict[str, str]:
        # Validates schema fields while preserving caller-provided insertion order.
        if not isinstance(fields, Mapping) or not fields:
            raise ValueError("TraceSchema.fields must contain at least one field")
        normalized: dict[str, str] = {}
        for raw_name, raw_description in fields.items():
            name = raw_name.strip() if isinstance(raw_name, str) else ""
            description = raw_description.strip() if isinstance(raw_description, str) else ""
            if not name:
                raise ValueError("TraceSchema field names cannot be empty")
            if not description:
                raise ValueError(f"TraceSchema field {name!r} must have a description")
            normalized[name] = description
        return normalized


@dataclass(frozen=True, slots=True)
class TraceOption:
    """Agent constructor option for trace artifact generation."""

    mode: TraceMode
    schema: TraceSchema
    every_n_iterations: int = 5
    max_trace_iterations: int = 3

    def __post_init__(self) -> None:
        # Validates interval and bounded trace-agent iteration settings.
        if not isinstance(self.mode, TraceMode):
            object.__setattr__(self, "mode", TraceMode(self.mode))
        object.__setattr__(self, "schema", TraceSchema.coerce(self.schema))
        if self.every_n_iterations <= 0:
            raise ValueError("TraceOption.every_n_iterations must be greater than zero")
        if self.max_trace_iterations < 1 or self.max_trace_iterations > 3:
            raise ValueError("TraceOption.max_trace_iterations must be between 1 and 3")

    @classmethod
    def continual(cls, schema: TraceSchema | Mapping[str, str], *, every_n_iterations: int = 5, max_trace_iterations: int = 3) -> "TraceOption":
        # Builds a validated continual trace option from a schema or field mapping.
        return cls(
            mode=TraceMode.CONTINUAL,
            schema=TraceSchema.coerce(schema),
            every_n_iterations=every_n_iterations,
            max_trace_iterations=max_trace_iterations,
        )

    @property
    def enabled(self) -> bool:
        # Returns whether this option should activate trace runtime behavior.
        return self.mode is TraceMode.CONTINUAL

    @property
    def is_continual(self) -> bool:
        # Returns whether this option uses the continual trace mode.
        return self.mode is TraceMode.CONTINUAL


__all__ = [
    "TraceMode",
    "TraceOption",
    "TraceSchema",
]
