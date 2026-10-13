"""Context Protocol Header

Description:
    Defines immutable data contracts representing agent states, capabilities, and configurations.
Purpose:
    Exposes stable data structures like AgentCard and AgentMessage for registry and execution systems.
Architecture:
    - ProviderKeys: The matched provider keys and Vidbyte key that an agent's children carry.
    - AgentRunnerConfig: Primitive backend configuration, with the matched keys and the text-model mode.
    - PauseDuration: Validated whole-number delay for BaseAgent.pause().
    - AllowedToolNames: Validated, stripped tool names for the AgentLoopSettings.allowed_tools gate.
    - FallbackModel: One entry in an ordered agent fallback chain.
    - FallbackTransform: Rebuilt provider-derived state for a model switch.
    - AgentCard: Local agent description, capabilities, and tools.
    - AgentMessage: Actor-to-actor message payload.
    - AgentSpec: Construction-friendly agent settings block.
    - FinishReview: Accept, continue, or stop decision for one runtime finish attempt.
Relations:
    Used by vidbyte.agents.base, vidbyte.agents.registry, and orchestration strategies.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from vidbyte.lib.constants.jev import (
    VIDBYTE_API_KEY_PATTERN,
    VIDBYTE_API_KEY_PREFIX,
    VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND,
)
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.enums.text_model import TextModelMode
from vidbyte.lib.errors import AgentForkConfigurationError, ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.configs import (
        ActorRuntime,
        LinearRuntime,
        MctsSearchRuntime,
    )
    from vidbyte.agents.settings import AgentLoopSettings
    from vidbyte.agents.settings.fallback import AgentFallbackSettings
    from vidbyte.agents.settings.tool import ToolSettings
    from vidbyte.context.handoff import Handoff
    from vidbyte.context.manager import ContextManager
    from vidbyte.context.primitives import ContextItem
    from vidbyte.context.window import ContextWindowAlgorithm
    from vidbyte.lib.dataclasses.codex import CodexMessageData
    from vidbyte.lib.dataclasses.runner import RunnerHandle
    from vidbyte.lib.dataclasses.trace import TraceOption
    from vidbyte.lib.enums import AgentRuntimeType
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
    FINISH_REVIEW_REJECTED = "finish_review_rejected"
    ERROR = "error"


class FinishReviewAction(str, Enum):
    """What a runtime does with a finish attempt after reviewing it."""

    ACCEPT = "accept"
    CONTINUE = "continue"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class FinishReview:
    """Outcome of AgentMiddleware.review_finish for one finish attempt that the output contracts accepted."""

    action: FinishReviewAction = FinishReviewAction.ACCEPT
    feedback: str = ""

    def __post_init__(self) -> None:
        # @intent continue-feedback-is-never-empty
        # The runtime sends a continue review's feedback to the model as
        # the reason it may not finish yet, so a blank one would send an
        # empty message and leave the model guessing.
        if not isinstance(self.action, FinishReviewAction):
            raise ValueError(f"FinishReview action must be a FinishReviewAction, got {self.action!r}.")
        if not isinstance(self.feedback, str):
            raise ValueError(f"FinishReview feedback must be a string, got {type(self.feedback).__name__}.")
        if self.action is FinishReviewAction.CONTINUE and not self.feedback.strip():
            raise ValueError("FinishReview feedback must be non-blank text when the action is continue.")

    @classmethod
    def accept(cls) -> "FinishReview":
        """Let the run finish with the proposed answer."""
        return cls()

    @classmethod
    def continue_with(cls, feedback: str) -> "FinishReview":
        """Reject the finish attempt and send feedback back into the same loop."""
        return cls(action=FinishReviewAction.CONTINUE, feedback=feedback)

    @classmethod
    def stop(cls, feedback: str) -> "FinishReview":
        """Reject the finish attempt and end the run with the proposed answer and CONTRACT_UNSATISFIED; feedback is not sent to the model."""
        return cls(action=FinishReviewAction.STOP, feedback=feedback)


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
    allowed_tools: frozenset[str] | None = None

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
class AllowedToolNames:
    """Validated tool names for the AgentLoopSettings.allowed_tools gate, stripped like ToolSettings.denied_tools."""

    names: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject a bare string and blank names, and store each name stripped."""
        # @intent allowed-tools-validated-like-denied-tools
        # The one-tuple typo ("search") is a string whose gate would be single letters, silently denying the tool.
        if isinstance(self.names, (str, bytes)):
            raise ConfigurationError("AgentLoopSettings.allowed_tools must be an iterable of tool names, not a string.")
        names = tuple(str(value).strip() for value in self.names)
        if not all(names):
            raise ConfigurationError("AgentLoopSettings.allowed_tools cannot include blank tool names.")
        object.__setattr__(self, "names", names)


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
class ProviderKeys:
    """The matched form of a developer's api_keys list, which an agent's children carry.

    Developers pass api_keys as a plain list of key strings, and
    ProviderKeyMatcher.match builds this record from it: one key per
    provider, plus the Vidbyte key. A record passed in as api_keys is
    checked key by key and never re-bound. The repr shows provider
    names only, never a key.
    """

    providers: tuple[ModelProvider, ...] = ()
    keys: tuple[str, ...] = field(default=(), repr=False)
    vidbyte_api_key: str | None = field(default=None, repr=False)
    matched_primary: tuple[ModelProvider, ...] = ()
    matched_others: tuple[ModelProvider, ...] = ()

    def __post_init__(self) -> None:
        """Coerce provider names to members, and check that the keys line up with them."""
        # Turn every provider name into its enum member, so a lookup by
        # name and a lookup by member find the same key.
        for name in ("providers", "matched_primary", "matched_others"):
            object.__setattr__(self, name, self._members(name, getattr(self, name)))
        # One key per provider: a repeated provider would make key_for
        # ambiguous.
        if len(set(self.providers)) != len(self.providers):
            raise ConfigurationError("ProviderKeys.providers must not name a provider twice.", details={"field": "providers"})
        # Each provider needs exactly one usable key beside it.
        object.__setattr__(self, "keys", self._checked_keys(self.keys, len(self.providers)))
        # The Vidbyte key only ever goes to the gateway, so its format
        # is checked here, where it enters, without reading the
        # environment.
        self._check_vidbyte_api_key(self.vidbyte_api_key)

    @staticmethod
    def _members(name: str, values: object) -> tuple[ModelProvider, ...]:
        """Return values as ModelProvider members, refusing a bare string or an unknown name."""
        # @intent provider-names-become-members
        # A bare string would be read letter by letter, so it is refused
        # rather than split into one-letter provider names.
        message = f"ProviderKeys.{name} must be a tuple of ModelProvider members or their names."
        if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
            raise ConfigurationError(message, details={"field": name})
        try:
            return tuple(ModelProvider(value) for value in values)
        except (TypeError, ValueError):
            raise ConfigurationError(message, details={"field": name}) from None

    @staticmethod
    def _checked_keys(keys: object, count: int) -> tuple[str, ...]:
        """Return keys as a tuple of non-blank, stripped strings, one for each provider."""
        if not isinstance(keys, (tuple, list)) or len(keys) != count:
            raise ConfigurationError("ProviderKeys.keys must hold exactly one key for each provider.", details={"field": "keys"})
        for index, key in enumerate(keys):
            if not isinstance(key, str) or not key.strip() or key != key.strip():
                raise ConfigurationError(f"ProviderKeys.keys[{index}] must be a non-blank string without surrounding spaces.", details={"field": "keys", "index": index})
        return tuple(keys)

    @staticmethod
    def _check_vidbyte_api_key(key: object) -> None:
        """Refuse a Vidbyte key that is not a string or not a live key."""
        # @intent vidbyte-key-format-checked-where-it-enters
        # A malformed Vidbyte key fails here, at construction, with
        # the managed-credential error kind, so it never reaches the
        # gateway.
        details = {"error_kind": VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND}
        if key is None:
            return
        if not isinstance(key, str):
            raise ConfigurationError("vidbyte_api_key must be a string or None.", details=details)
        if re.fullmatch(VIDBYTE_API_KEY_PATTERN, key) is None:
            raise ConfigurationError(f"The managed Vidbyte API key must be a live key in the {VIDBYTE_API_KEY_PREFIX} format.", details=details)

    def key_for(self, provider: ModelProvider | str) -> str | None:
        """Return the key matched to provider, given as a member or its name, or None."""
        # @intent key-lookup-never-guesses
        # Only an exact provider match returns a key, so a key is never
        # sent to a provider it was not matched to.
        for held, key in zip(self.providers, self.keys, strict=True):
            if held == provider:
                return key
        return None


@dataclass(frozen=True, slots=True)
class AgentRunnerConfig:
    """Primitive runner settings captured by an SDK agent."""

    api_keys: ProviderKeys = field(default_factory=ProviderKeys, repr=False)
    provider: str | None = None
    model_name: str | None = None
    temperature: float | None = None
    run_id: str | None = None
    timeout_seconds: float | None = None
    model_mode: TextModelMode = TextModelMode.AUTO

    def __post_init__(self) -> None:
        """Refuse a raw key list or a mode that is not the enum."""
        # @intent runner-config-carries-a-matched-record
        # BaseAgent matches the developer's list before it builds this
        # config, so a raw list here means matching was skipped; the
        # message names no key.
        if not isinstance(self.api_keys, ProviderKeys):
            raise ConfigurationError("AgentRunnerConfig.api_keys must be a ProviderKeys record; BaseAgent matches the developer's list first.")
        if not isinstance(self.model_mode, TextModelMode):
            raise ConfigurationError("AgentRunnerConfig.model_mode must be a TextModelMode value.")


@dataclass(frozen=True, slots=True)
class FallbackModel:
    """One model in an ordered agent fallback chain."""

    provider: str
    model: str
    temperature: float | None = None

    def __post_init__(self) -> None:
        """Normalize an enum provider to its string value and reject blank provider or model names."""
        # @intent fallback-provider-is-a-plain-string
        # A ModelProvider member would otherwise render as 'ModelProvider.ANTHROPIC' in identity() and run metadata.
        if isinstance(self.provider, Enum):
            object.__setattr__(self, "provider", self.provider.value)
        if not str(self.provider).strip():
            raise ValueError("FallbackModel.provider cannot be empty")
        if not str(self.model).strip():
            raise ValueError("FallbackModel.model cannot be empty")

    def identity(self) -> str:
        """Return the 'provider/model' label used in metadata and error records."""
        return f"{self.provider}/{self.model}"

    def __repr__(self) -> str:
        """Return a developer-readable string naming the model and its temperature."""
        temperature = f", temperature={self.temperature!r}" if self.temperature is not None else ""
        return f"FallbackModel({self.identity()!r}{temperature})"


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
    # Provider-specific deterministic result data; absent for non-Codex agents.
    codex: CodexMessageData | None = None


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
        # @intent fork-drop-tools-validated-like-denied-tools
        # A typo like ("delete_record") is a str, so the drop set would hold its characters and the child keeps the tool.
        if isinstance(self.drop_tools, (str, bytes)):
            raise AgentForkConfigurationError("AgentForkSettings.drop_tools must be an iterable of tool names, not a string.")
        drop_tools = tuple(str(name).strip() for name in self.drop_tools)
        if not all(drop_tools):
            raise AgentForkConfigurationError("AgentForkSettings.drop_tools cannot include blank tool names.")
        object.__setattr__(self, "drop_tools", drop_tools)
        if self.model_name is not None and not isinstance(self.model_name, str):
            raise AgentForkConfigurationError(
                "model_name must be a single model name string; use AggregateAgent for multi-model aggregation."
            )
