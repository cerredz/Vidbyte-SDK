"""
FILE: vidbyte/tools/continual_trace.py

PURPOSE:
    Defines the internal tool used by the continual trace agent. Provides one model-visible updateTrace function that validates trace updates against the schema and deterministically merges them (append for arrays, deep merge for objects, replace for scalars) into the accumulated artifact.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/tools layer, which owns top-level tool contracts, catalogs, adapters, decorators, and execution helpers.
    It should be read with `vidbyte/tools/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.lib.dataclasses.trace: imported by this file.
    - vidbyte.tools.base: imported by this file.
    - vidbyte.tools.types: imported by this file.

FUNCTION INVENTORY:
    - UpdateTraceTool (class): public or navigational symbol owned here.
    - UPDATE_TRACE_TOOL_NAME (export): public or navigational symbol owned here.
    - UpdateTraceTool (export): public or navigational symbol owned here.

COMMON MODIFICATION PATTERNS:
    - When adding or removing a public symbol, update this header, the local `__all__` if present, and the nearest folder README file index.
    - When changing runtime behavior, update related docs or examples that describe the same contract before opening a PR.
    - When adding a new failure path, keep the error message safe for logs and include enough context for a future agent to route the fix.

WHAT NOT TO DO IN THIS FILE:
    1. Do not move responsibilities across SDK layers without updating the corresponding folder README and public exports.
    2. Do not add provider credentials, API keys, or unredacted prompt payloads to errors, metadata, traces, or comments.
    3. Do not edit generated cache files or make unrelated refactors while touching this file.

KNOWN EDGE CASES:
    - This SDK is in alpha and several files preserve compatibility exports; check `README.md` and `vidbyte/__init__.py` before renaming public symbols.
    - Agentic headers are living documentation. Re-run a header/code cross-check after changing imports, exports, errors, or concurrency behavior.

COMMON ERRORS RAISED BY THIS FILE:
    - None observed in this file; preserve this when adding new failure paths.

RELATED DOCS:
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/system_prompt.md: source prompt for the agentic-engineering principles applied to this file.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md: file-header anatomy used for this header.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/function_design.md: function design guidance for future edits.
    - docs/design/agentic-engineering-principles-agents-middleware-tools.md: design record for this documentation pass.

TESTS:
    - python -m compileall vidbyte; tests/test_custom_function_tools.py and tool-related scripts when changing tool behavior.

CONCURRENCY MODEL:
    - Review async/task state carefully; this file participates in agent, middleware, tool, or actor execution.
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
    "fields declared in the schema are accepted; any extra keys are silently dropped."
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
        # Builds a provider-native JSON Schema for the typed updateTrace argument.
        properties = {
            field_name: {"type": spec.type.value, "description": spec.description}
            for field_name, spec in self.schema.fields.items()
        }
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

    def _first_type_error(self, update: Mapping[str, Any]) -> str | None:
        # Returns the first declared-field value whose type violates its schema, or None.
        for field_name, spec in self.schema.fields.items():
            if field_name not in update or update[field_name] is None:
                continue
            if not self._value_matches_type(update[field_name], spec.type):
                return f"{field_name} expected {spec.type.value}"
        return None

    @staticmethod
    def _value_matches_type(value: Any, field_type: TraceFieldType) -> bool:
        # Checks one JSON-like value against a declared trace field type.
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
        # Merges only declared schema fields, appending arrays and deep-merging objects.
        merged = {field_name: base.get(field_name) for field_name in self.schema.fields}
        for field_name, spec in self.schema.fields.items():
            if field_name not in update:
                continue
            merged[field_name] = self._merge_field(spec, merged.get(field_name), update[field_name])
        return merged

    def _merge_field(self, spec: TraceField, previous: Any, incoming: Any) -> Any:
        # Applies the per-type merge policy for a single field value.
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
