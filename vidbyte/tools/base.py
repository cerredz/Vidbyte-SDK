"""Context Protocol Header

Description:
    Defines the abstract base class for all Vidbyte SDK tools.
Purpose:
    Provides shared call validation and a small async execution contract without
    owning registry, permission, or concrete tool behavior.
Architecture:
    - BaseTool: Abstract contract requiring spec() and execute().
Relations:
    Related to vidbyte.tools.types, vidbyte.tools.registry, and built-in tool modules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from vidbyte.tools.types import ToolCall, ToolResult, ToolSpec


class BaseTool(ABC):
    """Base class for native and bridged tools."""

    @property
    def name(self) -> str:
        """Return the stable registry name from the tool spec."""
        return self.spec().name

    @abstractmethod
    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""

    @abstractmethod
    async def execute(self, call: ToolCall) -> ToolResult:
        """Run the tool for an already validated call."""

    def validate_call(self, call: ToolCall) -> str | None:
        """Return a validation error string, or None when arguments are valid."""
        spec = self.spec()
        missing = [
            name
            for name in spec.required_parameter_names()
            if name not in call.arguments or call.arguments[name] is None
        ]
        if missing:
            return f"Missing required parameter(s): {', '.join(missing)}"
        return None
