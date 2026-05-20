# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the core dataclasses and enums for the Vidbyte SDK Tools Abstraction.
# Purpose: Establishes a standard contract for exchanging tool parameters, specs,
#          model calls, and execution results across agent strategies.
# Architecture & Functions:
#   - ToolStatus (Enum): Standardized execution statuses (SUCCESS, ERROR, TIMEOUT).
#   - ToolParameter (dataclass): Describes type, description, and requirement of parameters.
#   - ToolSpec (dataclass): Exposes name, description, and parameters to model prompts.
#   - ToolCall (dataclass): Represents a parsed tool invocation request.
#   - ToolResult (dataclass): Wraps outputs, metadata, errors, and observation strings.
# Codebase Relation:
#   - Forms the data-representation backbone of the `vidbyte.tools` namespace.
#   - Utilized by ToolRegistry, ToolExecutor, and all strategies (e.g. ReActStrategy).
# Similar Files:
#   - vidbyte/prompts/types.py (defines counterparts for the prompt subsystem)
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ToolStatus(str, Enum):
    """Execution outcome status of a tool run."""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class ToolParameter:
    """Defines a single parameter schema for a tool."""
    name: str
    type: str  # "string", "int", "bool", "float", etc.
    description: str
    required: bool = True
    default: Optional[Any] = None


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """
    Model-visible contract of a tool.
    Injected into prompts so models understand tool capabilities and usage.
    """
    name: str
    description: str
    parameters: List[ToolParameter] = field(default_factory=list)

    def to_prompt_str(self) -> str:
        """Renders the spec as a readable string for prompt injection."""
        params = "\n".join([
            f"  - {p.name} ({p.type}, "
            f"{'required' if p.required else 'optional'}): "
            f"{p.description}"
            for p in self.parameters
        ])
        return f"Tool: {self.name}\n{self.description}\nParameters:\n{params}"


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Represents a parsed tool invocation request from the model's response."""
    tool_name: str
    arguments: Dict[str, Any]
    raw: str  # The raw string matching from model generation


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Outcome of executing a tool, ready to be sent back into the agent loop."""
    tool_name: str
    status: ToolStatus
    output: Any
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_observation_str(self) -> str:
        """Renders as an Observation string for injection back into agent loop."""
        if self.status == ToolStatus.ERROR:
            return f"Observation: Tool {self.tool_name} failed - {self.error}"
        return f"Observation: {self.output}"
