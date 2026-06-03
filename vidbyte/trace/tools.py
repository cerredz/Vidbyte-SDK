"""Context Protocol Header

Description:
    Defines the internal tool used by the continual trace agent.
Purpose:
    Provides one model-visible updateTrace function that validates and stores
    schema-scoped trace artifact updates.
Architecture:
    - UpdateTraceTool: Safe tool with one required trace object argument.
Relations:
    Used by vidbyte.agents.continual_trace. Depends on public tool contracts.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from vidbyte.trace.options import TraceSchema
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolResult, ToolSpec


UPDATE_TRACE_TOOL_NAME = "updateTrace"


class UpdateTraceTool(BaseTool):
    """Tool used by ContinualTraceAgent to accept trace artifact updates."""

    def __init__(self, schema: TraceSchema, initial_trace: Mapping[str, Any] | None = None) -> None:
        # Initializes the accepted trace artifact from schema fields and prior values.
        self.schema = schema
        self._trace = self._merge_known_fields(schema.initial_artifact(), initial_trace or {})
        self.last_error: str | None = None

    def spec(self) -> ToolSpec:
        # Returns the model-facing updateTrace schema and compact prompt metadata.
        return ToolSpec(
            name=UPDATE_TRACE_TOOL_NAME,
            description="Update the continual trace artifact with any new information found in the main agent context.",
            parameters=(
                ToolParameter(
                    name="trace",
                    type="object",
                    description="A partial or complete trace artifact object using only the requested schema fields.",
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
        # Validates and merges the model-provided trace object into the stored artifact.
        raw_trace = call.arguments.get("trace")
        if not isinstance(raw_trace, Mapping):
            self.last_error = "trace argument must be an object"
            return ToolResult.error(
                UPDATE_TRACE_TOOL_NAME,
                "trace argument must be an object.",
                metadata={"error": "invalid_trace_argument"},
            )
        self._trace = self._merge_known_fields(self._trace, raw_trace)
        self.last_error = None
        return ToolResult.success(
            UPDATE_TRACE_TOOL_NAME,
            json.dumps(self._trace, sort_keys=True),
            metadata={"trace": self.current_trace()},
        )

    def current_trace(self) -> dict[str, Any]:
        # Returns a serializable copy of the latest accepted trace artifact.
        return dict(self._trace)

    def _input_schema(self) -> dict[str, Any]:
        # Builds a provider-native JSON Schema for the updateTrace tool argument.
        properties = {
            field_name: {"description": description}
            for field_name, description in self.schema.fields.items()
        }
        return {
            "type": "object",
            "properties": {
                "trace": {
                    "type": "object",
                    "description": "Trace artifact update. Unknown fields are ignored by the SDK.",
                    "properties": properties,
                    "additionalProperties": True,
                }
            },
            "required": ["trace"],
            "additionalProperties": False,
        }

    def _merge_known_fields(self, base: Mapping[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
        # Merges only declared schema fields, preserving omitted previous values.
        merged = {field_name: base.get(field_name) for field_name in self.schema.fields}
        for field_name in self.schema.fields:
            if field_name in update:
                merged[field_name] = update[field_name]
        return merged


__all__ = [
    "UPDATE_TRACE_TOOL_NAME",
    "UpdateTraceTool",
]
