from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ToolStatus(str, Enum):
    """Normalized tool execution status."""

    SUCCESS = "success"
    ERROR = "error"


class ToolPermission(str, Enum):
    """Permission tier declared by a tool."""

    SAFE = "safe"
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


@dataclass(frozen=True, slots=True)
class ToolParameter:
    """Model-facing description of one tool argument."""

    name: str
    type: str
    description: str = ""
    required: bool = True
    default: Any = None


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Model and provider-facing tool specification."""

    name: str
    description: str
    parameters: tuple[ToolParameter, ...] = ()
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    permission: ToolPermission = ToolPermission.SAFE
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_prompt_str(self) -> str:
        """Render a compact tool description for prompt insertion."""
        if not self.parameters:
            return f"Tool: {self.name}\n{self.description}\nParameters: none"
        rendered = "\n".join(
            f"  - {param.name} ({param.type}, {'required' if param.required else 'optional'}): {param.description}".rstrip()
            for param in self.parameters
        )
        return f"Tool: {self.name}\n{self.description}\nParameters:\n{rendered}"


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Structured request to execute a tool."""

    tool_name: str
    arguments: Mapping[str, Any]
    raw: str = ""


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Normalized tool execution result."""

    tool_name: str
    status: ToolStatus
    output: str
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, tool_name: str, output: object, *, metadata: Mapping[str, Any] | None = None) -> "ToolResult":
        return cls(tool_name=tool_name, status=ToolStatus.SUCCESS, output=str(output), metadata=dict(metadata or {}))

    @classmethod
    def failure(cls, tool_name: str, error: str, *, metadata: Mapping[str, Any] | None = None) -> "ToolResult":
        return cls(tool_name=tool_name, status=ToolStatus.ERROR, output="", error=error, metadata=dict(metadata or {}))

    def to_observation_str(self) -> str:
        if self.status is ToolStatus.ERROR:
            return f"Observation: Tool {self.tool_name} failed - {self.error}"
        return f"Observation: {self.output}"

