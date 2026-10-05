"""FILE: vidbyte/agents/jev/settings.py

PURPOSE: Defines JevAgent's two opinionated public configuration objects: JevAgentSettings for the agents that generate, and JevRuntimeSettings for Jev's own decision policy, whose `continual` field holds JevContinualSettings for the done checks and continuations. JevRunBriefSettings configures the mid-run brief: the separate writer's model and limits and the brief's refresh cadence. JevComputeSettings, set on JevRuntimeSettings.compute, turns on the mid-run compute checkpoint and holds its brief settings.
ROLE IN CODEBASE: JevAgent maps JevAgentSettings into BaseAgent and builds its preflight gate from both objects at construction, so JevRuntime never reads settings to decide what to ask.
ARCHITECTURE NOTE: The surface is intentionally closed; named Jev capabilities belong here as explicit settings instead of a generic decisions collection. JevAgentSettings holds the main agent and the JevSpecialist candidates Jev may hand a run to; JevRuntimeSettings holds the decision model, the preflight flags, the continuation settings (the done checks and their limits), and the tool-selector threshold.
COMMON MODIFICATION PATTERNS: Add a generative-agent field to JevAgentSettings or a Jev policy setting to JevRuntimeSettings, then implement its fixed policy in vidbyte/agents/jev/gate/ without exposing runtime replacement hooks.
KNOWN EDGE CASES: The generative provider cannot be TypeSafe because Jev is a decision model; neither generative nor decision API keys appear in repr output. Specialist titles must be unique because each one is a Choice option name. Preflight presets are validated by JevPreflightRegistry and done checks by JevDoneRegistry at construction, every continuation limit rejects booleans and non-integers, so no TypeSafe key is needed until a run asks Jev; the tool-selector threshold rejects booleans, non-finite values, and out-of-range probabilities.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-tool-selector.md, docs/design/jev-multipart-done-criteria.md, docs/design/jev-run-brief.md, docs/design/jev-compute-checkpoint.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, tests/test_jev_tool_selector.py, tests/test_jev_done.py, tests/test_jev_run_brief.py, tests/test_jev_compute.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.constants.jev import (
    JEV_COMPUTE_COOLDOWN_ITERATIONS,
    JEV_COMPUTE_HELPER_MAX_ITERATIONS,
    JEV_COMPUTE_HELPER_MAX_TOKENS,
    JEV_COMPUTE_MAX_HELPERS,
    JEV_COMPUTE_MAX_MOVES,
    JEV_COMPUTE_MAX_PARALLEL_HELPERS,
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
    JEV_RUN_BRIEF_MIN_GAP,
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
    JevComputeSituation,
    JevContinuationGate,
    JevDoneCheck,
    JevPreflightPreset,
    ModelProvider,
)
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev import JevDoneRegistry, JevPreflightRegistry
from vidbyte.lib.jev.compute import JevComputeRegistry
from vidbyte.tools.security import PermissionPolicy


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
    min_gap: int = JEV_RUN_BRIEF_MIN_GAP
    max_iterations: int = JEV_RUN_BRIEF_MAX_ITERATIONS
    max_tokens: int = JEV_RUN_BRIEF_MAX_TOKENS

    def __post_init__(self) -> None:
        self._validate_model()
        self._validate_temperature()
        for field_name in ("every_iterations", "min_gap", "max_iterations", "max_tokens"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ConfigurationError(f"JevRunBriefSettings.{field_name} must be an integer of at least 1.", details={"received": repr(value)})
        if self.min_gap > self.every_iterations:
            # @intent the-cadence-has-room-for-early-refreshes
            # min_gap is the floor between refreshes and every_iterations the ceiling; a floor above the ceiling
            # would silently turn every early trigger off, so the contradiction is refused instead.
            raise ConfigurationError("JevRunBriefSettings.min_gap cannot exceed every_iterations.", details={"min_gap": self.min_gap, "every_iterations": self.every_iterations})

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
    """Validated settings for mid-run dynamic compute: what JevAgent keeps and decides between the main agent's tool iterations.

    Setting `JevRuntimeSettings.compute` turns the compute checkpoint on. The checkpoint keeps the run brief current
    through its own writer agent, on the cadence and model `brief` sets, and after each verified refresh asks Jev
    which of the enabled `situations` the run is in. Situations are kept in priority order; an empty tuple keeps
    the brief and asks Jev nothing. When a situation is recognized, the checkpoint acts on it with helper agents,
    within a run-local budget: at most `max_moves` moves and `max_helpers` helpers per run, and `cooldown_iterations`
    main-loop iterations between moves. `max_moves=0` keeps recognition but never acts. Each helper is a separate,
    linear agent with the main agent's model, tools, and permissions and its own `helper_max_iterations` and
    `helper_max_tokens` limits; a fan-out runs at most `max_parallel_helpers` helpers at once.
    """

    brief: JevRunBriefSettings = field(default_factory=JevRunBriefSettings)
    situations: tuple[JevComputeSituation | str, ...] = (JevComputeSituation.REPEATING, JevComputeSituation.EACH_OF_SEVERAL, JevComputeSituation.SELF_CONTAINED_STEP)
    max_moves: int = JEV_COMPUTE_MAX_MOVES
    max_helpers: int = JEV_COMPUTE_MAX_HELPERS
    cooldown_iterations: int = JEV_COMPUTE_COOLDOWN_ITERATIONS
    helper_max_iterations: int = JEV_COMPUTE_HELPER_MAX_ITERATIONS
    helper_max_tokens: int = JEV_COMPUTE_HELPER_MAX_TOKENS
    max_parallel_helpers: int = JEV_COMPUTE_MAX_PARALLEL_HELPERS

    def __post_init__(self) -> None:
        if not isinstance(self.brief, JevRunBriefSettings):
            raise ConfigurationError("JevComputeSettings.brief must be a JevRunBriefSettings instance.")
        object.__setattr__(self, "situations", JevComputeRegistry.validate(self.situations))
        for field_name, minimum in (("max_moves", 0), ("max_helpers", 1), ("cooldown_iterations", 0), ("helper_max_iterations", 1), ("helper_max_tokens", 1), ("max_parallel_helpers", 1)):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ConfigurationError(f"JevComputeSettings.{field_name} must be an integer of at least {minimum}.", details={"received": repr(value)})


@dataclass(frozen=True, slots=True)
class JevRuntimeSettings:
    """Validated Jev decision policy: the TypeSafe model, the preflight flags, the continuation settings, the tool-selector threshold, and mid-run compute (off when None)."""

    decision: DecisionModelConfig = field(default_factory=DecisionModelConfig, repr=False)
    preflight: tuple[JevPreflightPreset | str, ...] = ()
    continual: JevContinualSettings = field(default_factory=JevContinualSettings)
    tool_selector_threshold: float = JEV_TOOL_SELECTOR_DEFAULT_THRESHOLD
    compute: JevComputeSettings | None = None

    def __post_init__(self) -> None:
        # Rejects invalid decision policy before JevAgent builds its preflight gate and run state.
        if not isinstance(self.decision, DecisionModelConfig):
            raise ConfigurationError("JevRuntimeSettings.decision must be a DecisionModelConfig instance.")
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


__all__ = ["JevAgentSettings", "JevComputeSettings", "JevContinualSettings", "JevRunBriefSettings", "JevRuntimeSettings"]
