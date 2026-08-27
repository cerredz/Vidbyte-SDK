"""Context Protocol Header

Description:
    Defines immutable data contracts representing agent states, capabilities, and configurations.
Purpose:
    Exposes stable data structures like AgentCard and AgentMessage for registry and execution systems.
Architecture:
    - AgentRunnerConfig: Primitive backend configuration.
    - PauseDuration: Validated whole-number delay for BaseAgent.pause().
    - FallbackModel: One entry in an ordered agent fallback chain.
    - FallbackTransform: Rebuilt provider-derived state for a model switch.
    - AgentCard: Local agent description, capabilities, and tools.
    - AgentMessage: Actor-to-actor message payload.
    - AgentSpec: Construction-friendly agent settings block.
Relations:
    Used by vidbyte.agents.base, vidbyte.agents.registry, and orchestration strategies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from vidbyte.lib.errors import AgentForkConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.configs import ActorRuntime, LinearRuntime, MctsSearchRuntime
    from vidbyte.agents.settings import AgentLoopSettings
    from vidbyte.agents.settings.fallback import AgentFallbackSettings
    from vidbyte.agents.settings.tool import ToolSettings
    from vidbyte.context.handoff import Handoff
    from vidbyte.context.manager import ContextManager
    from vidbyte.context.primitives import ContextItem
    from vidbyte.context.window import ContextWindowAlgorithm
    from vidbyte.lib.dataclasses.runner import RunnerHandle
    from vidbyte.lib.dataclasses.trace import TraceOption
    from vidbyte.lib.enums import AgentRuntimeType, ModelProvider
    from vidbyte.middleware import AgentMiddleware
    from vidbyte.tools.catalog import Tools
    from vidbyte.tools.types import ToolCallContext


class AgentStopReason(str, Enum):
    """Machine-readable reason an agent runtime stopped."""

    FINAL_RESPONSE = "final_response"
    IS_DONE = "is_done"
    MAX_ITERATIONS = "max_iterations"
    MAX_TOKENS = "max_tokens"
    MAX_TOOL_CALLS = "max_tool_calls"
    MAX_CALLS_PER_ITERATION = "max_calls_per_iteration"
    MAX_IDENTICAL_CALLS = "max_identical_calls"
    MAX_CONSECUTIVE_FAILURES = "max_consecutive_failures"
    MAX_ERROR_CALLS = "max_error_calls"
    SLIDING_WINDOW_MAX_CALLS = "sliding_window_max_calls"
    TIMEOUT = "timeout"
    MIDDLEWARE_ABORT = "middleware_abort"
    TOOL_SETTINGS_DENIED = "tool_settings_denied"
    TOOL_LOOP_LIMIT = "tool_loop_limit"
    CONTRACT_UNSATISFIED = "contract_unsatisfied"
    VERIFICATION_FAILED = "verification_failed"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class AgentRuntimeConfig:
    """Internal direct-runner loop budgets for an agent."""

    max_iterations: int | None = None
    max_tokens: int | None = None
    max_tool_calls: int | None = None
    timeout_seconds: float | None = None
    compaction_trigger_tokens: int | None = None
    compaction_target_tokens: int | None = None
    tool_settings: "ToolSettings | None" = None

    def __post_init__(self) -> None:
        """Validate optional budget values."""
        for field_name in (
            "max_iterations",
            "max_tokens",
            "max_tool_calls",
            "compaction_trigger_tokens",
            "compaction_target_tokens",
        ):
            value = getattr(self, field_name)
            if value is not None and value <= 0:
                raise ValueError(f"{field_name} must be greater than zero when provided.")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero when provided.")


@dataclass(frozen=True, slots=True)
class PauseDuration:
    """Validated whole-number delay in seconds for a cooperative agent pause."""

    seconds: int

    def __post_init__(self) -> None:
        """Reject non-integer, boolean, and negative delays."""
        if isinstance(self.seconds, bool) or not isinstance(self.seconds, int):
            raise ValueError("PauseDuration.seconds must be an integer.")
        if self.seconds < 0:
            raise ValueError("PauseDuration.seconds must be non-negative.")


@dataclass(frozen=True, slots=True)
class AgentRuntimeStats:
    """Summary accounting for one agent runtime execution."""

    iteration_count: int = 0
    tokens_used: int | None = None
    tool_call_count: int = 0
    stop_reason: AgentStopReason = AgentStopReason.FINAL_RESPONSE


@dataclass(frozen=True, slots=True)
class AgentIterationSnapshot:
    """Observable direct-runtime state captured after one completed iteration."""

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
    temperature: float | None = None
    run_id: str | None = None
    timeout_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class FallbackModel:
    """One model in an ordered agent fallback chain."""

    provider: str
    model: str
    api_key: str | None = None
    temperature: float | None = None

    def __post_init__(self) -> None:
        """Reject entries that do not name both a provider and a model."""
        if not str(self.provider).strip():
            raise ValueError("FallbackModel.provider cannot be empty")
        if not str(self.model).strip():
            raise ValueError("FallbackModel.model cannot be empty")

    def identity(self) -> str:
        """Return the 'provider/model' label used in metadata and error records."""
        return f"{self.provider}/{self.model}"

    def __repr__(self) -> str:
        """Return a developer-readable string that never exposes the API key."""
        key = ", api_key='***'" if self.api_key else ""
        temperature = f", temperature={self.temperature!r}" if self.temperature is not None else ""
        return f"FallbackModel({self.identity()!r}{key}{temperature})"


@dataclass(frozen=True, slots=True)
class FallbackTransform:
    """Rebuilt provider-derived state for the model a run is switching to."""

    index: int
    handle: RunnerHandle
    provider: str
    tool_schemas: tuple[dict[str, Any], ...]
    messages: list[dict[str, Any]]
    context_reset: bool
    model: FallbackModel = field(repr=False)


@dataclass(frozen=True, slots=True)
class AgentInput:
    """Typed agent input for prompt metadata and per-call context."""

    prompt: str
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
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentMessage:
    """In-process message passed between agents."""

    sender: str
    recipient: str
    content: str
    message_type: str = "response"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    # The validated instance when the sending agent declared an output_schema, else None.
    structured: Any = None


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


@dataclass(frozen=True, slots=True)
class AgentForkSettings:
    """Validated, self-describing bundle of every BaseAgent.fork override.

    Each field defaults to a value that means "inherit from the parent agent".
    Passing an explicit value overrides that single part of the child branch.
    Validation happens eagerly in __post_init__ so an invalid fork request fails
    at settings-construction time rather than deep inside the fork pipeline.
    """

    name: str | None = None
    tools: Sequence[object] | Tools | None = None
    add_tools: Sequence[object] = ()
    drop_tools: Sequence[str] = ()
    system_prompt: str | None = None
    metadata: dict[str, Any] | None = None
    middleware: Sequence[AgentMiddleware] | None = None
    context_items: Sequence[ContextItem] | None = None
    context_manager: ContextManager | None = None
    algorithm: ContextWindowAlgorithm | str | None = None
    include_history: bool = False
    history: Sequence[AgentMessage] | None = None
    trace_option: TraceOption | None = None
    include_run_state: bool = False
    output_schema: type | Mapping[str, Any] | None = None
    agent_loop_settings: AgentLoopSettings | None = None
    max_iterations: int | None = None
    handoff: Handoff | None = None
    runtime: AgentRuntimeType | str | LinearRuntime | MctsSearchRuntime | ActorRuntime | None = None
    run_id: str | None = None
    model_name: str | None = None
    provider: ModelProvider | str | None = None
    temperature: float | None = None
    fallback: Sequence[str | FallbackModel] | AgentFallbackSettings | None = None
    mcp: bool = True
    inherit_mcp: bool | None = None

    def __post_init__(self) -> None:
        """Reject internally inconsistent or out-of-range fork requests."""
        if self.agent_loop_settings is not None and self.max_iterations is not None:
            raise AgentForkConfigurationError("Pass either agent_loop_settings or max_iterations, not both.")
        if self.max_iterations is not None and self.max_iterations <= 0:
            raise AgentForkConfigurationError("max_iterations must be greater than zero when provided.")
        if self.temperature is not None and not 0.0 <= self.temperature <= 2.0:
            raise AgentForkConfigurationError("temperature must be between 0 and 2 when provided.")
        if self.model_name is not None and not isinstance(self.model_name, str):
            raise AgentForkConfigurationError(
                "model_name must be a single model name string; use AggregateAgent for multi-model aggregation."
            )
