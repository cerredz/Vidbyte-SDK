"""Context Protocol Header

Description:
    Implements DeclareOutputSchemaTool — an agent-facing builtin for declaring a
    structured output shape at runtime.
Purpose:
    Lets an agent announce the fields it will emit before appending values, so a
    harness can read a predictable structured snapshot after the run.
Architecture:
    - DeclareOutputSchemaTool: BaseTool that routes to OutputSchemaBuilder.declare.
Relations:
    Pairs with AppendOutputTool over a shared OutputSchemaBuilder instance.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.output_schema.builder import OutputSchemaBuilder
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)


class DeclareOutputSchemaTool(BaseTool):
    """Builtin tool that declares the fields an agent will emit as structured output."""

    def __init__(self, builder: OutputSchemaBuilder) -> None:
        # Stores the shared builder that also backs the paired append tool.
        self._builder = builder

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="declare_output_schema",
            description=(
                "Declare the structured output you will build during this run. "
                "Provide a list of fields; set repeated=true for fields you will "
                "append multiple entries to (e.g. files, prompts, notes). Call "
                "this once before append_output."
            ),
            parameters=(
                ToolParameter(
                    name="fields",
                    type="array",
                    description=(
                        "List of field objects, each: {name, description, repeated}. "
                        "May be passed as a JSON array or a JSON string."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Register the declared fields on the shared builder."""
        fields = self._normalize_fields(call.arguments.get("fields"))
        if not fields:
            return ToolResult.error(call.tool_name, "No valid fields were provided to declare.")
        declared = self._builder.declare(fields)
        return ToolResult.success(call.tool_name, f"Declared output fields: {', '.join(declared)}.")

    @staticmethod
    def _normalize_fields(raw: Any) -> Sequence[Mapping[str, Any] | str]:
        # Accepts a JSON string, a single field, or a list of field declarations.
        if raw is None:
            return ()
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return ({"name": raw},)
            raw = parsed
        if isinstance(raw, Mapping):
            return (raw,)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            return tuple(raw)
        return ()


__all__ = [
    "DeclareOutputSchemaTool",
]
