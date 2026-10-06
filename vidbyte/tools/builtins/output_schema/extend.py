"""Context Protocol Header

Description:
    Implements ExtendOutputSchemaTool — an agent-facing builtin for adding fields
    to the output schema after the initial declaration.
Purpose:
    Lets an agent extend its declared output shape mid-run when it discovers the
    request warrants fields it did not declare upfront, so dynamic prompt-shaped
    output (hypotheses, migration_steps, reproduction_steps, etc.) stays first-class.
Architecture:
    - ExtendOutputSchemaTool: BaseTool that routes additively to OutputSchemaBuilder.declare.
Relations:
    Pairs with DeclareOutputSchemaTool and AppendOutputTool over a shared
    OutputSchemaBuilder instance.
"""

from __future__ import annotations

from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.output_schema.builder import OutputSchemaBuilder
from vidbyte.tools.builtins.output_schema.declare import DeclareOutputSchemaTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class ExtendOutputSchemaTool(BaseTool):
    """Builtin tool that adds fields to the output schema after the initial declaration."""

    def __init__(self, builder: OutputSchemaBuilder) -> None:
        # Stores the shared builder that also backs the paired declare/append tools.
        self._builder = builder

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="extend_output_schema",
            description=(
                "Add additional output fields to the schema after the initial "
                "declare_output_schema call. Use when you discover mid-run that "
                "the request warrants fields you did not declare upfront (e.g. "
                "hypotheses for a research question, migration_steps for a "
                "refactor, reproduction_steps for a bug). Fields are added "
                "additively; existing fields are not affected. Can be called "
                "multiple times."
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
        """Register the additional fields on the shared builder."""
        fields = DeclareOutputSchemaTool._normalize_fields(call.arguments.get("fields"))
        if not fields:
            return ToolResult.error(call.tool_name, "No valid fields were provided to extend.")
        declared = self._builder.declare(fields)
        return ToolResult.success(call.tool_name, f"Extended output schema with fields: {', '.join(declared)}.")


__all__ = [
    "ExtendOutputSchemaTool",
]
