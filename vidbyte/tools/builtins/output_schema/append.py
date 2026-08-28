"""Context Protocol Header

Description:
    Implements AppendOutputTool — an agent-facing builtin for appending entries
    to a previously declared runtime output schema.
Purpose:
    Lets an agent emit relevant results incrementally during a run so the harness
    keeps only the compressed structured output, not the full transcript.
Architecture:
    - AppendOutputTool: BaseTool that routes to OutputSchemaBuilder.append.
Relations:
    Pairs with DeclareOutputSchemaTool over a shared OutputSchemaBuilder instance.
"""

from __future__ import annotations

from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.output_schema.builder import OutputSchemaBuilder
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)


class AppendOutputTool(BaseTool):
    """Builtin tool that appends one entry to the agent's declared output schema."""

    def __init__(self, builder: OutputSchemaBuilder) -> None:
        # Stores the shared builder that also backs the paired declare tool.
        self._builder = builder

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="append_output",
            description=(
                "Append one entry to a declared output field. For repeated fields "
                "this adds to the list; for scalar fields this sets the value. "
                "Pass a JSON object or array as the value when the field holds "
                "structured entries."
            ),
            parameters=(
                ToolParameter(
                    name="field",
                    type="string",
                    description="Name of the declared field to append to or set.",
                    required=True,
                ),
                ToolParameter(
                    name="value",
                    type="string",
                    description="The entry to store. May be plain text or a JSON object/array.",
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Append or set the provided value on the shared builder."""
        field = str(call.arguments.get("field", "")).strip()
        if not field:
            return ToolResult.error(call.tool_name, "A non-empty 'field' is required.")
        message = self._builder.append(field, call.arguments.get("value"))
        return ToolResult.success(call.tool_name, message)


__all__ = [
    "AppendOutputTool",
]
