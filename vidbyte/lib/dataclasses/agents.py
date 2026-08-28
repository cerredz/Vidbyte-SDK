"""Context Protocol Header

FILE: vidbyte/lib/dataclasses/agents.py
PURPOSE: Defines shared, dependency-light contracts for agent execution,
         fallback transitions, and agent-facing configuration. It owns the
         validation that higher-level agent packages must not duplicate while
         exposing stable records such as AgentCard and AgentMessage.
ROLE IN CODEBASE: Imported by agents, runtimes, registries, orchestration
                  strategies, and public package shims. It may depend on lib
                  enums/errors, but must not import vidbyte.agents at module
                  import time.
ARCHITECTURE NOTE: This is the dependency-light contract layer. FallbackModel
                    identifies one catalog model; AgentFallbackConfig validates
                    the resolved chain; FallbackTransitionRequest validates
                    mutable runtime state before a switch. AgentRunnerConfig,
                    PauseDuration, AgentCard, AgentMessage, and AgentSpec remain
                    the other shared agent contracts.
FUNCTION INVENTORY: FallbackModel validates and identifies a catalog model;
    AgentFallbackConfig validates the complete fallback chain;
    FallbackTransitionRequest validates in-flight transition state;
    FallbackTransition carries a validated transform and audit record; the
    remaining dataclasses provide existing agent, runner, message, and fork
    contracts. Existing agent/fallback and runtime tests cover these contracts.
COMMON MODIFICATION PATTERNS: Add cross-package fallback invariants here when
    settings construction and runtime transitions need the same rule. Keep
    public data contracts here and update ``vidbyte/lib/dataclasses/__init__.py``
    when a public export changes.
WHAT NOT TO DO: Do not import AgentFallback, settings, runners, provider
    adapters, auth, or network clients at module scope. Lazy registry imports
    prevent an SDK bootstrap cycle; higher-level behavior belongs elsewhere.
KNOWN EDGE CASES: Policy arrays contain one value per transition (resolved
    chain length minus one). Transition history is intentionally mutable because
    the owning runtime appends credential-free audit records in place. Provider
    model validation must remain lazy at registry boundaries to avoid bootstrap
    cycles.
COMMON ERRORS: FallbackConfigurationError covers declaration failures;
    FallbackTransitionError covers malformed in-flight state; existing agent
    configuration errors retain their established classes.
TEST FILES: Existing agent/fallback and runtime tests plus scripts/run_ci.py.
CONCURRENCY MODEL: Contracts are frozen, but attempts/errors lists are shared
    with the owning single-run runtime and are mutated only during that run.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-fallback-policies.md
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from numbers import Real
from typing import TYPE_CHECKING, Any

from vidbyte.lib.enums import FallbackPolicyType
from vidbyte.lib.errors import (
    AgentForkConfigurationError,
    ConfigurationError,
    FallbackConfigurationError,
    FallbackTransitionError,
)

if TYPE_CHECKING:
    from vidbyte.agents.fallback.settings import AgentFallbackSettings
    from vidbyte.agents.runtimes.configs import (
        ActorRuntime,
        LinearRuntime,
        MctsSearchRuntime,
    )
    from vidbyte.agents.settings import AgentLoopSettings
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
    tool_settings: ToolSettings | None = None

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
        """Reject entries that do not name a supported provider/model pair."""
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise FallbackConfigurationError("FallbackModel.provider must be a non-empty string.")
        if not isinstance(self.model, str) or not self.model.strip():
            raise FallbackConfigurationError("FallbackModel.model must be a non-empty string.")
        try:
            from vidbyte.lib.registries.models import ProviderModelRegistry

            ProviderModelRegistry.validate_provider_model_pair(self.provider, self.model)
        except ConfigurationError as exc:
            raise FallbackConfigurationError(
                f"FallbackModel '{self.provider}/{self.model}' is not a supported SDK model.",
                details={"provider": self.provider, "model": self.model},
            ) from exc

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
class AgentFallbackConfig:
    """Validated immutable input contract consumed by AgentFallback."""

    models: Sequence[FallbackModel]
    fallback_on: Sequence[type[BaseException]] = ()
    policies: Sequence[object] = ()

    def __post_init__(self) -> None:
        """Normalize collections and validate the complete fallback contract."""
        try:
            models = tuple(self.models)
            fallback_on = tuple(self.fallback_on)
            policies = tuple(self.policies)
        except TypeError as exc:
            raise FallbackConfigurationError("Fallback configuration collections must be iterable.") from exc
        object.__setattr__(self, "models", models)
        object.__setattr__(self, "fallback_on", fallback_on)
        object.__setattr__(self, "policies", policies)
        self._validate_models()
        self._validate_error_types()
        self.validate_policies(self.policies, transition_count=len(self.models) - 1)

    def _validate_models(self) -> None:
        # The chain owns resolved FallbackModel values so provider/model validation happens once at its boundary.
        if not self.models:
            raise FallbackConfigurationError("AgentFallbackConfig.models must contain the primary model.")
        for position, model in enumerate(self.models):
            if not isinstance(model, FallbackModel):
                raise FallbackConfigurationError(
                    f"AgentFallbackConfig.models[{position}] must be a FallbackModel, got {type(model).__name__}.",
                    details={"position": position, "actual_type": type(model).__name__},
                )

    def _validate_error_types(self) -> None:
        # Every error filter must be usable by AgentFallback.is_model_error.
        for position, error_type in enumerate(self.fallback_on):
            if not isinstance(error_type, type) or not issubclass(error_type, BaseException):
                raise FallbackConfigurationError(
                    f"AgentFallbackConfig.fallback_on[{position}] must be an exception class, got {error_type!r}.",
                    details={"position": position, "value": repr(error_type)},
                )

    @classmethod
    def validate_policies(cls, policies: Sequence[object], *, transition_count: int) -> None:
        """Validate policy kinds, capabilities, dimensions, and numeric values."""
        if isinstance(transition_count, bool) or not isinstance(transition_count, int) or transition_count < 0:
            raise FallbackConfigurationError(f"Fallback transition count must be a non-negative integer, got {transition_count!r}.")
        try:
            entries = tuple(policies)
        except TypeError as exc:
            raise FallbackConfigurationError("Fallback policies must be iterable.") from exc
        seen: set[FallbackPolicyType] = set()
        for position, policy in enumerate(entries):
            kind = getattr(policy, "policy_type", None)
            if not isinstance(kind, FallbackPolicyType):
                raise FallbackConfigurationError(
                    f"Fallback policy at position {position} must declare a FallbackPolicyType, got {kind!r}.",
                    details={"position": position, "policy_type": repr(kind)},
                )
            if kind in seen:
                raise FallbackConfigurationError(
                    f"Fallback policy type '{kind.value}' was declared more than once; use one policy per kind.",
                    details={"policy_type": kind.value},
                )
            seen.add(kind)
            values = cls._policy_values(policy, position)
            cls._validate_hop_count(policy, values, transition_count)
            cls._validate_hop_elements(policy, values)
            required_method = "deadline_for" if kind is FallbackPolicyType.LATENCY else "budget_for"
            if not callable(getattr(policy, required_method, None)):
                raise FallbackConfigurationError(
                    f"Fallback policy '{type(policy).__name__}' declares {kind.value!r} but lacks {required_method}().",
                    details={"policy_type": kind.value, "required_method": required_method},
                )

    @staticmethod
    def _policy_values(policy: object, position: int) -> tuple[object, ...]:
        hop_values = getattr(policy, "hop_values", None)
        if not callable(hop_values):
            raise FallbackConfigurationError(
                f"Fallback policy at position {position} must expose hop_values().",
                details={"position": position, "policy": type(policy).__name__},
            )
        try:
            return tuple(hop_values())
        except (TypeError, ValueError) as exc:
            raise FallbackConfigurationError(
                f"Fallback policy '{type(policy).__name__}' returned an invalid hop-value sequence.",
                details={"policy": type(policy).__name__},
            ) from exc

    @staticmethod
    def _validate_hop_count(policy: object, values: tuple[object, ...], expected: int) -> None:
        if len(values) == expected:
            return
        raise FallbackConfigurationError(
            f"{type(policy).__name__} declares {len(values)} hop value(s), but this chain has {expected} fallback "
            f"model(s) ({expected + 1} total including the primary), which means {expected} possible transitions. "
            "Every per-hop policy needs exactly one value per transition: one for the primary and one for each "
            "fallback except the last, which has nowhere left to fall back to.",
            details={"policy": type(policy).__name__, "expected_hop_count": expected, "actual_hop_count": len(values)},
        )

    @staticmethod
    def _validate_hop_elements(policy: object, values: tuple[object, ...]) -> None:
        for position, value in enumerate(values):
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) or value <= 0:
                raise FallbackConfigurationError(
                    f"{type(policy).__name__} hop value at position {position} must be a positive finite number, got {value!r}.",
                    details={"policy": type(policy).__name__, "position": position, "value": repr(value)},
                )


@dataclass(frozen=True, slots=True)
class FallbackTransitionRequest:
    """Strict runtime input contract for one error- or policy-driven transition."""

    agent_name: str
    chain_length: int
    index: int
    handle: RunnerHandle
    provider: str
    tools: Tools
    messages: Sequence[Mapping[str, Any]]
    attempts: list[dict[str, str]]
    errors: list[BaseException]
    error: BaseException | None = None
    reason: str | None = None
    cost_usd: float | None = None

    def __post_init__(self) -> None:
        """Reject malformed runtime state before fallback logic can mutate it."""
        self._validate_identity()
        self._validate_trigger()
        self._validate_dependencies()
        self._validate_messages()
        self._validate_history()

    def _validate_identity(self) -> None:
        if not isinstance(self.agent_name, str) or not self.agent_name.strip():
            raise FallbackTransitionError("FallbackTransitionRequest.agent_name must be a non-empty string.")
        if isinstance(self.chain_length, bool) or not isinstance(self.chain_length, int) or self.chain_length <= 0:
            raise FallbackTransitionError("FallbackTransitionRequest.chain_length must be a positive integer.")
        if isinstance(self.index, bool) or not isinstance(self.index, int) or not 0 <= self.index < self.chain_length:
            raise FallbackTransitionError(
                f"FallbackTransitionRequest.index {self.index!r} is outside chain range 0..{self.chain_length - 1}.",
                details={"index": self.index, "chain_length": self.chain_length},
            )
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise FallbackTransitionError("FallbackTransitionRequest.provider must be a non-empty string.")
        try:
            from vidbyte.lib.registries.models import ProviderModelRegistry

            ProviderModelRegistry.validate_provider(self.provider)
        except ConfigurationError as exc:
            raise FallbackTransitionError(
                f"FallbackTransitionRequest.provider '{self.provider}' is not in the SDK provider catalog.",
                details={"provider": self.provider},
            ) from exc

    def _validate_trigger(self) -> None:
        if (self.error is None) == (self.reason is None):
            raise FallbackTransitionError("Provide exactly one of error or reason for a fallback transition.")
        if self.error is not None and not isinstance(self.error, BaseException):
            raise FallbackTransitionError("FallbackTransitionRequest.error must be an exception instance.")
        if self.reason is not None:
            if not isinstance(self.reason, str) or not self.reason.strip() or len(self.reason) > 128:
                raise FallbackTransitionError("FallbackTransitionRequest.reason must be a non-empty string of at most 128 characters.")
            if self.cost_usd is None and self.reason == "cost_budget_exceeded":
                raise FallbackTransitionError("A cost-budget transition must include the current cost rollup.")
        elif self.cost_usd is not None:
            raise FallbackTransitionError("FallbackTransitionRequest.cost_usd is only valid for a policy transition.")
        if self.cost_usd is not None and (isinstance(self.cost_usd, bool) or not isinstance(self.cost_usd, Real) or not math.isfinite(self.cost_usd) or self.cost_usd < 0):
            raise FallbackTransitionError("FallbackTransitionRequest.cost_usd must be a finite non-negative number.")

    def _validate_dependencies(self) -> None:
        if not callable(getattr(self.handle, "invoke", None)) or not callable(getattr(self.handle, "with_runner", None)):
            raise FallbackTransitionError("FallbackTransitionRequest.handle must expose invoke() and with_runner().")
        if not callable(getattr(self.tools, "provider_schemas", None)):
            raise FallbackTransitionError("FallbackTransitionRequest.tools must expose provider_schemas().")

    def _validate_messages(self) -> None:
        if isinstance(self.messages, (str, bytes)) or not isinstance(self.messages, Sequence):
            raise FallbackTransitionError("FallbackTransitionRequest.messages must be a sequence of provider message mappings.")
        if len(self.messages) > 10_000:
            raise FallbackTransitionError("FallbackTransitionRequest.messages cannot contain more than 10,000 messages.")
        for position, message in enumerate(self.messages):
            if not isinstance(message, Mapping):
                raise FallbackTransitionError(f"Fallback message {position} must be a mapping.")
            role = message.get("role")
            if not isinstance(role, str) or not role.strip():
                raise FallbackTransitionError(f"Fallback message {position} must contain a non-empty string role.")
            content = message.get("content", message.get("parts", ""))
            if len(str(content)) > 1_000_000:
                raise FallbackTransitionError(f"Fallback message {position} exceeds the 1,000,000-character content limit.")

    def _validate_history(self) -> None:
        if not isinstance(self.attempts, list) or not isinstance(self.errors, list):
            raise FallbackTransitionError("FallbackTransitionRequest.attempts and errors must be mutable lists.")
        if len(self.errors) > len(self.attempts):
            raise FallbackTransitionError("Fallback transition errors cannot outnumber recorded attempts.")
        for position, attempt in enumerate(self.attempts):
            if not isinstance(attempt, Mapping) or set(attempt) != {"from", "to", "error_type"} or not all(isinstance(value, str) for value in attempt.values()):
                raise FallbackTransitionError(f"Fallback attempt {position} has an invalid credential-free record shape.")
        if not all(isinstance(error, BaseException) for error in self.errors):
            raise FallbackTransitionError("Fallback transition errors must contain exception instances.")


@dataclass(frozen=True, slots=True)
class FallbackTransition:
    """Validated result of one fallback transition, including its audit record."""

    transform: FallbackTransform
    attempt: Mapping[str, str]


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
