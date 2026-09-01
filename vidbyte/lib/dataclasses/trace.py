"""FILE: vidbyte/lib/dataclasses/trace.py

PURPOSE: Defines the user-visible continual trace schema and configuration contracts, including TraceField's nested subfield/item shape and the recursive builder that fills it from a pydantic model.
ROLE IN CODEBASE: Consumed by vidbyte/trace/continual/{agent,middleware}.py, rendered into a model-facing JSON Schema by vidbyte/tools/continual_trace.py, and re-exported by vidbyte.trace and vidbyte.__init__ for public use.
ARCHITECTURE NOTE: TraceMode/TraceFieldType/TraceField/TraceSchema/TraceOption are configuration contracts only; none of them execute a trace update. TraceField.fields/.items let an OBJECT/ARRAY field declare a nested shape recursively, validated and depth-capped once, on TraceField itself, so every construction path (from_model, a raw mapping, or direct construction) is provably within bounds.
COMMON MODIFICATION PATTERNS: Add a new leaf TraceFieldType by extending _annotation_to_type. Add a new way to declare nested shape by extending _field_from_annotation, keeping the depth cap and OBJECT/ARRAY-only validation on TraceField itself rather than duplicating it in the builder.
KNOWN EDGE CASES: A plain dict[str, Any] or list[dict[str, Any]] annotation still maps to an opaque OBJECT/ARRAY with fields/items left None — only a nested BaseModel (or list[BaseModel]) annotation triggers the recursive builder. A list[SubModel] item's description falls back to a generated string when SubModel has no docstring.
RELATED DOCS: docs/design/nested-continual-trace-shapes.md, docs/design/continual-trace-agent.md, skills/vidbyte-sdk/continual-tracing.md
TESTS: tests/test_continual_trace.py, scripts/test-continual-trace.py
"""

from __future__ import annotations

import typing
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, model_validator

from vidbyte.lib.constants.trace import MAX_TRACE_FIELD_NESTING_DEPTH

_ROOT_FIELD_DEPTH = 1
_CHILD_DEPTH_STEP = 1


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
    """Typed description object for one continual trace field, optionally declaring its own nested subfield or item shape."""

    description: str
    type: TraceFieldType = TraceFieldType.STRING
    fields: Mapping[str, "TraceField"] | None = None
    items: "TraceField | None" = None

    @model_validator(mode="after")
    def _validate_shape(self) -> "TraceField":
        # Normalizes the description and enforces the OBJECT/ARRAY-only nesting contract and depth cap.
        stripped = self.description.strip() if isinstance(self.description, str) else ""
        if not stripped:
            raise ValueError("TraceField.description cannot be empty")
        self.description = stripped
        if self.fields is not None and self.type is not TraceFieldType.OBJECT:
            raise ValueError("TraceField.fields is only valid when type is OBJECT")
        if self.items is not None and self.type is not TraceFieldType.ARRAY:
            raise ValueError("TraceField.items is only valid when type is ARRAY")
        if self._nesting_depth() > MAX_TRACE_FIELD_NESTING_DEPTH:
            raise ValueError(f"TraceField nesting exceeds the maximum depth of {MAX_TRACE_FIELD_NESTING_DEPTH}")
        return self

    def _nesting_depth(self) -> int:
        # Returns the height of this field's own declared shape tree, counting itself as depth 1.
        child_depths = [sub._nesting_depth() for sub in (self.fields or {}).values()]
        if self.items is not None:
            child_depths.append(self.items._nesting_depth())
        return 1 + max(child_depths, default=0)


TraceField.model_rebuild()


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
        # Builds a typed TraceSchema from a pydantic model, recursing into nested submodels for their declared shape.
        fields = cls._fields_from_model(model, depth=_ROOT_FIELD_DEPTH)
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
        # Accepts a plain description string, a mapping, or a TraceField and returns a validated TraceField.
        if isinstance(value, TraceField):
            return value
        if isinstance(value, str):
            return TraceField(description=value)
        if isinstance(value, Mapping):
            return TraceField(**value)
        raise ValueError(f"TraceSchema field {name!r} must be a description string, mapping, or TraceField")

    @classmethod
    def _fields_from_model(cls, model: type[BaseModel], *, depth: int) -> dict[str, TraceField]:
        # Builds one TraceField per pydantic field, recursing into nested BaseModel/list[BaseModel] annotations.
        fields: dict[str, TraceField] = {}
        for field_name, info in model.model_fields.items():
            field_description = (info.description or "").strip()
            if not field_description:
                raise ValueError(f"TraceSchema field {field_name!r} must have a pydantic Field(description=...)")
            fields[field_name] = cls._field_from_annotation(info.annotation, field_description, depth=depth)
        return fields

    @classmethod
    def _field_from_annotation(cls, annotation: Any, description: str, *, depth: int) -> TraceField:
        # Builds one typed TraceField from a pydantic annotation, recursing into a nested submodel's own fields.
        origin = typing.get_origin(annotation)
        target = origin if origin is not None else annotation
        if isinstance(target, type) and issubclass(target, BaseModel):
            return TraceField(description=description, type=TraceFieldType.OBJECT, fields=cls._fields_from_model(target, depth=depth + _CHILD_DEPTH_STEP))
        if origin in (list, tuple, set, frozenset):
            item_field = cls._item_field_from_args(typing.get_args(annotation), depth=depth)
            return TraceField(description=description, type=TraceFieldType.ARRAY, items=item_field)
        return TraceField(description=description, type=cls._annotation_to_type(annotation))

    @classmethod
    def _item_field_from_args(cls, args: tuple[Any, ...], *, depth: int) -> TraceField | None:
        # Returns a nested item shape only when the list's single type argument is itself a submodel.
        if not args:
            return None
        item_type = args[0]
        item_origin = typing.get_origin(item_type)
        item_target = item_origin if item_origin is not None else item_type
        if not (isinstance(item_target, type) and issubclass(item_target, BaseModel)):
            return None
        item_description = (item_target.__doc__ or "").strip() or f"One entry in this list, each describing a single {item_target.__name__} record."
        return TraceField(description=item_description, type=TraceFieldType.OBJECT, fields=cls._fields_from_model(item_target, depth=depth + _CHILD_DEPTH_STEP))

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
