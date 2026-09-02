"""Context Protocol Header

FILE: vidbyte/tools/customization.py

PURPOSE:
    Owns the pure spec transformer behind BaseTool.customize(). It creates
    immutable model-facing specs that replace a tool description or existing
    top-level parameter descriptions. Do not add behavior-changing parameters
    here; semantic extensions belong to a real tool or typed adapter contract.

ROLE IN CODEBASE:
    Called lazily by the _CustomizedTool wrapper in vidbyte.tools.base. It uses
    the validated vidbyte.lib.dataclasses.tools.ToolCustomization, ToolSpec,
    and ToolParameter contracts plus standard dataclass replacement machinery.
    Returned specs flow through the tool catalog, formatter, and providers.

ARCHITECTURE NOTE:
    This module is deliberately independent of vidbyte.tools.base so a pure
    presentation transform cannot enlarge the base/activity dependency cycle.
    Both ToolSpec.parameters and explicit input_schema properties are copied so
    prompt rendering and provider schemas cannot drift.

FUNCTION INVENTORY:
    _ToolSpecCustomizer.apply(spec, customization) -> ToolSpec
        Applies validated description replacements to both schema representations.
    _ToolSpecCustomizer._replace_parameters(parameters, descriptions) -> tuple[ToolParameter, ...]
        Replaces matching ToolParameter descriptions immutably.
    _ToolSpecCustomizer._replace_input_schema(schema, descriptions) -> Mapping[str, Any] | None
        Deep-copies and updates validated explicit input-schema property descriptions.
    No validation or execution functions live here; ToolCustomization validates
        input before the base-owned wrapper invokes this transformer.

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
    4. Do not import or unwrap BaseTool here; wrapper identity belongs to base.py.

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

TESTS:
    tests/test_tool_core.py and tests/test_provider_tool_schema_translation.py
    cover validation, delegation, prompt rendering, explicit schemas, and
    provider schema output. Coverage percentage is not tracked for this module.

CONCURRENCY MODEL:
    No shared mutable state or locks. Each call creates a fresh ToolSpec from
    immutable validated replacement data.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from typing import Any

from vidbyte.lib.dataclasses.tools import ToolCustomization
from vidbyte.tools.types import ToolParameter, ToolSpec


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
