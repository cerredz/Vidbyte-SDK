"""Context Protocol Header

Description:
    Defines the abstract base class and structural protocol for all Vidbyte SDK tools.
Purpose:
    Provides shared call validation and a small async execution contract while supporting
    both class-based and protocol-based developer tools.
Architecture:
    - BaseTool: Abstract contract requiring spec() and execute().
    - ToolLike: Structural protocol for developer-provided tools.
Relations:
    Related to vidbyte.tools.types, vidbyte.tools.registry, and built-in tool modules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

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


class ToolLike(Protocol):
    """Structural protocol for developer-provided tools."""

    def spec(self) -> ToolSpec:
        """Return model-facing tool metadata."""

    async def arun(self, **kwargs: Any) -> Any:
        """Execute the tool asynchronously."""
