"""Context Protocol Header

Description:
    Binds a declarative ToolActivity annotation to an existing tool and separates
    the model-authored annotation from the tool's business arguments.
Purpose:
    Lets an application capture one small typed explanation of the high-level
    action a tool call represents, without a second agent, a reporting tool, or
    any change to the wrapped tool's execution, permission, or billing contract.
Architecture:
    - ACTIVITY_ARGUMENT_KEY: Reserved provider-facing input name.
    - bind_activity: Wraps a tool so its spec carries the annotation declaration.
    - prepare_tool_call: Splits a validated annotation out of call arguments.
    - unwrap_tool: Returns the original tool behind an SDK activity binding.
    - _ActivityBoundTool: Private delegating wrapper; never exported.
Relations:
    Declared by vidbyte.lib.dataclasses.tools; rendered by
    vidbyte.lib.tools.formatter; applied by vidbyte.tools.catalog,
    vidbyte.tools.executor, and vidbyte.agents.runtime.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from pydantic import ValidationError

from vidbyte.lib.dataclasses.tools import ACTIVITY_ARGUMENT_KEY
from vidbyte.lib.errors import ToolRegistrationError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolActivity, ToolCall, ToolCallActivity, ToolResult, ToolSpec

_MAX_VALIDATION_DETAIL_CHARS = 500


def bind_activity(tool: BaseTool, activity: ToolActivity) -> BaseTool:
    """Return a tool that declares one reserved activity annotation alongside its arguments."""
    _reject_conflicting_declaration(tool)
    return _ActivityBoundTool(tool, activity)


def prepare_tool_call(tool: BaseTool, call: ToolCall) -> ToolCall:
    """Return a call whose validated activity annotation is separated from business arguments."""
    activity = declared_activity(tool)
    if activity is None or call.activity is not None:
        return call
    raw = call.arguments.get(ACTIVITY_ARGUMENT_KEY)
    if raw is None:
        return call
    captured = _capture_activity(activity, raw)
    if captured is None:
        # Leave the malformed value in place so validate_call can explain it.
        return call
    arguments = {name: value for name, value in call.arguments.items() if name != ACTIVITY_ARGUMENT_KEY}
    return replace(call, arguments=arguments, activity=captured)


def unwrap_tool(tool: BaseTool) -> BaseTool:
    """Return the original tool behind any SDK activity binding, leaving other tools untouched."""
    unwrapped = tool
    while isinstance(unwrapped, _ActivityBoundTool):
        unwrapped = unwrapped.wrapped_tool
    return unwrapped


def declared_activity(tool: BaseTool) -> ToolActivity | None:
    """Return the activity declaration a tool exposes through its spec, if any."""
    spec = tool.spec()
    return spec.activity if isinstance(spec, ToolSpec) else None


def _reject_conflicting_declaration(tool: BaseTool) -> None:
    # Refuses a binding that would shadow an existing activity declaration or business input.
    spec = tool.spec()
    if spec.activity is not None:
        raise ToolRegistrationError(f"Tool '{spec.name}' already declares an activity annotation")
    if any(parameter.name == ACTIVITY_ARGUMENT_KEY for parameter in spec.parameters):
        raise ToolRegistrationError(f"Tool '{spec.name}' already declares an '{ACTIVITY_ARGUMENT_KEY}' parameter")
    properties = _input_schema_properties(spec)
    if ACTIVITY_ARGUMENT_KEY in properties:
        raise ToolRegistrationError(f"Tool '{spec.name}' already declares an '{ACTIVITY_ARGUMENT_KEY}' input property")


def _input_schema_properties(spec: ToolSpec) -> Mapping[str, Any]:
    # Reads the declared property names from a spec's explicit input schema.
    if not isinstance(spec.input_schema, Mapping):
        return {}
    properties = spec.input_schema.get("properties")
    return properties if isinstance(properties, Mapping) else {}


def _capture_activity(activity: ToolActivity, raw: object) -> ToolCallActivity | None:
    # Normalizes a model-authored annotation through its schema, or returns None when invalid.
    try:
        model = activity.schema.model_validate(raw)
    except ValidationError:
        return None
    return ToolCallActivity(payload=model.model_dump(mode="json"), metadata=activity.metadata)


def _validation_detail(activity: ToolActivity, raw: object) -> str:
    # Renders a bounded, model-readable reason why an annotation failed its schema.
    try:
        activity.schema.model_validate(raw)
    except ValidationError as exc:
        return "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or ACTIVITY_ARGUMENT_KEY}: {error['msg']}"
            for error in exc.errors()
        )[:_MAX_VALIDATION_DETAIL_CHARS]
    return "annotation did not reach the tool"


class _ActivityBoundTool(BaseTool):
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
        activity_error = self._activity_error(call)
        if activity_error:
            return activity_error
        return self._tool.validate_call(prepare_tool_call(self, call))

    async def execute(self, call: ToolCall) -> ToolResult:
        """Run the wrapped tool against business arguments with the annotation removed."""
        return await self._tool.execute(self._business_call(call))

    def _business_call(self, call: ToolCall) -> ToolCall:
        # Captures a valid annotation and always removes the reserved key, so a caller that
        # skipped validation cannot pass a malformed annotation through as a tool argument.
        prepared = prepare_tool_call(self, call)
        if ACTIVITY_ARGUMENT_KEY not in prepared.arguments:
            return prepared
        arguments = {name: value for name, value in prepared.arguments.items() if name != ACTIVITY_ARGUMENT_KEY}
        return replace(prepared, arguments=arguments)

    def _activity_error(self, call: ToolCall) -> str | None:
        # Returns a bounded validation message when the reserved annotation is absent or invalid.
        if call.activity is not None:
            return None
        raw = call.arguments.get(ACTIVITY_ARGUMENT_KEY)
        if raw is None:
            if self._activity.required:
                return f"Missing required parameters: {ACTIVITY_ARGUMENT_KEY}"
            return None
        return f"Invalid '{ACTIVITY_ARGUMENT_KEY}' annotation: {_validation_detail(self._activity, raw)}"


__all__ = ["ACTIVITY_ARGUMENT_KEY", "bind_activity", "declared_activity", "prepare_tool_call", "unwrap_tool"]
