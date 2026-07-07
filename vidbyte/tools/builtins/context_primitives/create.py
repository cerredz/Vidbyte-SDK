"""Context Protocol Header

Description:
    Implements CreateContextPrimitiveTool for registry-generated context creation.
Purpose:
    Lets agents create typed context-window primitives through one tool instance
    per primitive key while sharing validation and manager mutation logic.
Architecture:
    - CreateContextPrimitiveTool: BaseTool backed by a PrimitiveToolDefinition.
Relations:
    Used via context_window_tools and vidbyte.tools.builtins.context_primitives.
    Depends on ContextManager, ContextWindowPlacement, and the create registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.context_primitives.registry import PrimitiveToolDefinition
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager


class CreateContextPrimitiveTool(BaseTool):
    """Generic create tool instantiated once per context primitive registry row."""

    def __init__(self, definition: PrimitiveToolDefinition, context_manager: ContextManager) -> None:
        """Store the primitive definition and live manager shared with the runtime."""
        self._definition = definition
        self._manager = context_manager

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration supplied by the registry row."""
        return ToolSpec(
            name=self._definition.tool_name,
            description=self._definition.description,
            parameters=self._definition.parameters,
            input_schema=dict(self._definition.input_schema),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Build the requested primitive and upsert it into the shared manager."""
        args = dict(call.arguments)
        validation_error = self._validate_arguments(args)
        if validation_error is not None:
            return ToolResult.error(call.tool_name, validation_error)
        placement_result = self._parse_placement(args)
        if not isinstance(placement_result, ContextWindowPlacement):
            return ToolResult.error(call.tool_name, placement_result)
        args.pop("placement", None)
        try:
            item = self._definition.builder(args)
            self._manager.upsert(item, placement=placement_result)
        except (TypeError, ValueError) as exc:
            return ToolResult.error(call.tool_name, self._format_builder_error(exc))
        return ToolResult.success(
            call.tool_name,
            f"Created primitive '{item.primitive_id}' ({item.kind}) at placement '{placement_result.value}'.",
            metadata={"primitive_id": item.primitive_id, "kind": item.kind, "placement": placement_result.value},
        )

    def _validate_arguments(self, args: dict[str, Any]) -> str | None:
        """Return an actionable validation error, or None when arguments are accepted."""
        schema = self._definition.input_schema
        properties = set(schema.get("properties", {}).keys())
        unknown = sorted(name for name in args if name not in properties)
        if unknown:
            return f"Unknown argument(s): {', '.join(unknown)}. Use only: {', '.join(sorted(properties))}."
        missing = [name for name in schema.get("required", ()) if name not in args or args[name] is None]
        if missing:
            return f"Missing required argument(s): {', '.join(missing)}."
        return None

    def _parse_placement(self, args: dict[str, Any]) -> ContextWindowPlacement | str:
        """Return a normalized placement enum or an error message string."""
        placement_raw = str(args.get("placement", ContextWindowPlacement.END_OF_CONTEXT.value)).strip()
        try:
            return ContextWindowPlacement(placement_raw)
        except ValueError:
            allowed = ", ".join(placement.value for placement in ContextWindowPlacement)
            return f"Invalid placement '{placement_raw}'. Use one of: {allowed}."

    def _format_builder_error(self, exc: Exception) -> str:
        """Return a model-steering error message for primitive construction failures."""
        return f"Could not create {self._definition.key} primitive: {exc}"


__all__ = ["CreateContextPrimitiveTool"]
