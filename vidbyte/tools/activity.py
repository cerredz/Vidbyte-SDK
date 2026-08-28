"""Context Protocol Header

Description:
    Binds a declarative ToolActivity annotation to an existing tool and separates
    the model-authored annotation from the tool's business arguments.
Purpose:
    Lets an application capture one small typed explanation of the high-level
    action a tool call represents, without a second agent, a reporting tool, or
    any change to the wrapped tool's execution, permission, or billing contract.
Architecture:
    - ActivityToolFormatter: Public static surface for bind, prepare, unwrap, and
      validation helpers that separate reserved activity input from business args.
    - _ActivityBoundTool: Private delegating wrapper; never exported.
Relations:
    Declared by vidbyte.lib.dataclasses.tools; rendered by
    vidbyte.lib.tools.formatter; applied by vidbyte.tools.catalog,
    vidbyte.tools.executor, vidbyte.tools.customization, and vidbyte.agents.runtime.
    Its generic unwrap path is shared with specification customization so runtime
    pricing continues to see the original priced operation tool.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from pydantic import ValidationError

from vidbyte.lib.dataclasses.tools import ACTIVITY_ARGUMENT_KEY
from vidbyte.lib.errors import ToolRegistrationError
from vidbyte.tools.base import BaseTool, _ToolWrapper, _unwrap_tool
from vidbyte.tools.types import ToolActivity, ToolCall, ToolCallActivity, ToolResult, ToolSpec


class ActivityToolFormatter:
    """Binds activity annotations and separates them from tool business arguments."""

    _MAX_VALIDATION_DETAIL_CHARS = 500

    @staticmethod
    def bind(tool: BaseTool, activity: ToolActivity) -> BaseTool:
        """Return a tool that declares one reserved activity annotation alongside its arguments."""
        ActivityToolFormatter._reject_conflicting_declaration(tool)
        return _ActivityBoundTool(tool, activity)

    @staticmethod
    def prepare_call(tool: BaseTool, call: ToolCall) -> ToolCall:
        """Return a call whose validated activity annotation is separated from business arguments."""
        activity = ActivityToolFormatter.declared(tool)
        if activity is None or call.activity is not None:
            return call
        raw = call.arguments.get(ACTIVITY_ARGUMENT_KEY)
        if raw is None:
            return call
        captured = ActivityToolFormatter._capture(activity, raw)
        if captured is None:
            # Leave the malformed value in place so validate_call can explain it.
            return call
        return replace(
            call,
            arguments=ActivityToolFormatter._without_activity_key(call.arguments),
            activity=captured,
        )

    @staticmethod
    def unwrap(tool: BaseTool) -> BaseTool:
        """Return the original tool behind any SDK wrapper, leaving plain tools untouched."""
        return _unwrap_tool(tool)

    @staticmethod
    def declared(tool: BaseTool) -> ToolActivity | None:
        """Return the activity declaration a tool exposes through its spec, if any."""
        spec = tool.spec()
        return spec.activity if isinstance(spec, ToolSpec) else None

    @staticmethod
    def business_call(tool: BaseTool, call: ToolCall) -> ToolCall:
        """Prepare a call and always strip the reserved key so it never reaches the tool."""
        prepared = ActivityToolFormatter.prepare_call(tool, call)
        if ACTIVITY_ARGUMENT_KEY not in prepared.arguments:
            return prepared
        return replace(
            prepared,
            arguments=ActivityToolFormatter._without_activity_key(prepared.arguments),
        )

    @staticmethod
    def validation_error(activity: ToolActivity, call: ToolCall) -> str | None:
        """Return a bounded validation message when the reserved annotation is absent or invalid."""
        if call.activity is not None:
            return None
        raw = call.arguments.get(ACTIVITY_ARGUMENT_KEY)
        if raw is None:
            if activity.required:
                return f"Missing required parameters: {ACTIVITY_ARGUMENT_KEY}"
            return None
        detail = ActivityToolFormatter._validation_detail(activity, raw)
        return f"Invalid '{ACTIVITY_ARGUMENT_KEY}' annotation: {detail}"

    @staticmethod
    def _reject_conflicting_declaration(tool: BaseTool) -> None:
        # Refuses a binding that would shadow an existing activity declaration or business input.
        spec = tool.spec()
        if spec.activity is not None:
            raise ToolRegistrationError(f"Tool '{spec.name}' already declares an activity annotation")
        if any(parameter.name == ACTIVITY_ARGUMENT_KEY for parameter in spec.parameters):
            raise ToolRegistrationError(
                f"Tool '{spec.name}' already declares an '{ACTIVITY_ARGUMENT_KEY}' parameter"
            )
        properties = ActivityToolFormatter._input_schema_properties(spec)
        if ACTIVITY_ARGUMENT_KEY in properties:
            raise ToolRegistrationError(
                f"Tool '{spec.name}' already declares an '{ACTIVITY_ARGUMENT_KEY}' input property"
            )

    @staticmethod
    def _input_schema_properties(spec: ToolSpec) -> Mapping[str, Any]:
        # Reads the declared property names from a spec's explicit input schema.
        if not isinstance(spec.input_schema, Mapping):
            return {}
        properties = spec.input_schema.get("properties")
        return properties if isinstance(properties, Mapping) else {}

    @staticmethod
    def _capture(activity: ToolActivity, raw: object) -> ToolCallActivity | None:
        # Normalizes a model-authored annotation through its schema, or returns None when invalid.
        try:
            model = activity.schema.model_validate(raw)
        except ValidationError:
            return None
        return ToolCallActivity(payload=model.model_dump(mode="json"), metadata=activity.metadata)

    @staticmethod
    def _validation_detail(activity: ToolActivity, raw: object) -> str:
        # Renders a bounded, model-readable reason why an annotation failed its schema.
        try:
            activity.schema.model_validate(raw)
        except ValidationError as exc:
            return "; ".join(
                f"{'.'.join(str(part) for part in error['loc']) or ACTIVITY_ARGUMENT_KEY}: {error['msg']}"
                for error in exc.errors()
            )[: ActivityToolFormatter._MAX_VALIDATION_DETAIL_CHARS]
        return "annotation did not reach the tool"

    @staticmethod
    def _without_activity_key(arguments: Mapping[str, Any]) -> dict[str, Any]:
        # Returns a shallow copy of arguments with the reserved activity key removed.
        return {name: value for name, value in arguments.items() if name != ACTIVITY_ARGUMENT_KEY}


class _ActivityBoundTool(_ToolWrapper):
    """Delegating wrapper that adds one reserved activity annotation to a tool."""

    def __init__(self, tool: BaseTool, activity: ToolActivity) -> None:
        # Retains the wrapped tool and the declaration rendered into its provider schema.
        self._tool = tool
        self._activity = activity

    @property
    def wrapped_tool(self) -> BaseTool:
        """Return the tool this binding delegates every contract to."""
        return self._tool

    def spec(self) -> ToolSpec:
        """Return the wrapped spec with the activity declaration attached."""
        return replace(self._tool.spec(), activity=self._activity)

    def validate_call(self, call: ToolCall) -> str | None:
        """Reject a missing or malformed annotation before delegating to the wrapped tool."""
        activity_error = ActivityToolFormatter.validation_error(self._activity, call)
        if activity_error:
            return activity_error
        return self._tool.validate_call(ActivityToolFormatter.prepare_call(self, call))

    async def execute(self, call: ToolCall) -> ToolResult:
        """Run the wrapped tool against business arguments with the annotation removed."""
        return await self._tool.execute(ActivityToolFormatter.business_call(self, call))


__all__ = ["ACTIVITY_ARGUMENT_KEY", "ActivityToolFormatter"]
