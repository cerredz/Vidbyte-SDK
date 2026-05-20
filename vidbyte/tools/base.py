from __future__ import annotations

from abc import ABC, abstractmethod

from vidbyte.tools.types import ToolCall, ToolResult, ToolSpec


class BaseTool(ABC):
    """Base interface for Vidbyte SDK tools."""

    @abstractmethod
    def spec(self) -> ToolSpec:
        """Return the tool's model-facing contract."""

    @abstractmethod
    async def execute(self, call: ToolCall) -> ToolResult:
        """Execute a validated tool call."""

    @property
    def name(self) -> str:
        return self.spec().name

    def validate_call(self, call: ToolCall) -> str | None:
        required_names = {param.name for param in self.spec().parameters if param.required}
        missing = sorted(required_names.difference(call.arguments))
        if missing:
            return f"Missing required parameters: {', '.join(missing)}"
        return None

