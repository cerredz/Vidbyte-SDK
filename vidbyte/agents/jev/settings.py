"""FILE: vidbyte/agents/jev/settings.py

PURPOSE: Defines JevAgent's two opinionated public configuration objects: JevAgentSettings for the agents that generate, and JevRuntimeSettings for Jev's own decision policy, whose `continual` field holds JevContinualSettings for the done checks and continuations. JevRunBriefSettings configures the mid-run brief: the separate writer's model and limits and the brief's refresh cadence.
ROLE IN CODEBASE: JevAgent maps JevAgentSettings into BaseAgent and builds its preflight gate from both objects at construction, so JevRuntime never reads settings to decide what to ask.
ARCHITECTURE NOTE: The surface is intentionally closed; named Jev capabilities belong here as explicit settings instead of a generic decisions collection. JevAgentSettings holds the main agent and the JevSpecialist candidates Jev may hand a run to; JevRuntimeSettings holds the decision model, the preflight flags, the continuation settings (the done checks and their limits), and the tool-selector threshold.
COMMON MODIFICATION PATTERNS: Add a generative-agent field to JevAgentSettings or a Jev policy setting to JevRuntimeSettings, then implement its fixed policy in vidbyte/agents/jev/gate/ without exposing runtime replacement hooks.
KNOWN EDGE CASES: The generative provider cannot be TypeSafe because Jev is a decision model; neither generative nor decision API keys appear in repr output. Specialist titles must be unique because each one is a Choice option name. Preflight presets are validated by JevPreflightRegistry and done checks by JevDoneRegistry at construction, every continuation limit rejects booleans and non-integers, so no TypeSafe key is needed until a run asks Jev; the tool-selector threshold rejects booleans, non-finite values, and out-of-range probabilities.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-tool-selector.md, docs/design/jev-multipart-done-criteria.md, docs/design/jev-run-brief.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, tests/test_jev_tool_selector.py, tests/test_jev_done.py, tests/test_jev_run_brief.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.constants.jev import (
    JEV_BULK_DEFAULT_MAX_ITEMS,
    JEV_BULK_DEFAULT_MAX_PARALLEL_AGENTS,
    JEV_BULK_DEFAULT_PLANNER_MAX_ITERATIONS,
    JEV_BULK_DEFAULT_PLANNER_MAX_TOKENS,
    JEV_BULK_MIN_ITEMS,
    JEV_BULK_MIN_PARALLEL_AGENTS,
    JEV_BULK_MIN_PLANNER_MAX_ITERATIONS,
    JEV_BULK_MIN_PLANNER_MAX_TOKENS,
    JEV_COMPUTE_CLONES_DEFAULT,
    JEV_COMPUTE_CLONES_MAX,
    JEV_DONE_MAX_CONTINUATIONS,
    JEV_FAITHFUL_SCOPE_EXTRA_ITERATIONS,
    JEV_FAITHFUL_SCOPE_EXTRA_TOKENS,
    JEV_FAITHFUL_SCOPE_EXTRA_TOOL_CALLS,
    JEV_HANDOFF_MAX_ITERATIONS,
    JEV_HANDOFF_MAX_TOKENS,
    JEV_REVIEW_MAX_ITERATIONS,
    JEV_REVIEW_MAX_TOKENS,
    JEV_RUN_BRIEF_EVERY_ITERATIONS,
    JEV_RUN_BRIEF_MAX_ITERATIONS,
    JEV_RUN_BRIEF_MAX_TOKENS,
    JEV_RUN_STATE_MAX_ITERATIONS,
    JEV_RUN_STATE_MAX_TOKENS,
    JEV_SPECIALIST_MAX_COUNT,
    JEV_TOOL_SELECTOR_DEFAULT_THRESHOLD,
    JEV_TOOL_SELECTOR_MAX_THRESHOLD,
    JEV_TOOL_SELECTOR_MIN_THRESHOLD,
)
from vidbyte.lib.dataclasses.jev import JevSpecialist
from vidbyte.lib.dataclasses.model_configs import DecisionModelConfig
from vidbyte.lib.enums import (
    DecisionModelMode,
    JevContinuationGate,
    JevDoneCheck,
    JevDynamicComputeOption,
    JevPreflightPreset,
    ModelProvider,
)
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev import JevDoneRegistry, JevPreflightRegistry
from vidbyte.lib.jev.compute import JevComputeRegistry
from vidbyte.tools.security import PermissionPolicy


@dataclass(frozen=True, slots=True)
class JevBulkSettings:
    """Validated limits for one opt-in Jev bulk-work planning and execution pass."""

    max_parallel_agents: int = JEV_BULK_DEFAULT_MAX_PARALLEL_AGENTS
    max_items: int = JEV_BULK_DEFAULT_MAX_ITEMS
    planner_max_iterations: int = JEV_BULK_DEFAULT_PLANNER_MAX_ITERATIONS
    planner_max_tokens: int = JEV_BULK_DEFAULT_PLANNER_MAX_TOKENS

    def __post_init__(self) -> None:
        # Rejects invalid resource bounds before JevAgent builds its planner or worker pool.
        self._validate_limit("max_parallel_agents", JEV_BULK_MIN_PARALLEL_AGENTS)
        self._validate_limit("max_items", JEV_BULK_MIN_ITEMS)
        self._validate_limit("planner_max_iterations", JEV_BULK_MIN_PLANNER_MAX_ITERATIONS)
        self._validate_limit("planner_max_tokens", JEV_BULK_MIN_PLANNER_MAX_TOKENS)

    def _validate_limit(self, field_name: str, minimum: int) -> None:
        # Requires a whole-number resource limit and excludes bool, which is an int subclass.
        value = getattr(self, field_name)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ConfigurationError(
                f"JevBulkSettings.{field_name} must be an integer of at least {minimum}.",
                details={"received": repr(value)},
            )


@dataclass(frozen=True, slots=True)
class JevAgentSettings:
    """Validated settings for the agent JevAgent runs by default and the specialists Jev may hand a run to instead."""

    name: str
    system_prompt: str
    provider: ModelProvider | str
    model_name: str
    api_key: str | None = field(default=None, repr=False)
    temperature: float | None = None
    timeout_seconds: float | None = None
    tools: tuple[object, ...] = ()
    permission_policy: PermissionPolicy = field(default_factory=PermissionPolicy)
    loop: AgentLoopSettings = field(default_factory=AgentLoopSettings)
    agents: tuple[JevSpecialist, ...] = ()
    bulk_work: JevBulkSettings = field(default_factory=JevBulkSettings)

    def __post_init__(self) -> None:
        # Normalizes immutable inputs and rejects invalid agent configuration before runtime construction.
        # @intent opinionated-settings-fail-before-runtime
        # A frozen, validated settings object prevents later capability code from inheriting ambiguous policy inputs.
        self._validate_text(self.name, "name")
        self._validate_text(self.system_prompt, "system_prompt")
        self._validate_text(self.model_name, "model_name")
        provider = self._normalized_provider()
        if provider is ModelProvider.TYPESAFE:
            raise ConfigurationError("JevAgentSettings.provider must be a generative model provider, not TypeSafe.")
        object.__setattr__(self, "provider", provider)
        if isinstance(self.tools, (str, bytes)):
            raise ConfigurationError("JevAgentSettings.tools must be an iterable of tool objects, not a string.")
        try:
            object.__setattr__(self, "tools", tuple(self.tools))
        except TypeError as exc:
            raise ConfigurationError("JevAgentSettings.tools must be an iterable of tool objects.") from exc
        self._validate_temperature()
        self._validate_timeout()
        if not isinstance(self.permission_policy, PermissionPolicy):
            raise ConfigurationError("JevAgentSettings.permission_policy must be a PermissionPolicy instance.")
        if not isinstance(self.loop, AgentLoopSettings):
            raise ConfigurationError("JevAgentSettings.loop must be an AgentLoopSettings instance.")
        if not isinstance(self.bulk_work, JevBulkSettings):
            raise ConfigurationError("JevAgentSettings.bulk_work must be a JevBulkSettings instance.")
        self._validate_agents()

    def _validate_agents(self) -> None:
        # Freezes the specialists in the order given, which is also the order Jev reads their options.
        if isinstance(self.agents, (str, bytes)):
            raise ConfigurationError("JevAgentSettings.agents must be an iterable of JevSpecialist values, not a string.")
        try:
            agents = tuple(self.agents)
        except TypeError as exc:
            raise ConfigurationError("JevAgentSettings.agents must be an iterable of JevSpecialist values.") from exc
        if not all(isinstance(agent, JevSpecialist) for agent in agents):
            raise ConfigurationError("JevAgentSettings.agents must contain only JevSpecialist values.")
        if len(agents) > JEV_SPECIALIST_MAX_COUNT:
            raise ConfigurationError(f"JevAgentSettings.agents can hold at most {JEV_SPECIALIST_MAX_COUNT} specialists.")
        titles = [agent.title for agent in agents]
        if len(set(titles)) != len(titles):
            raise ConfigurationError("JevAgentSettings.agents must have unique titles.", details={"titles": titles})
        object.__setattr__(self, "agents", agents)

    @staticmethod
    def _validate_text(value: object, field_name: str) -> None:
        # Requires identity and prompt fields to be non-blank strings.
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"JevAgentSettings.{field_name} must be a non-blank string.")

    def _normalized_provider(self) -> ModelProvider:
        # Converts the public string form into the SDK provider enum exactly once.
        # @intent generative-and-decision-providers-stay-distinct
        # Canonicalizing here lets construction reject TypeSafe before a decision model is mistaken for a text runner.
        try:
            return self.provider if isinstance(self.provider, ModelProvider) else ModelProvider(self.provider)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"Unsupported model provider: {self.provider!r}") from exc

    def _validate_temperature(self) -> None:
        # Applies the shared generative-model temperature range without accepting booleans or non-finite numbers.
        value = self.temperature
        if value is None:
            return
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 2.0:
            raise ConfigurationError("JevAgentSettings.temperature must be a finite number between 0 and 2.")

    def _validate_timeout(self) -> None:
        # Requires a finite positive generative-model timeout when one is supplied.
        value = self.timeout_seconds
        if value is None:
            return
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0.0:
            raise ConfigurationError("JevAgentSettings.timeout_seconds must be a finite number greater than zero.")


@dataclass(frozen=True, slots=True)
class JevContinualSettings:
    """Validated done checks, continuation gate and cap, and run-state, reviewer, and handoff limits."""

    checks: tuple[JevDoneCheck | str, ...] = ()
    max_continuations: int = JEV_DONE_MAX_CONTINUATIONS
    run_state_max_iterations: int = JEV_RUN_STATE_MAX_ITERATIONS
    run_state_max_tokens: int = JEV_RUN_STATE_MAX_TOKENS
    handoff_max_iterations: int = JEV_HANDOFF_MAX_ITERATIONS
    handoff_max_tokens: int = JEV_HANDOFF_MAX_TOKENS
    faithful_scope_extra_iterations: int = JEV_FAITHFUL_SCOPE_EXTRA_ITERATIONS
    faithful_scope_extra_tokens: int = JEV_FAITHFUL_SCOPE_EXTRA_TOKENS
    faithful_scope_extra_tool_calls: int = JEV_FAITHFUL_SCOPE_EXTRA_TOOL_CALLS
    review_max_iterations: int = JEV_REVIEW_MAX_ITERATIONS
    review_max_tokens: int = JEV_REVIEW_MAX_TOKENS
    gate: JevContinuationGate | str = JevContinuationGate.SAME_CONTEXT

    def __post_init__(self) -> None:
        # Rejects unknown or repeated done checks and non-integer limits before JevAgent builds its run state.
        # @intent zero-continuations-still-checks
        # max_continuations may be 0: the checks still run and report on JevAgent.response, but a failed
        # check never sends the main agent back to work.
        object.__setattr__(self, "checks", JevDoneRegistry.validate(self.checks))
        self._validate_count("max_continuations", minimum=0)
        for field_name in ("run_state_max_iterations", "run_state_max_tokens", "handoff_max_iterations", "handoff_max_tokens", "review_max_iterations", "review_max_tokens"):
            self._validate_count(field_name, minimum=1)
        for field_name in ("faithful_scope_extra_iterations", "faithful_scope_extra_tokens", "faithful_scope_extra_tool_calls"):
            self._validate_count(field_name, minimum=0)
        try:
            gate = self.gate if isinstance(self.gate, JevContinuationGate) else JevContinuationGate(self.gate)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"Unsupported Jev continuation gate: {self.gate!r}") from exc
        if gate is JevContinuationGate.FRESH and not self.checks:
            raise ConfigurationError("JevContinualSettings.gate='fresh' requires at least one done check.")
        object.__setattr__(self, "gate", gate)

    def _validate_count(self, field_name: str, *, minimum: int) -> None:
        # Requires a whole number at or above the minimum, excluding bool.
        value = getattr(self, field_name)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ConfigurationError(f"JevContinualSettings.{field_name} must be an integer of at least {minimum}.", details={"received": repr(value)})


@dataclass(frozen=True, slots=True)
class JevRunBriefSettings:
    """Validated settings for the run brief: the writer's model, its loop limits, and how often the brief is refreshed.

    The writer is a separate, tool-free agent. Leave `provider` and `model_name` unset to reuse the main agent's
    model and key, set only `model_name` for a cheaper model from the same provider, or set both for another
    provider, which then uses `api_key` or that provider's environment variable instead of the main agent's key.
    """

    provider: ModelProvider | str | None = None
    model_name: str | None = None
    api_key: str | None = field(default=None, repr=False)
    temperature: float | None = None
    every_iterations: int = JEV_RUN_BRIEF_EVERY_ITERATIONS
    max_iterations: int = JEV_RUN_BRIEF_MAX_ITERATIONS
    max_tokens: int = JEV_RUN_BRIEF_MAX_TOKENS

    def __post_init__(self) -> None:
        self._validate_model()
        self._validate_temperature()
        for field_name in ("every_iterations", "max_iterations", "max_tokens"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ConfigurationError(f"JevRunBriefSettings.{field_name} must be an integer of at least 1.", details={"received": repr(value)})

    def _validate_model(self) -> None:
        # Normalizes the writer's provider and requires a model name with it.
        # @intent a-writer-provider-names-its-own-model
        # A model name belongs to one provider, so a writer moved to another provider cannot silently inherit the
        # main agent's model name; and Jev decides rather than writes, so it can never be the writer's provider.
        if self.model_name is not None and (not isinstance(self.model_name, str) or not self.model_name.strip()):
            raise ConfigurationError("JevRunBriefSettings.model_name must be a non-blank string when set.")
        if self.provider is None:
            return
        try:
            provider = self.provider if isinstance(self.provider, ModelProvider) else ModelProvider(self.provider)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"Unsupported model provider: {self.provider!r}") from exc
        if provider is ModelProvider.TYPESAFE:
            raise ConfigurationError("JevRunBriefSettings.provider must be a generative model provider, not TypeSafe.")
        if self.model_name is None:
            raise ConfigurationError("JevRunBriefSettings.provider requires model_name, because a model name belongs to one provider.")
        object.__setattr__(self, "provider", provider)

    def _validate_temperature(self) -> None:
        value = self.temperature
        if value is None:
            return
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 2.0:
            raise ConfigurationError("JevRunBriefSettings.temperature must be a finite number between 0 and 2.")


@dataclass(frozen=True, slots=True)
class JevComputeSettings:
    """Validated run-brief settings, enabled dynamic-compute options, and the clone count for the mid-run checkpoint.

    CLONE is opt-in because it is the one option that launches agents: add it to `dynamic_compute`, and `clones`
    sets how many copies of the main agent its one launch per run starts.
    """

    brief: JevRunBriefSettings = field(default_factory=JevRunBriefSettings)
    dynamic_compute: tuple[JevDynamicComputeOption | str, ...] = (
        JevDynamicComputeOption.FRESH_AGENT,
        JevDynamicComputeOption.FORK_AGENT,
        JevDynamicComputeOption.SUBAGENT,
    )
    clones: int = JEV_COMPUTE_CLONES_DEFAULT

    def __post_init__(self) -> None:
        if not isinstance(self.brief, JevRunBriefSettings):
            raise ConfigurationError("JevComputeSettings.brief must be a JevRunBriefSettings instance.")
        object.__setattr__(self, "dynamic_compute", JevComputeRegistry.validate(self.dynamic_compute))
        if isinstance(self.clones, bool) or not isinstance(self.clones, int) or not 1 <= self.clones <= JEV_COMPUTE_CLONES_MAX:
            raise ConfigurationError(f"JevComputeSettings.clones must be an integer from 1 through {JEV_COMPUTE_CLONES_MAX}.")


@dataclass(frozen=True, slots=True)
class JevRuntimeSettings:
    """Validated Jev decision policy: Vidbyte-managed decisions, preflight flags, continuation settings, and the tool-selector threshold."""

    decision: DecisionModelConfig = field(default_factory=DecisionModelConfig.vidbyte_managed, repr=False)
    preflight: tuple[JevPreflightPreset | str, ...] = ()
    continual: JevContinualSettings = field(default_factory=JevContinualSettings)
    tool_selector_threshold: float = JEV_TOOL_SELECTOR_DEFAULT_THRESHOLD
    compute: JevComputeSettings | None = None

    def __post_init__(self) -> None:
        # Keeps every JevAgent decision on the Vidbyte-managed path before runtime construction.
        if type(self.decision) is not DecisionModelConfig:
            raise ConfigurationError("JevRuntimeSettings.decision must be an exact DecisionModelConfig instance; subclasses are not supported.")
        if self.decision.mode is not DecisionModelMode.VIDBYTE_MANAGED:
            raise ConfigurationError("JevRuntimeSettings.decision must use VIDBYTE_MANAGED mode; direct TypeSafe configurations are supported only with standalone DecisionModelRunner.")
        object.__setattr__(self, "preflight", JevPreflightRegistry.validate(self.preflight))
        if not isinstance(self.continual, JevContinualSettings):
            raise ConfigurationError("JevRuntimeSettings.continual must be a JevContinualSettings instance.")
        if self.compute is not None and not isinstance(self.compute, JevComputeSettings):
            raise ConfigurationError("JevRuntimeSettings.compute must be a JevComputeSettings instance or None.")
        self._validate_tool_selector_threshold()

    def _validate_tool_selector_threshold(self) -> None:
        # Accepts calibrated probabilities on the closed unit interval, but excludes bool and non-finite values.
        value = self.tool_selector_threshold
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not JEV_TOOL_SELECTOR_MIN_THRESHOLD <= value <= JEV_TOOL_SELECTOR_MAX_THRESHOLD
        ):
            raise ConfigurationError("JevRuntimeSettings.tool_selector_threshold must be a finite probability between 0 and 1 inclusive.")
        object.__setattr__(self, "tool_selector_threshold", float(value))


__all__ = ["JevAgentSettings", "JevBulkSettings", "JevComputeSettings", "JevContinualSettings", "JevRunBriefSettings", "JevRuntimeSettings"]
