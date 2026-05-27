"""Context Protocol Header

Description:
    Implements ContextDefineTool — an agent-facing builtin for creating
    custom-shaped context window primitives with user-defined fields and schema.
Purpose:
    Lets agents define their own structured primitives at runtime when no
    built-in type (text, task, plan, document, memory, progress) fits the
    domain. Fields and schema are supplied as JSON strings (Option A).
Architecture:
    - ContextDefineTool: BaseTool that parses, validates, and upserts a
      CustomContextItem into the live ContextManager registry.
Relations:
    Used via vidbyte.tools.builtins.context_primitives. Depends on
    vidbyte.context.manager and vidbyte.context.primitives.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager


class ContextDefineTool(BaseTool):
    """Builtin tool that creates a custom-shaped context window primitive from agent-supplied fields."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores a reference to the live manager shared with AgentRuntime.
        self._manager = context_manager

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="context_define",
            description=(
                "Create a custom-shaped context window primitive with user-defined fields. "
                "Use when no built-in type fits your structure. "
                "Pass fields as a JSON object and optionally schema to document each field. "
                "The primitive persists in your context window on every future turn."
            ),
            parameters=(
                ToolParameter(
                    name="primitive_id",
                    type="string",
                    description="Stable identifier for this primitive, e.g. 'coding_task:auth.py'.",
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="Display title shown in the context window.",
                    required=True,
                ),
                ToolParameter(
                    name="fields",
                    type="string",
                    description=(
                        'JSON object mapping field names to their current values, '
                        'e.g. \'{"objective": "fix auth", "files": ["auth.py"]}\'.'
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="schema",
                    type="string",
                    description=(
                        'Optional JSON object mapping field names to human-readable descriptions, '
                        'e.g. \'{"objective": "high-level goal", "files": "files this task touches"}\'. '
                        "Every key in schema must appear in fields."
                    ),
                    required=False,
                    default="{}",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Parse, validate, and upsert a CustomContextItem into the manager registry."""
        validation = self._parse_and_validate(dict(call.arguments))
        if isinstance(validation, ToolResult):
            return validation
        primitive_id, title, fields_dict, schema_dict = validation
        item = self._build_custom_primitive(primitive_id, title, fields_dict, schema_dict)
        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))
        return ToolResult.success(
            call.tool_name,
            f"Custom primitive '{primitive_id}' defined with {len(fields_dict)} fields.",
        )

    def _parse_and_validate(self, args: dict) -> tuple[str, str, dict, dict] | ToolResult:
        """Validate all arguments and return parsed values or a ToolResult.error on failure."""
        tool_name = "context_define"

        primitive_id = str(args.get("primitive_id", "")).strip()
        if not primitive_id:
            return ToolResult.error(tool_name, "primitive_id cannot be empty.")

        title = str(args.get("title", "")).strip()
        if not title:
            return ToolResult.error(tool_name, "title cannot be empty.")

        fields_result = self._parse_json_dict(args.get("fields", ""), "fields", tool_name)
        if isinstance(fields_result, ToolResult):
            return fields_result
        fields_dict = fields_result
        if not fields_dict:
            return ToolResult.error(tool_name, "fields cannot be empty — define at least one field.")

        schema_str = str(args.get("schema", "{}") or "{}")
        schema_result = self._parse_json_dict(schema_str, "schema", tool_name)
        if isinstance(schema_result, ToolResult):
            return schema_result
        schema_dict = schema_result

        for key in schema_dict:
            if key not in fields_dict:
                return ToolResult.error(
                    tool_name,
                    f"schema key '{key}' has no corresponding entry in fields.",
                )

        return primitive_id, title, fields_dict, schema_dict

    def _parse_json_dict(self, raw: object, param_name: str, tool_name: str) -> dict | ToolResult:
        """Parse a JSON string into a dict, returning a ToolResult.error on any failure."""
        raw_str = str(raw) if raw is not None else ""
        try:
            parsed = json.loads(raw_str)
        except (json.JSONDecodeError, ValueError):
            return ToolResult.error(tool_name, f"{param_name} must be a valid JSON object.")
        if not isinstance(parsed, dict):
            return ToolResult.error(tool_name, f"{param_name} must be a JSON object, not a list or scalar.")
        return parsed

    def _build_custom_primitive(self, primitive_id: str, title: str, fields: dict, schema: dict) -> object:
        """Construct the CustomContextItem from validated inputs."""
        from vidbyte.context.primitives import CustomContextItem
        return CustomContextItem(
            primitive_id=primitive_id,
            title=title,
            fields=fields,
            schema=schema,
        )
