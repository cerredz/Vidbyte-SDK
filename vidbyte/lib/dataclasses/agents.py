"""Context Protocol Header

Description:
    Defines immutable data contracts representing agent states, capabilities, and configurations.
Purpose:
    Exposes stable data structures like AgentCard and AgentMessage for registry and execution systems.
Architecture:
    - AgentRunnerConfig: Primitive backend configuration.
    - AgentCard: Local agent description, capabilities, and tools.
    - AgentMessage: Actor-to-actor message payload.
    - AgentSpec: Construction-friendly agent settings block.
Relations:
    Used by vidbyte.agents.base, vidbyte.agents.registry, and orchestration strategies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Mapping

from vidbyte.lib.enums import ModelModality

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager
    from vidbyte.context.primitives import ContextItem
    from vidbyte.context.window import ContextWindowAlgorithm
    from vidbyte.tools.types import ToolCallContext


class AgentStopReason(str, Enum):
    """Machine-readable reason an agent runtime stopped."""

    FINAL_RESPONSE = "final_response"
    IS_DONE = "is_done"
    MAX_ITERATIONS = "max_iterations"
    MAX_TOKENS = "max_tokens"
    MIDDLEWARE_ABORT = "middleware_abort"
    TOOL_LOOP_LIMIT = "tool_loop_limit"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class AgentRuntimeConfig:
    """Internal direct-runner loop budgets for an agent."""

    max_iterations: int | None = None
    max_tokens: int | None = None
    compaction_trigger_tokens: int | None = None
    compaction_target_tokens: int | None = None

    def __post_init__(self) -> None:
        """Validate optional budget values."""
        for field_name in (
            "max_iterations",
            "max_tokens",
            "compaction_trigger_tokens",
            "compaction_target_tokens",
        ):
            value = getattr(self, field_name)
            if value is not None and value <= 0:
                raise ValueError(f"{field_name} must be greater than zero when provided.")


@dataclass(frozen=True, slots=True)
class AgentRuntimeStats:
    """Summary accounting for one agent runtime execution."""

    iteration_count: int = 0
    tokens_used: int | None = None
    tool_call_count: int = 0
    stop_reason: AgentStopReason = AgentStopReason.FINAL_RESPONSE


@dataclass(frozen=True, slots=True)
class AgentIterationSnapshot:
    """Observable direct-runtime state captured after one non-final iteration."""

    iteration_count: int
    message: str
    provider: str
    assistant_output: str | None = None
    tool_calls: tuple[ToolCallContext, ...] = ()
    tokens_used: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentRunnerConfig:
    """Primitive runner settings captured by an SDK agent."""

    api_key: str | None = None
    provider: str | None = None
    model_name: str | None = None
    modality: ModelModality | str = ModelModality.AUTO
    temperature: float | None = None
    run_id: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentInput:
    """Typed agent input for reliable modality routing."""

    prompt: str
    modality: ModelModality | str = ModelModality.AUTO
    metadata: Mapping[str, Any] = field(default_factory=dict)
    context_items: tuple[ContextItem, ...] = ()
    context_manager: ContextManager | None = None


@dataclass(frozen=True, slots=True)
class AgentCard:
    """Local capability declaration for an agent."""

    name: str
    description: str
    system_prompt: str
    capabilities: tuple[str, ...] = ()
    tool_names: tuple[str, ...] = ()
    mcp_tool_names: tuple[str, ...] = ()
    mcp_server_names: tuple[str, ...] = ()
    modalities: tuple[ModelModality, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentMessage:
    """In-process message passed between agents."""

    sender: str
    recipient: str
    content: str
    message_type: str = "response"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentMetadata:
    """Metadata for exposing an agent as a tool."""

    name: str = ""
    description: str = ""
    use_cases: str = ""


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """Construction-friendly agent description."""

    name: str
    system_prompt: str
    description: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    context_items: tuple[ContextItem, ...] = ()
    context_manager: ContextManager | None = None
    algorithm: ContextWindowAlgorithm | str | None = None
