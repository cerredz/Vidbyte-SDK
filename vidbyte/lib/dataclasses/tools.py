"""Context Protocol Header

Description:
    Defines typed data contracts shared by all Vidbyte SDK tools.
Purpose:
    Owns model-facing tool metadata, invocation payloads, execution status, and
    bounded result objects while avoiding any concrete tool behavior.
Architecture:
    - ToolStatus: Normalized execution status enum.
    - ToolPermission: Authorization level requested by a tool.
    - ToolParameter: Single model-facing parameter declaration.
    - ToolSpec: Tool metadata plus compact prompt rendering.
    - ToolCall: Runtime invocation payload.
    - ToolResult: Runtime response payload with success/error helpers.
Relations:
    Re-exported by vidbyte.tools.types for existing SDK imports.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolStatus(str, Enum):
    """Execution status returned by every tool."""

    SUCCESS = "success"
    ERROR = "error"


class ToolPermission(str, Enum):
    """Risk level used by permission policies before execution."""

    SAFE = "safe"
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


@dataclass(frozen=True, slots=True)
class ToolParameter:
    """Model-facing declaration for one tool argument."""

    name: str
    type: str
    description: str
    required: bool = True

    def __post_init__(self) -> None:
        """Validate parameter metadata when the dataclass is created."""
        if not self.name.strip():
            raise ValueError("ToolParameter.name cannot be empty")
        if not self.type.strip():
            raise ValueError("ToolParameter.type cannot be empty")


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Model-facing declaration for a tool."""

    name: str
    description: str
    parameters: tuple[ToolParameter, ...] = ()
    permission: ToolPermission = ToolPermission.SAFE
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate the tool name and description."""
        if not self.name.strip():
            raise ValueError("ToolSpec.name cannot be empty")
        if not self.description.strip():
            raise ValueError("ToolSpec.description cannot be empty")

    def required_parameter_names(self) -> tuple[str, ...]:
        """Return the names of parameters that must be supplied in calls."""
        return tuple(parameter.name for parameter in self.parameters if parameter.required)

    def to_prompt_str(self) -> str:
        """Render compact tool documentation inside a tool XML block."""
        lines = ["<tool>", f"Tool: {self.name}", f"Description: {self.description}"]
        if self.parameters:
            lines.append("Parameters:")
            for parameter in self.parameters:
                required = "required" if parameter.required else "optional"
                lines.append(
                    f"- {parameter.name} ({parameter.type}, {required}): {parameter.description}"
                )
        else:
            lines.append("Parameters: none")
        lines.extend((f"Permission: {self.permission.value}", "</tool>"))
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Runtime request for a named tool with JSON-like arguments."""

    tool_name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate that the call names a tool."""
        if not self.tool_name.strip():
            raise ValueError("ToolCall.tool_name cannot be empty")


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Runtime response returned by a tool or execution pipeline."""

    tool_name: str
    status: ToolStatus
    output: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def success(
        cls,
        tool_name: str,
        output: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> "ToolResult":
        """Build a successful result with optional safe metadata."""
        return cls(
            tool_name=tool_name,
            status=ToolStatus.SUCCESS,
            output=output,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def error(
        cls,
        tool_name: str,
        output: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> "ToolResult":
        """Build a failed result with optional safe metadata."""
        return cls(
            tool_name=tool_name,
            status=ToolStatus.ERROR,
            output=output,
            metadata=dict(metadata or {}),
        )
