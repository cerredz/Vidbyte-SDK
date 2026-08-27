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
    vidbyte.tools.base._ToolWrapper and the validated
    vidbyte.lib.dataclasses.tools.ToolCustomization, ToolSpec, and ToolParameter
    contracts plus the standard dataclass replacement machinery. Its
    returned spec flows through vidbyte.tools.catalog.Tools, vidbyte.lib.tools
    formatter.ToolsFormatter, and provider clients. Its execution delegation
    flows through vidbyte.tools.executor.ToolExecutor and vidbyte.agents.runtime.

ARCHITECTURE NOTE:
    This is a presentation-only decorator. The wrapped BaseTool remains the
    source of truth for call validation, execution, permissions, billing, and
    output behavior. Both ToolSpec.parameters and explicit input_schema
    properties are copied so prompt rendering and provider schemas cannot drift.

FUNCTION INVENTORY:
    _CustomizedTool.__init__(tool, customization) -> None
        Stores the already-validated description replacements.
    _CustomizedTool.spec() -> ToolSpec
        Returns a copied model-facing spec with replacements applied.
    _CustomizedTool.validate_call(call) -> str | None
        Delegates call validation to the original tool.
    _CustomizedTool.execute(call) -> ToolResult
        Delegates execution to the original tool without changing arguments.
    _ToolSpecCustomizer.apply(spec, customization) -> ToolSpec
        Applies validated description replacements to both schema representations.
    _ToolSpecCustomizer._replace_parameters(parameters, descriptions) -> tuple[ToolParameter, ...]
        Replaces matching ToolParameter descriptions immutably.
    _ToolSpecCustomizer._replace_input_schema(schema, descriptions) -> Mapping[str, Any] | None
        Deep-copies and updates validated explicit input-schema property descriptions.
    No validation functions live here; ToolCustomization owns all input and
        source-schema validation before this module is constructed.

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
from typing import Any

from vidbyte.lib.dataclasses.tools import ToolCustomization
from vidbyte.tools.base import BaseTool, _ToolWrapper
from vidbyte.tools.types import ToolCall, ToolParameter, ToolResult, ToolSpec


class _CustomizedTool(_ToolWrapper):
    """Private wrapper that changes model-facing descriptions only."""

    def __init__(self, tool: BaseTool, customization: ToolCustomization) -> None:
        # The dataclass owns validation; this wrapper only preserves the tool boundary.
        self._tool = tool
        self._customization = customization

    @property
    def wrapped_tool(self) -> BaseTool:
        # Return the original tool for shared runtime identity handling.
        return self._tool

    def spec(self) -> ToolSpec:
        # Return a fresh customized spec while preserving the wrapped contract.
        return _ToolSpecCustomizer.apply(self._tool.spec(), self._customization)

    def validate_call(self, call: ToolCall) -> str | None:
        # Preserve the original validation contract and error wording.
        return self._tool.validate_call(call)

    async def execute(self, call: ToolCall) -> ToolResult:
        # Execute the original tool with the original business arguments.
        return await self._tool.execute(call)


class _ToolSpecCustomizer:
    """Pure helpers for applying description replacements to a ToolSpec."""

    @staticmethod
    def apply(spec: ToolSpec, customization: ToolCustomization) -> ToolSpec:
        # Replace every model-facing description representation from validated input.
        parameter_descriptions = customization.parameter_descriptions
        input_schema = _ToolSpecCustomizer._replace_input_schema(
            spec.input_schema,
            parameter_descriptions,
        )
        return replace(
            spec,
            description=customization.description,
            parameters=_ToolSpecCustomizer._replace_parameters(spec.parameters, parameter_descriptions),
            input_schema=input_schema,
        )

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
    def _replace_input_schema(schema: Mapping[str, Any] | None, descriptions: Mapping[str, str]) -> Mapping[str, Any] | None:
        # Deep-copy validated explicit JSON Schema properties before applying descriptions.
        if schema is None or not descriptions:
            return schema
        copied = deepcopy(dict(schema))
        copied_properties = dict(copied["properties"])
        for name, description in descriptions.items():
            copied_properties[name] = {**copied_properties[name], "description": description}
        copied["properties"] = copied_properties
        return copied


__all__: list[str] = []
