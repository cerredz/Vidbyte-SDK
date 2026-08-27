"""Shared execution contracts for strategy-specific reasoning trace tools."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar

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


@dataclass(frozen=True, slots=True)
class ReasoningTraceDefinition:
    """Describe one strategy's public model-facing reasoning trace contract."""

    skill_name: str
    purpose: str
    description: str
    parameters: tuple[ToolParameter, ...]

    def __post_init__(self) -> None:
        if not self.skill_name.strip():
            raise ValueError("Reasoning trace skill names cannot be blank")
        if not self.purpose.strip():
            raise ValueError(f"Reasoning trace purpose is blank: {self.skill_name}")
        if not self.description.strip():
            raise ValueError(f"Reasoning trace description is blank: {self.skill_name}")
        if not self.parameters:
            raise ValueError(f"Reasoning trace parameters are empty: {self.skill_name}")
        names = tuple(parameter.name for parameter in self.parameters)
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate reasoning trace parameter: {self.skill_name}")


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
            self._manager.upsert(item)
        except (TypeError, ValueError) as exc:
            return ToolResult.error(call.tool_name, str(exc))
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

    def _normalize_arguments(self, args: Mapping[str, Any]) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for declaration in self.definition.parameters:
            if declaration.name not in args:
                if declaration.required:
                    raise ValueError(f"Missing required parameter: {declaration.name}")
                continue
            values[declaration.name] = self._normalize_value(declaration, args[declaration.name])
        return values

    def _normalize_value(self, declaration: ToolParameter, value: Any) -> Any:
        if declaration.type == "string":
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Parameter '{declaration.name}' must be a non-empty string.")
            return value.strip()
        if declaration.type == "number":
            if isinstance(value, bool):
                raise ValueError(f"Parameter '{declaration.name}' must be a finite number.")
            try:
                parsed = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Parameter '{declaration.name}' must be a finite number.") from exc
            if not math.isfinite(parsed):
                raise ValueError(f"Parameter '{declaration.name}' must be a finite number.")
            if declaration.name == "confidence" and not 0.0 <= parsed <= 1.0:
                raise ValueError("Parameter 'confidence' must be between 0.0 and 1.0.")
            return parsed
        if declaration.type == "array":
            if not isinstance(value, (list, tuple)) or not value:
                raise ValueError(f"Parameter '{declaration.name}' must be a non-empty array.")
            normalized = tuple(str(item).strip() for item in value if str(item).strip())
            if not normalized:
                raise ValueError(f"Parameter '{declaration.name}' must be a non-empty array.")
            return normalized
        if declaration.type == "integer":
            if isinstance(value, bool):
                raise ValueError(f"Parameter '{declaration.name}' must be an integer.")
            try:
                return int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Parameter '{declaration.name}' must be an integer.") from exc
        if declaration.type == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"Parameter '{declaration.name}' must be a boolean.")
            return value
        raise ValueError(f"Parameter '{declaration.name}' uses unsupported type '{declaration.type}'.")

    def _build_item(self, values: Mapping[str, Any]) -> Any:
        from vidbyte.context.primitives import ReasoningTraceContextItem

        self._counter += 1
        primitive_id = self._next_primitive_id()
        confidence = values.get("confidence")
        canonical = {
            "question": str(values.get("question", "")),
            "strategy_application": str(values.get("strategy_application", "")),
            "evidence": str(values.get("evidence", "")),
            "assumptions": str(values.get("assumptions", "")),
            "alternatives": str(values.get("alternatives", "")),
            "disconfirming_signals": str(values.get("disconfirming_signals", "")),
            "confidence": confidence if isinstance(confidence, (int, float)) else None,
            "next_action": str(values.get("next_action", "")),
        }
        return ReasoningTraceContextItem(
            primitive_id=primitive_id,
            strategy_name=self.definition.skill_name,
            strategy_purpose=self.definition.purpose,
            strategy_fields=MappingProxyType(dict(values)),
            question=canonical["question"],
            strategy_application=canonical["strategy_application"],
            evidence=canonical["evidence"],
            assumptions=canonical["assumptions"],
            alternatives=canonical["alternatives"],
            disconfirming_signals=canonical["disconfirming_signals"],
            confidence=canonical["confidence"],
            next_action=canonical["next_action"],
            metadata={"source_skill": self.definition.skill_name},
        )

    def _next_primitive_id(self) -> str:
        while True:
            primitive_id = f"reasoning_trace:{self.definition.skill_name}:{self._counter}"
            if self._manager.get_by_id(primitive_id) is None:
                return primitive_id
            self._counter += 1


__all__ = ["ReasoningTraceDefinition", "ReasoningTraceTool", "parameter"]
