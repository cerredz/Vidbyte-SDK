"""Context Protocol Header

Description:
    Defines the abstract base class and structural protocol for all Vidbyte SDK tools.
Purpose:
    Provides shared call validation and a small async execution contract while supporting
    both class-based and protocol-based developer tools.
Architecture:
    - BaseTool: Abstract contract requiring spec() and execute(), plus the
      with_activity() binding used to attach a model-authored annotation.
    - ToolLike: Structural protocol for developer-provided tools.
Relations:
    Related to vidbyte.tools.types, vidbyte.tools.activity, vidbyte.tools.registry,
    and built-in tool modules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

from vidbyte.tools.types import ToolActivity, ToolCall, ToolResult, ToolSpec


class BaseTool(ABC):
    """Base class for native and bridged tools."""

    @property
    def name(self) -> str:
        """Return the stable registry name from the tool spec."""
        return self.spec().name

    def with_activity(self, activity: ToolActivity) -> "BaseTool":
        """Return this tool with one reserved activity annotation the model fills in per call."""
        from vidbyte.tools.activity import bind_activity

        return bind_activity(self, activity)

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
            return f"Missing required parameters: {', '.join(missing)}"
        return None


class ToolLike(Protocol):
    """Structural protocol for developer-provided tools."""

    def spec(self) -> ToolSpec:
        """Return model-facing tool metadata."""

    async def arun(self, **kwargs: Any) -> Any:
        """Execute the tool asynchronously."""
