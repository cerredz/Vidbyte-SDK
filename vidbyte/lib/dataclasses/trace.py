"""Context Protocol Header

Description:
    Defines user-visible continual trace schema and configuration contracts.
Purpose:
    Keeps trace artifact configuration separate from observability tracers while
    giving agents a stable, typed option object for continual trace updates.
Architecture:
    - TraceMode: Supported trace execution modes.
    - TraceFieldType: JSON-like value types a single trace field can hold.
    - TraceField: Pydantic description object carrying a typed field description.
    - TraceSchema: Ordered typed field descriptions for JSON-like trace artifacts.
    - TraceOption: Agent constructor option for continual tracing.
Relations:
    Re-exported by vidbyte.trace and consumed by the continual trace middleware/agent.
"""

from __future__ import annotations

import typing
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class TraceMode(str, Enum):
    """Supported trace execution modes."""

    CONTINUAL = "continual"


class TraceFieldType(str, Enum):
    """JSON-like value types a single trace field can hold."""

    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


class TraceField(BaseModel):
    """Typed description object for one continual trace field."""

    model_config = ConfigDict(extra="forbid")

    description: str
    type: TraceFieldType = TraceFieldType.STRING


@dataclass(frozen=True, slots=True)
class TraceSchema:
    """Ordered schema of typed field descriptions for a JSON-like trace artifact."""

    name: str
    fields: Mapping[str, TraceField] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        # Validates and normalizes the schema name and typed field descriptions.
        normalized_name = self.name.strip() if isinstance(self.name, str) else ""
        if not normalized_name:
            raise ValueError("TraceSchema.name cannot be empty")
        normalized_fields = self._normalized_fields(self.fields)
        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "fields", normalized_fields)
        object.__setattr__(self, "description", self.description.strip() if isinstance(self.description, str) else "")

    @classmethod
    def coerce(cls, raw: "TraceSchema | type[BaseModel] | Mapping[str, Any]") -> "TraceSchema":
        # Converts pydantic models or mapping schemas into named TraceSchema instances.
        if isinstance(raw, TraceSchema):
            return raw
        if isinstance(raw, type) and issubclass(raw, BaseModel):
            return cls.from_model(raw)
        if isinstance(raw, Mapping):
            return cls(name="custom_trace", fields=raw, description="Custom continual trace schema.")
        raise TypeError("trace schema must be a TraceSchema, a pydantic BaseModel subclass, or a mapping of field names to descriptions")

    @classmethod
    def from_model(cls, model: type[BaseModel], *, name: str | None = None, description: str | None = None) -> "TraceSchema":
        # Builds a typed TraceSchema from a pydantic model using each field's description and annotation.
        fields: dict[str, TraceField] = {}
        for field_name, info in model.model_fields.items():
            field_description = (info.description or "").strip()
            if not field_description:
                raise ValueError(f"TraceSchema field {field_name!r} must have a pydantic Field(description=...)")
            fields[field_name] = TraceField(description=field_description, type=cls._annotation_to_type(info.annotation))
        schema_name = (name or model.__name__).strip()
        schema_description = description if description is not None else (model.__doc__ or "").strip()
        return cls(name=schema_name, fields=fields, description=schema_description)

    def initial_artifact(self) -> dict[str, Any]:
        # Returns a complete empty artifact keyed by every declared schema field.
        return {field_name: None for field_name in self.fields}

    def describe_fields(self) -> str:
        # Renders typed field descriptions for trace-agent prompts.
        return "\n".join(f"- {name} ({spec.type.value}): {spec.description}" for name, spec in self.fields.items())

    @classmethod
    def _normalized_fields(cls, fields: Mapping[str, Any]) -> dict[str, TraceField]:
        # Validates schema fields while preserving caller-provided insertion order.
        if not isinstance(fields, Mapping) or not fields:
            raise ValueError("TraceSchema.fields must contain at least one field")
        normalized: dict[str, TraceField] = {}
        for raw_name, raw_value in fields.items():
            name = raw_name.strip() if isinstance(raw_name, str) else ""
            if not name:
                raise ValueError("TraceSchema field names cannot be empty")
            normalized[name] = cls._normalize_field_value(name, raw_value)
        return normalized

    @staticmethod
    def _normalize_field_value(name: str, value: Any) -> TraceField:
        # Accepts a plain description string, a mapping, or a TraceField and returns a TraceField.
        if isinstance(value, TraceField):
            field_obj = value
        elif isinstance(value, str):
            field_obj = TraceField(description=value)
        elif isinstance(value, Mapping):
            field_obj = TraceField(**value)
        else:
            raise ValueError(f"TraceSchema field {name!r} must be a description string, mapping, or TraceField")
        if not field_obj.description.strip():
            raise ValueError(f"TraceSchema field {name!r} must have a description")
        return field_obj.model_copy(update={"description": field_obj.description.strip()})

    @staticmethod
    def _annotation_to_type(annotation: Any) -> TraceFieldType:
        # Maps a Python type annotation onto the closest JSON-like trace field type.
        origin = typing.get_origin(annotation)
        target = origin if origin is not None else annotation
        if isinstance(target, type):
            if issubclass(target, bool):
                return TraceFieldType.BOOLEAN
            if issubclass(target, int):
                return TraceFieldType.INTEGER
            if issubclass(target, float):
                return TraceFieldType.NUMBER
            if issubclass(target, str):
                return TraceFieldType.STRING
            if issubclass(target, (list, tuple, set, frozenset)):
                return TraceFieldType.ARRAY
            if issubclass(target, Mapping):
                return TraceFieldType.OBJECT
        return TraceFieldType.STRING


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
        if isinstance(self.every_n_iterations, bool) or not isinstance(self.every_n_iterations, int) or self.every_n_iterations <= 0:
            raise ValueError("TraceOption.every_n_iterations must be a positive integer")
        if isinstance(self.max_trace_iterations, bool) or not isinstance(self.max_trace_iterations, int) or self.max_trace_iterations < 1 or self.max_trace_iterations > 3:
            raise ValueError("TraceOption.max_trace_iterations must be between 1 and 3")

    @classmethod
    def continual(cls, schema: TraceSchema | type[BaseModel] | Mapping[str, Any], *, every_n_iterations: int = 5, max_trace_iterations: int = 3) -> "TraceOption":
        # Builds a validated continual trace option from a schema, pydantic model, or field mapping.
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
    "TraceFieldType",
    "TraceField",
    "TraceOption",
    "TraceSchema",
]
