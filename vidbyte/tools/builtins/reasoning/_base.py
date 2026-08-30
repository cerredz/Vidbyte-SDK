"""FILE: vidbyte/tools/builtins/reasoning/_base.py

PURPOSE: Owns shared definitions, typed argument normalization, execution, rendering, and context writes for all strategy-specific trace tools.
ROLE IN CODEBASE: Every reasoning trace class subclasses ReasoningTraceTool and supplies one immutable ReasoningTraceDefinition.
ARCHITECTURE NOTE: Class-bound helpers enforce one validation contract while leaf modules retain model-facing strategy schemas.
COMMON MODIFICATION PATTERNS: Add behavior here only when every reasoning trace needs it; keep strategy-specific fields in leaf modules.
KNOWN EDGE CASES: Booleans are not numbers, numeric values must be finite, confidence is bounded, and context writes may reject records.
RELATED DOCS: docs/design/reasoning-deep-observability-tools.md and field-guide/vidbyte-sdk/class-bound-helpers.md.
TESTS: scripts/check_reasoning_trace_contracts.py and the source/package stages in scripts/run_ci.py.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, cast

from vidbyte.context.primitives.base import ContextItem
from vidbyte.lib.errors import (
    ReasoningTraceArgumentError,
    ReasoningTraceDefinitionError,
)
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager
    from vidbyte.context.primitives import ReasoningTraceContextItem

NormalizedReasoningValue = str | float | int | bool | tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReasoningTraceDefinition:
    """Describe one strategy's public model-facing reasoning trace contract."""

    skill_name: str
    purpose: str
    description: str
    parameters: tuple[ToolParameter, ...]

    def __post_init__(self) -> None:
        if not self.skill_name.strip():
            raise ReasoningTraceDefinitionError("skill name cannot be blank")
        if not self.purpose.strip():
            raise ReasoningTraceDefinitionError(
                "purpose cannot be blank",
                skill_name=self.skill_name,
            )
        if not self.description.strip():
            raise ReasoningTraceDefinitionError(
                "description cannot be blank",
                skill_name=self.skill_name,
            )
        if not self.parameters:
            raise ReasoningTraceDefinitionError(
                "at least one parameter is required",
                skill_name=self.skill_name,
            )
        names = tuple(parameter.name for parameter in self.parameters)
        if len(names) != len(set(names)):
            raise ReasoningTraceDefinitionError(
                "parameter names must be unique",
                skill_name=self.skill_name,
            )


def parameter(*, name: str, type: str, description: str, required: bool = True) -> ToolParameter:
    """Build one explicit strategy-owned model parameter declaration."""
    return ToolParameter(name=name, type=type, description=description, required=required)


class ReasoningTraceTool(BaseTool):
    """Execute one strategy-specific public reasoning trace contract."""

    definition: ClassVar[ReasoningTraceDefinition]

    def __init__(self, context_manager: ContextManager) -> None:
        """Retain the caller-owned context manager and a local readable ID counter."""
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return this strategy's own description and parameter shape."""
        return ToolSpec(
            name=self.definition.skill_name,
            description=self.definition.description,
            parameters=self.definition.parameters,
            permission=ToolPermission.SAFE,
            binds_to_primitive="reasoning_trace",
            metadata={"source_skill": self.definition.skill_name},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate, record, and return one strategy-specific public checkpoint."""
        args = dict(call.arguments)
        validation_error = self._validate_arguments(args)
        if validation_error is not None:
            return ToolResult.error(call.tool_name, validation_error)
        try:
            values = self._normalize_arguments(args)
            item = self._build_item(values)
            self._manager.upsert(cast(ContextItem, item))
        except ReasoningTraceArgumentError as exc:
            return ToolResult.error(
                call.tool_name,
                exc.message,
                metadata={"error": "invalid_reasoning_trace_argument", **exc.details},
            )
        except (TypeError, ValueError):
            return ToolResult.error(
                call.tool_name,
                "The reasoning trace could not be recorded because its context values were invalid.",
                metadata={"error": "invalid_reasoning_trace_context"},
            )
        return ToolResult.success(
            call.tool_name,
            item.to_context_text(),
            metadata={
                "strategy": item.strategy_name,
                "primitive_id": item.primitive_id,
                "parameters": tuple(values),
            },
        )

    def _validate_arguments(self, args: Mapping[str, Any]) -> str | None:
        allowed = {parameter.name for parameter in self.definition.parameters}
        unknown = sorted(name for name in args if name not in allowed)
        if unknown:
            return f"Unknown argument(s): {', '.join(unknown)}. Use only: {', '.join(sorted(allowed))}."
        missing = [parameter.name for parameter in self.definition.parameters if parameter.required and (parameter.name not in args or args[parameter.name] is None)]
        if missing:
            return f"Missing required parameter(s): {', '.join(missing)}."
        return None

    def _normalize_arguments(
        self,
        args: Mapping[str, Any],
    ) -> dict[str, NormalizedReasoningValue]:
        values: dict[str, NormalizedReasoningValue] = {}
        for declaration in self.definition.parameters:
            if declaration.name not in args:
                if declaration.required:
                    raise ReasoningTraceArgumentError(
                        declaration.name,
                        "a required value",
                    )
                continue
            values[declaration.name] = self._normalize_value(
                declaration, args[declaration.name]
            )
        return values

    def _normalize_value(
        self,
        declaration: ToolParameter,
        value: Any,
    ) -> NormalizedReasoningValue:
        if declaration.type == "string":
            return self._normalize_string(declaration, value)
        if declaration.type == "number":
            return self._normalize_number(declaration, value)
        if declaration.type == "array":
            return self._normalize_array(declaration, value)
        if declaration.type == "integer":
            return self._normalize_integer(declaration, value)
        if declaration.type == "boolean":
            return self._normalize_boolean(declaration, value)
        raise ReasoningTraceArgumentError(
            declaration.name,
            f"a supported declared type, not '{declaration.type}'",
        )

    @staticmethod
    def _normalize_string(declaration: ToolParameter, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ReasoningTraceArgumentError(declaration.name, "a non-empty string")
        return value.strip()

    @staticmethod
    def _normalize_number(declaration: ToolParameter, value: Any) -> float:
        if isinstance(value, bool):
            raise ReasoningTraceArgumentError(declaration.name, "a finite number")
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ReasoningTraceArgumentError(
                declaration.name, "a finite number"
            ) from exc
        if not math.isfinite(parsed):
            raise ReasoningTraceArgumentError(declaration.name, "a finite number")
        if declaration.name == "confidence" and not 0.0 <= parsed <= 1.0:
            raise ReasoningTraceArgumentError(
                declaration.name,
                "a number between 0.0 and 1.0",
            )
        return parsed

    @staticmethod
    def _normalize_array(
        declaration: ToolParameter,
        value: Any,
    ) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)) or not value:
            raise ReasoningTraceArgumentError(declaration.name, "a non-empty array")
        normalized = tuple(str(item).strip() for item in value if str(item).strip())
        if not normalized:
            raise ReasoningTraceArgumentError(declaration.name, "a non-empty array")
        return normalized

    @staticmethod
    def _normalize_integer(declaration: ToolParameter, value: Any) -> int:
        if isinstance(value, bool):
            raise ReasoningTraceArgumentError(declaration.name, "an integer")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ReasoningTraceArgumentError(declaration.name, "an integer") from exc

    @staticmethod
    def _normalize_boolean(declaration: ToolParameter, value: Any) -> bool:
        if not isinstance(value, bool):
            raise ReasoningTraceArgumentError(declaration.name, "a boolean")
        return value

    def _build_item(
        self,
        values: Mapping[str, NormalizedReasoningValue],
    ) -> ReasoningTraceContextItem:
        from vidbyte.context.primitives import ReasoningTraceContextItem

        self._counter += 1
        primitive_id = self._next_primitive_id()
        return ReasoningTraceContextItem(
            primitive_id=primitive_id,
            strategy_name=self.definition.skill_name,
            strategy_purpose=self.definition.purpose,
            strategy_fields=MappingProxyType(dict(values)),
            question=self._canonical_text(values, "question"),
            strategy_application=self._canonical_text(values, "strategy_application"),
            evidence=self._canonical_text(values, "evidence"),
            assumptions=self._canonical_text(values, "assumptions"),
            alternatives=self._canonical_text(values, "alternatives"),
            disconfirming_signals=self._canonical_text(values, "disconfirming_signals"),
            confidence=self._canonical_confidence(values),
            next_action=self._canonical_text(values, "next_action"),
            metadata={"source_skill": self.definition.skill_name},
        )

    @staticmethod
    def _canonical_text(
        values: Mapping[str, NormalizedReasoningValue],
        name: str,
    ) -> str:
        return str(values.get(name, ""))

    @staticmethod
    def _canonical_confidence(
        values: Mapping[str, NormalizedReasoningValue],
    ) -> float | None:
        confidence = values.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            return None
        return float(confidence)

    def _next_primitive_id(self) -> str:
        while True:
            primitive_id = f"reasoning_trace:{self.definition.skill_name}:{self._counter}"
            if self._manager.get_by_id(primitive_id) is None:
                return primitive_id
            self._counter += 1


__all__ = ["ReasoningTraceDefinition", "ReasoningTraceTool", "parameter"]
