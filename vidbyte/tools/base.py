# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the abstract BaseTool class for the Vidbyte SDK.
# Purpose: Establishes a standard contract for implementing external tools
#          and provides general argument validation.
# Architecture & Functions:
#   - BaseTool (ABC): Abstract class requiring spec() and execute() methods.
#   - BaseTool.validate_call(call): Default parameter validation logic.
#   - BaseTool.name (property): Automatically exposes the tool name.
# Codebase Relation:
#   - Forms the base interface implemented by all built-in and developer-defined tools.
# Similar Files:
#   - vidbyte/prompts/base.py (defines counterparts for the prompt subsystem)
# ==============================================================================

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from vidbyte.tools.types import ToolCall, ToolResult, ToolSpec


class BaseTool(ABC):
    """
    Abstract interface for all tools in the Vidbyte SDK.
    Developers subclass this to provide custom logic to their agents.
    """

    @abstractmethod
    def spec(self) -> ToolSpec:
        """
        Returns the readable contract for this tool.
        This is what gets injected into model prompts.
        """
        pass

    @abstractmethod
    async def execute(self, call: ToolCall) -> ToolResult:
        """
        Executes the tool logic asynchronously.
        Returns a ToolResult which can be formatted as an observation.
        """
        pass

    def validate_call(self, call: ToolCall) -> Optional[str]:
        """
        Performs pre-execution check on incoming arguments.
        Returns an error string if validation fails, or None if valid.
        """
        spec = self.spec()
        required = [p.name for p in spec.parameters if p.required]
        missing = [r for r in required if r not in call.arguments]
        if missing:
            return f"Missing required parameters: {missing}"
        return None

    @property
    def name(self) -> str:
        """Convenience property to access tool name."""
        return self.spec().name
