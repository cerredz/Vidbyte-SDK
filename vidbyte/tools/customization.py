"""Context Protocol Header

FILE: vidbyte/tools/customization.py

PURPOSE:
    Owns the private delegating wrapper behind BaseTool.customize(). It creates
    immutable model-facing views that replace a tool description or existing
    top-level parameter descriptions while leaving validation and execution on
    the original tool. Do not add behavior-changing parameters here; semantic
    extensions belong to a real tool or a future typed adapter contract.

ROLE IN CODEBASE:
    Called lazily by vidbyte.tools.base.BaseTool.customize(). It calls
    vidbyte.tools.base._ToolWrapper and vidbyte.lib.dataclasses.tools.ToolSpec,
    ToolParameter, and the standard dataclass replacement machinery. Its
    returned spec flows through vidbyte.tools.catalog.Tools, vidbyte.lib.tools
    formatter.ToolsFormatter, and provider clients. Its execution delegation
    flows through vidbyte.tools.executor.ToolExecutor and vidbyte.agents.runtime.

ARCHITECTURE NOTE:
    This is a presentation-only decorator. The wrapped BaseTool remains the
    source of truth for call validation, execution, permissions, billing, and
    output behavior. Both ToolSpec.parameters and explicit input_schema
    properties are copied so prompt rendering and provider schemas cannot drift.

FUNCTION INVENTORY:
    _CustomizedTool.__init__(tool, description, parameter_descriptions) -> None
        Validates and freezes the requested description replacements.
    _CustomizedTool.spec() -> ToolSpec
        Returns a copied model-facing spec with replacements applied.
    _CustomizedTool.validate_call(call) -> str | None
        Delegates call validation to the original tool.
    _CustomizedTool.execute(call) -> ToolResult
        Delegates execution to the original tool without changing arguments.
    _ToolSpecCustomizer.apply(spec, description, parameter_descriptions) -> ToolSpec
        Applies validated description replacements to both schema representations.
    _ToolSpecCustomizer._declared_parameter_names(spec) -> frozenset[str]
        Returns effective top-level parameter names and validates explicit schemas.
    _ToolSpecCustomizer._replace_parameters(parameters, descriptions) -> tuple[ToolParameter, ...]
        Replaces matching ToolParameter descriptions immutably.
    _ToolSpecCustomizer._replace_input_schema(schema, descriptions, tool_name) -> Mapping[str, Any] | None
        Deep-copies and updates explicit input-schema property descriptions.
    _validate_description_values(tool_name, description, parameter_descriptions) -> dict[str, str]
        Rejects blank or incorrectly typed replacement values before schema use.

COMMON MODIFICATION PATTERNS:
    Add only model-facing presentation fields here. If a change needs a new
    argument, validation rule, side effect, permission, or output contract,
    implement a concrete BaseTool or typed adapter instead. If ToolSpec gains
    another provider-facing representation, update apply() so all descriptions
    remain synchronized and extend tests/test_provider_tool_schema_translation.py.

WHAT NOT TO DO IN THIS FILE:
    1. Do not add arbitrary parameters; execution ownership belongs to the
       concrete tool under vidbyte/tools/builtins/ or a future adapter module.
    2. Do not mutate a wrapped ToolSpec or caller-owned input_schema mapping.
    3. Do not perform provider-specific formatting; that belongs to
       vidbyte/lib/tools/formatter.py.
    4. Do not unwrap tools here; wrapper identity belongs to vidbyte/tools/base.py.

KNOWN EDGE CASES:
    - Tools may represent inputs through parameters, explicit input_schema, or
      both; an override must address every effective top-level name.
    - A malformed explicit schema is rejected when a parameter description
      needs to be applied rather than being silently partially modified.
    - Nested properties are not independently addressable; customization is
      intentionally limited to top-level tool parameters.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/tool-spec-customization.md
        Design source of truth for this wrapper and its intentional boundaries.
    https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/tools/README.md
        Public tool usage and customization guidance.

AUTO-GENERATED FLAG: No. This file is maintained by hand.

TEST FILES:
    tests/test_tool_core.py and tests/test_provider_tool_schema_translation.py
    cover validation, delegation, prompt rendering, explicit schemas, and
    provider schema output. Coverage percentage is not tracked for this module.

CONCURRENCY MODEL:
    No shared mutable state or locks. Each wrapper freezes its own replacement
    mapping and creates a fresh ToolSpec on every spec() call.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType
from typing import Any

from vidbyte.tools.base import BaseTool, _ToolWrapper
from vidbyte.tools.types import ToolCall, ToolParameter, ToolResult, ToolSpec


class _CustomizedTool(_ToolWrapper):
    """Private wrapper that changes model-facing descriptions only."""

    def __init__(self, tool: BaseTool, *, description: str | None = None, parameter_descriptions: Mapping[str, str] | None = None) -> None:
        # Validate replacement values before the wrapper can enter a catalog.
        descriptions = _validate_description_values(tool.name, description, parameter_descriptions)
        _ToolSpecCustomizer.apply(tool.spec(), description, descriptions)
        self._tool = tool
        self._description = description
        self._parameter_descriptions = MappingProxyType(descriptions)

    @property
    def wrapped_tool(self) -> BaseTool:
        # Return the original tool for shared runtime identity handling.
        return self._tool

    def spec(self) -> ToolSpec:
        # Return a fresh customized spec while preserving the wrapped contract.
        return _ToolSpecCustomizer.apply(self._tool.spec(), self._description, self._parameter_descriptions)

    def validate_call(self, call: ToolCall) -> str | None:
        # Preserve the original validation contract and error wording.
        return self._tool.validate_call(call)

    async def execute(self, call: ToolCall) -> ToolResult:
        # Execute the original tool with the original business arguments.
        return await self._tool.execute(call)


class _ToolSpecCustomizer:
    """Pure helpers for applying description replacements to a ToolSpec."""

    @staticmethod
    def apply(spec: ToolSpec, description: str | None, parameter_descriptions: Mapping[str, str]) -> ToolSpec:
        # Validate names and replace every model-facing description representation.
        if parameter_descriptions:
            declared = _ToolSpecCustomizer._declared_parameter_names(spec)
            unknown = sorted(set(parameter_descriptions) - declared)
            if unknown:
                names = ", ".join(repr(name) for name in unknown)
                raise ValueError(f"Tool '{spec.name}' has no top-level parameter(s): {names}")
        input_schema = _ToolSpecCustomizer._replace_input_schema(
            spec.input_schema,
            parameter_descriptions,
            spec.name,
        )
        return replace(
            spec,
            description=description if description is not None else spec.description,
            parameters=_ToolSpecCustomizer._replace_parameters(spec.parameters, parameter_descriptions),
            input_schema=input_schema,
        )

    @staticmethod
    def _declared_parameter_names(spec: ToolSpec) -> frozenset[str]:
        # Return the provider-facing top-level names from the active schema representation.
        if spec.input_schema is None:
            return frozenset(parameter.name for parameter in spec.parameters)
        properties = spec.input_schema.get("properties") if isinstance(spec.input_schema, Mapping) else None
        if not isinstance(properties, Mapping):
            raise ValueError(f"Tool '{spec.name}' input_schema must expose top-level properties")
        if not all(isinstance(name, str) for name in properties):
            raise ValueError(f"Tool '{spec.name}' input_schema property names must be strings")
        return frozenset(properties)

    @staticmethod
    def _replace_parameters(parameters: tuple[ToolParameter, ...], descriptions: Mapping[str, str]) -> tuple[ToolParameter, ...]:
        # Return copied ToolParameter values with only selected descriptions changed.
        return tuple(
            replace(parameter, description=descriptions[parameter.name])
            if parameter.name in descriptions
            else parameter
            for parameter in parameters
        )

    @staticmethod
    def _replace_input_schema(schema: Mapping[str, Any] | None, descriptions: Mapping[str, str], tool_name: str) -> Mapping[str, Any] | None:
        # Deep-copy explicit JSON Schema properties before applying descriptions.
        if schema is None or not descriptions:
            return schema
        properties = schema.get("properties") if isinstance(schema, Mapping) else None
        if not isinstance(properties, Mapping):
            raise ValueError(f"Tool '{tool_name}' input_schema must expose top-level properties")
        try:
            copied = deepcopy(dict(schema))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Tool '{tool_name}' input_schema could not be copied") from exc
        copied_source = copied["properties"]
        if not isinstance(copied_source, Mapping):
            raise ValueError(f"Tool '{tool_name}' input_schema must expose top-level properties")
        copied_properties: dict[str, Any] = {}
        for name, property_schema in copied_source.items():
            if name not in descriptions:
                copied_properties[name] = property_schema
                continue
            if not isinstance(property_schema, Mapping):
                raise ValueError(f"Tool '{tool_name}' input_schema property '{name}' must be an object")
            copied_properties[name] = {**dict(property_schema), "description": descriptions[name]}
        copied["properties"] = copied_properties
        return copied


def _validate_description_values(tool_name: str, description: str | None, parameter_descriptions: Mapping[str, str] | None) -> dict[str, str]:
    # Reject blank or incorrectly typed descriptions before constructing the wrapper.
    if description is not None and (not isinstance(description, str) or not description.strip()):
        raise ValueError(f"Tool '{tool_name}' description customization cannot be blank")
    if parameter_descriptions is None:
        return {}
    if not isinstance(parameter_descriptions, Mapping):
        raise ValueError(f"Tool '{tool_name}' parameter_descriptions must be a mapping")
    copied = dict(parameter_descriptions)
    for name, value in copied.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Tool '{tool_name}' parameter description name cannot be blank")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Tool '{tool_name}' parameter '{name}' description cannot be blank")
    return copied


__all__: list[str] = []
