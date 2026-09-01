"""FILE: vidbyte/tools/continual_trace.py

PURPOSE: Defines the internal updateTrace tool used by the continual trace agent — the only model-visible tool for writing into a running continual trace artifact.
ROLE IN CODEBASE: Used by vidbyte.agents.continual_trace.ContinualTraceAgent. Depends on the public tool contracts and on vidbyte.lib.dataclasses.trace.TraceSchema/TraceField, including TraceField's optional nested fields/items shape.
ARCHITECTURE NOTE: UpdateTraceTool is a schema-scoped tool with one required trace object argument. Its JSON Schema and type validation walk a TraceField's declared fields/items recursively, but its merge policy stays exactly one level deep regardless of nesting: array fields append with exact-duplicate dedupe, object fields are shallow-merged one key at a time (never recursively), and scalar fields are replaced outright. A nested array declared inside an OBJECT field's fields is therefore still fully replaced, not appended to, every time that OBJECT field is touched — nesting changes what shape is validated and shown to the model, not how a value merges across calls.
COMMON MODIFICATION PATTERNS: Change validation and JSON Schema rendering together in _first_shape_error/_json_schema_for_field, since both walk the same TraceField tree. Never change _merge_field's shallow-object/append-array policy to "fix" nested accumulation — instead move the field that needs to accumulate to its own top-level ARRAY field, per skills/vidbyte-sdk/continual-tracing.md.
KNOWN EDGE CASES: An OBJECT field's undeclared subfields, or an ARRAY field's elements when items is None, are validated only at the outer type check and pass through to merge untouched, matching the top-level "unknown keys are dropped at merge, not at validation" policy.
RELATED DOCS: docs/design/nested-continual-trace-shapes.md, docs/design/continual-trace-agent.md, skills/vidbyte-sdk/continual-tracing.md
TESTS: tests/test_continual_trace.py, scripts/test-continual-trace.py
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.lib.dataclasses.trace import TraceField, TraceFieldType, TraceSchema
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolResult, ToolSpec


UPDATE_TRACE_TOOL_NAME = "updateTrace"

_TOOL_DESCRIPTION = (
    "A continual trace is a structured, incrementally-updated artifact that records what a "
    "running agent is doing — its goal, the actions it has taken, any mistakes it made, and its "
    "current status. It is built up across multiple passes as the agent works, so each call to "
    "this tool adds to the record rather than replacing it. "
    "Use this tool to write your observations about the main agent's context window into the "
    "trace artifact. You must call it exactly once per response. "
    "The update merges into the existing artifact using these rules: array fields are appended "
    "(new items are added after existing ones; exact duplicates are skipped), object fields are "
    "shallow-merged (your keys overwrite matching keys, other keys are kept), and scalar fields "
    "are replaced outright. Fields you omit are left unchanged from the prior value. Only "
    "fields declared in the schema are accepted; any extra keys are silently dropped. Some "
    "object and array fields declare their own nested subfields or item shape below — that "
    "nested shape only tells you what to write, it does not change the merge rule above; a "
    "nested array inside an object field is still replaced whole, not appended to, whenever you "
    "resend that object field."
)

_TRACE_PARAM_DESCRIPTION = (
    "The trace fields you want to update. You may include any subset of the declared "
    "schema fields. Omitted fields keep their current value. Do not include keys that "
    "are not in the schema."
)


class UpdateTraceTool(BaseTool):
    """Tool used by ContinualTraceAgent to accept and merge trace artifact updates."""

    def __init__(self, schema: TraceSchema, initial_trace: Mapping[str, Any] | None = None) -> None:
        # Seeds the accepted artifact from the schema and any prior trace values.
        self.schema = schema
        self._trace = self._merge_known_fields(schema.initial_artifact(), initial_trace or {})
        self.last_error: str | None = None

    def spec(self) -> ToolSpec:
        # Returns the model-facing updateTrace declaration and compact prompt metadata.
        return ToolSpec(
            name=UPDATE_TRACE_TOOL_NAME,
            description=_TOOL_DESCRIPTION,
            parameters=(
                ToolParameter(
                    name="trace",
                    type="object",
                    description=_TRACE_PARAM_DESCRIPTION,
                    required=True,
                ),
            ),
            input_schema=self._input_schema(),
            metadata={"internal": True, "trace_schema": self.schema.name},
        )

    def validate_call(self, call: ToolCall) -> str | None:
        # Records validation errors produced before execute() can inspect arguments.
        error = super().validate_call(call)
        if error:
            self.last_error = error
        return error

    async def execute(self, call: ToolCall) -> ToolResult:
        # Validates the model-provided trace object and merges it into the stored artifact.
        raw_trace = call.arguments.get("trace")
        if not isinstance(raw_trace, Mapping):
            self.last_error = "trace argument must be an object"
            return ToolResult.error(UPDATE_TRACE_TOOL_NAME, "trace argument must be an object.", metadata={"error": "invalid_trace_argument"})
        type_error = self._first_type_error(raw_trace)
        if type_error is not None:
            self.last_error = type_error
            return ToolResult.error(UPDATE_TRACE_TOOL_NAME, f"output shape mismatch: {type_error}", metadata={"error": "trace_shape_mismatch", "detail": type_error})
        self._trace = self._merge_known_fields(self._trace, raw_trace)
        self.last_error = None
        return ToolResult.success(UPDATE_TRACE_TOOL_NAME, json.dumps(self._trace, sort_keys=True, default=str), metadata={"trace": self.current_trace()})

    def current_trace(self) -> dict[str, Any]:
        # Returns a serializable copy of the latest accepted trace artifact.
        return dict(self._trace)

    def _input_schema(self) -> dict[str, Any]:
        # Builds a provider-native JSON Schema for the typed updateTrace argument, recursing into declared nested shape.
        properties = {field_name: self._json_schema_for_field(spec) for field_name, spec in self.schema.fields.items()}
        return {
            "type": "object",
            "properties": {
                "trace": {
                    "type": "object",
                    "description": _TRACE_PARAM_DESCRIPTION,
                    "properties": properties,
                    "additionalProperties": False,
                }
            },
            "required": ["trace"],
            "additionalProperties": False,
        }

    def _json_schema_for_field(self, spec: TraceField) -> dict[str, Any]:
        # Renders one TraceField as JSON Schema, recursing into its declared fields/items when present.
        schema: dict[str, Any] = {"type": spec.type.value, "description": spec.description}
        if spec.type is TraceFieldType.OBJECT and spec.fields:
            schema["properties"] = {name: self._json_schema_for_field(sub) for name, sub in spec.fields.items()}
            schema["additionalProperties"] = False
        if spec.type is TraceFieldType.ARRAY and spec.items is not None:
            schema["items"] = self._json_schema_for_field(spec.items)
        return schema

    def _first_type_error(self, update: Mapping[str, Any]) -> str | None:
        # Returns the first declared-field value whose shape violates its schema, or None.
        for field_name, spec in self.schema.fields.items():
            if field_name not in update or update[field_name] is None:
                continue
            error = self._first_shape_error(update[field_name], spec, field_name)
            if error is not None:
                return error
        return None

    def _first_shape_error(self, value: Any, spec: TraceField, path: str) -> str | None:
        # Recursively checks one value against a TraceField's leaf type and, when declared, its nested fields/items.
        if not self._value_matches_type(value, spec.type):
            return f"{path} expected {spec.type.value}"
        if spec.type is TraceFieldType.OBJECT and spec.fields:
            for sub_name, sub_spec in spec.fields.items():
                if sub_name not in value or value[sub_name] is None:
                    continue
                error = self._first_shape_error(value[sub_name], sub_spec, f"{path}.{sub_name}")
                if error is not None:
                    return error
        if spec.type is TraceFieldType.ARRAY and spec.items is not None:
            for index, element in enumerate(value):
                error = self._first_shape_error(element, spec.items, f"{path}[{index}]")
                if error is not None:
                    return error
        return None

    @staticmethod
    def _value_matches_type(value: Any, field_type: TraceFieldType) -> bool:
        # Checks one JSON-like value against a declared trace field's own leaf type.
        if field_type is TraceFieldType.ARRAY:
            return isinstance(value, Sequence) and not isinstance(value, (str, bytes))
        if field_type is TraceFieldType.OBJECT:
            return isinstance(value, Mapping)
        if field_type is TraceFieldType.BOOLEAN:
            return isinstance(value, bool)
        if field_type is TraceFieldType.INTEGER:
            return isinstance(value, int) and not isinstance(value, bool)
        if field_type is TraceFieldType.NUMBER:
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        return isinstance(value, str)

    def _merge_known_fields(self, base: Mapping[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
        # Merges only declared schema fields, appending arrays and shallow-merging objects one level deep.
        merged = {field_name: base.get(field_name) for field_name in self.schema.fields}
        for field_name, spec in self.schema.fields.items():
            if field_name not in update:
                continue
            merged[field_name] = self._merge_field(spec, merged.get(field_name), update[field_name])
        return merged

    def _merge_field(self, spec: TraceField, previous: Any, incoming: Any) -> Any:
        # Applies the per-type merge policy for a single field value; object merges never recurse past one level.
        if incoming is None:
            return previous
        if spec.type is TraceFieldType.ARRAY:
            return self._append_unique(previous, incoming)
        if spec.type is TraceFieldType.OBJECT:
            base = dict(previous) if isinstance(previous, Mapping) else {}
            base.update(dict(incoming))
            return base
        return incoming

    @staticmethod
    def _append_unique(previous: Any, incoming: Any) -> list[Any]:
        # Appends incoming array items to the prior list, skipping exact duplicates.
        result = list(previous) if isinstance(previous, list) else ([] if previous is None else [previous])
        for item in list(incoming):
            if item not in result:
                result.append(item)
        return result


__all__ = [
    "UPDATE_TRACE_TOOL_NAME",
    "UpdateTraceTool",
]
