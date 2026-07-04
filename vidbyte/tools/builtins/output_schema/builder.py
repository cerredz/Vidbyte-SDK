"""Context Protocol Header

Description:
    Implements OutputSchemaBuilder — a runtime accumulator that lets an agent
    declare a structured output shape and append entries to it during a run.
Purpose:
    Backs the declare_output_schema / append_output tools so an agent can fill
    its window with exploration while the harness reads only a compressed,
    structured snapshot back out.
Architecture:
    - OutputSchemaField: One declared field (scalar or repeated list).
    - OutputSchemaBuilder: Live registry of declared fields and their values.
Relations:
    Consumed by DeclareOutputSchemaTool and AppendOutputTool, and read by
    paradigm harnesses that map snapshots into typed artifacts.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class OutputSchemaField:
    """One field the agent declared it will emit in its structured output."""

    name: str
    description: str = ""
    repeated: bool = False


class OutputSchemaBuilder:
    """Runtime accumulator for an agent-declared output schema."""

    def __init__(self) -> None:
        # Holds declared fields in insertion order plus their accumulated values.
        self._fields: dict[str, OutputSchemaField] = {}
        self._values: dict[str, Any] = {}
        self._implicit = False

    def declare(self, fields: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
        # Registers the declared fields and initializes storage for each.
        declared: list[str] = []
        for raw in fields:
            field = self._coerce_field(raw)
            if field is None:
                continue
            self._register(field)
            declared.append(field.name)
        return tuple(declared)

    def append(self, field_name: str, value: Any) -> str:
        # Appends to a repeated field or sets a scalar field, auto-declaring if unknown.
        name = field_name.strip()
        if not name:
            return "Ignored append with an empty field name."
        field = self._fields.get(name)
        if field is None:
            field = OutputSchemaField(name=name, description="", repeated=True)
            self._register(field)
            self._implicit = True
        coerced = self._coerce_value(value)
        if field.repeated:
            self._values[name].append(coerced)
            return f"Appended one entry to '{name}' (now {len(self._values[name])})."
        self._values[name] = coerced
        return f"Set field '{name}'."

    def snapshot(self) -> dict[str, Any]:
        # Returns a serializable view of declared fields and accumulated values.
        return {
            "fields": [
                {"name": f.name, "description": f.description, "repeated": f.repeated}
                for f in self._fields.values()
            ],
            "values": {name: self._copy_value(value) for name, value in self._values.items()},
            "implicit": self._implicit,
        }

    def is_declared(self) -> bool:
        # Reports whether the agent has declared any fields yet.
        return bool(self._fields)

    def is_empty(self) -> bool:
        # Reports whether no values have been accumulated.
        return not any(self._values.values())

    def _register(self, field: OutputSchemaField) -> None:
        # Stores a field declaration and seeds its value slot when new.
        self._fields[field.name] = field
        if field.name not in self._values:
            self._values[field.name] = [] if field.repeated else None

    @staticmethod
    def _coerce_field(raw: Mapping[str, Any] | str) -> OutputSchemaField | None:
        # Normalizes a declared field from a mapping or a bare string name.
        if isinstance(raw, str):
            name = raw.strip()
            return OutputSchemaField(name=name) if name else None
        if isinstance(raw, Mapping):
            name = str(raw.get("name", "")).strip()
            if not name:
                return None
            return OutputSchemaField(
                name=name,
                description=str(raw.get("description", "")).strip(),
                repeated=bool(raw.get("repeated", False)),
            )
        return None

    @staticmethod
    def _coerce_value(value: Any) -> Any:
        # Parses JSON-looking strings into objects, otherwise returns the value as-is.
        if isinstance(value, str):
            text = value.strip()
            if text[:1] in ("{", "[") :
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return value
            return value
        return value

    @staticmethod
    def _copy_value(value: Any) -> Any:
        # Returns a shallow copy of list values so snapshots do not alias state.
        if isinstance(value, list):
            return list(value)
        return value


__all__ = [
    "OutputSchemaBuilder",
    "OutputSchemaField",
]
