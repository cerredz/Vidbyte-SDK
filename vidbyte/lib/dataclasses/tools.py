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
    - ToolActivity: Declarative annotation schema bound to an existing tool.
    - ToolCallActivity: Normalized per-call annotation captured before execution.
    - ToolSpec: Tool metadata plus compact prompt rendering.
    - ToolCustomization: Validated description replacements bound to one ToolSpec.
    - ToolCall: Runtime invocation payload.
    - ToolResult: Runtime response payload with success/error helpers.
    - ToolCallContext: Agent-local lifecycle context for tool calls.
Relations:
    Re-exported by vidbyte.tools.types for existing SDK imports; bound to tools
    by vidbyte.tools.activity.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel

# Reserved provider-facing input name carrying a tool's activity annotation. Fixed so
# prompts, provider schemas, and middleware stay uniform across every consumer.
ACTIVITY_ARGUMENT_KEY = "activity"


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


class ToolCallState(str, Enum):
    """Lifecycle state for an agent-managed tool call."""

    REQUESTED = "requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"


@dataclass(frozen=True, slots=True)
class ToolParameter:
    """Model-facing declaration for one tool argument."""

    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None

    def __post_init__(self) -> None:
        """Validate parameter metadata when the dataclass is created."""
        if not self.name.strip():
            raise ValueError("ToolParameter.name cannot be empty")
        if not self.type.strip():
            raise ValueError("ToolParameter.type cannot be empty")


@dataclass(frozen=True, slots=True)
class ToolActivity:
    """Declares one typed annotation the model fills in alongside a tool's arguments."""

    schema: type[BaseModel]
    description: str
    required: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate the annotation schema and freeze its static consumer metadata."""
        if not isinstance(self.schema, type) or not issubclass(self.schema, BaseModel):
            raise ValueError("ToolActivity.schema must be a pydantic BaseModel subclass")
        if not self.description.strip():
            raise ValueError("ToolActivity.description cannot be empty")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class ToolCallActivity:
    """Normalized annotation captured from one model-issued tool call."""

    payload: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze both mappings so a captured annotation cannot be mutated by a consumer."""
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Model-facing declaration for a tool."""

    name: str
    description: str
    parameters: tuple[ToolParameter, ...] = ()
    permission: ToolPermission = ToolPermission.SAFE
    metadata: Mapping[str, Any] = field(default_factory=dict)
    input_schema: Mapping[str, Any] | None = None
    binds_to_primitive: str | None = None
    output_schema: type | Mapping[str, Any] | None = None
    activity: ToolActivity | None = None

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
class ToolCustomization:
    """Validated model-facing description replacements for one tool spec."""

    tool_spec: ToolSpec
    description: str
    parameter_descriptions: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # @intent description-only-tool-contract
        # Customization changes only the instructions a model sees; the wrapped
        # tool remains authoritative for accepted arguments and execution.
        # Keeping the source ToolSpec here lets this dataclass reject a name or
        # schema shape that the runtime tool cannot honor before the wrapper is
        # exposed to a catalog or provider. A wrapper-side check would duplicate
        # validation and could let prompt and execution contracts drift.
        if not isinstance(self.tool_spec, ToolSpec):
            raise ValueError("ToolCustomization.tool_spec must be a ToolSpec")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("ToolCustomization.description cannot be blank")
        if not isinstance(self.parameter_descriptions, Mapping):
            raise ValueError("ToolCustomization.parameter_descriptions must be a mapping")

        descriptions = dict(self.parameter_descriptions)
        self._validate_description_values(descriptions)
        if descriptions:
            declared = self._declared_parameter_names()
            unknown = sorted(set(descriptions) - declared)
            if unknown:
                names = ", ".join(repr(name) for name in unknown)
                raise ValueError(f"Tool '{self.tool_spec.name}' has no top-level parameter(s): {names}")
            self._validate_schema_properties(descriptions)
        object.__setattr__(self, "parameter_descriptions", MappingProxyType(descriptions))

    def _validate_description_values(self, descriptions: Mapping[str, str]) -> None:
        # Reject malformed override values before any schema transformation occurs.
        for name, description in descriptions.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Tool '{self.tool_spec.name}' parameter description name cannot be blank")
            if not isinstance(description, str) or not description.strip():
                raise ValueError(
                    f"Tool '{self.tool_spec.name}' parameter '{name}' description cannot be blank"
                )

    def _declared_parameter_names(self) -> frozenset[str]:
        # Use explicit schema properties when providers use that representation.
        schema = self.tool_spec.input_schema
        if schema is None:
            return frozenset(parameter.name for parameter in self.tool_spec.parameters)
        if not isinstance(schema, Mapping):
            raise ValueError(f"Tool '{self.tool_spec.name}' input_schema must be a mapping")
        properties = schema.get("properties")
        if not isinstance(properties, Mapping):
            raise ValueError(f"Tool '{self.tool_spec.name}' input_schema must expose top-level properties")
        if not all(isinstance(name, str) for name in properties):
            raise ValueError(f"Tool '{self.tool_spec.name}' input_schema property names must be strings")
        return frozenset(properties)

    def _validate_schema_properties(self, descriptions: Mapping[str, str]) -> None:
        # Confirm explicit properties can receive descriptions without partial mutation.
        if not descriptions or self.tool_spec.input_schema is None:
            return
        schema = self.tool_spec.input_schema
        properties = schema.get("properties") if isinstance(schema, Mapping) else None
        if not isinstance(properties, Mapping):
            raise ValueError(f"Tool '{self.tool_spec.name}' input_schema must expose top-level properties")
        for name in descriptions:
            if not isinstance(properties[name], Mapping):
                raise ValueError(
                    f"Tool '{self.tool_spec.name}' input_schema property '{name}' must be an object"
                )
        try:
            deepcopy(dict(schema))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Tool '{self.tool_spec.name}' input_schema could not be copied") from exc


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Runtime request for a named tool with JSON-like arguments."""

    tool_name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    call_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    activity: ToolCallActivity | None = None

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

    @classmethod
    def failure(
        cls,
        tool_name: str,
        output: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> "ToolResult":
        """Alias for error() — build a failed result."""
        return cls.error(tool_name, output, metadata=metadata)


@dataclass(frozen=True, slots=True)
class ToolCallContext:
    """Structured context for one agent-managed tool call attempt."""

    tool_name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    state: ToolCallState = ToolCallState.REQUESTED
    call_id: str | None = None
    result: ToolResult | None = None
    provider: str | None = None
    model: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    iteration_count: int | None = None
    activity: ToolCallActivity | None = None

    @property
    def name(self) -> str:
        """Compatibility alias for context rendering."""
        return self.tool_name

    @property
    def output(self) -> str | None:
        """Compatibility alias for context rendering."""
        return self.result.output if self.result else None

