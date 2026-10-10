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
    JEV_COMPUTE_CLONES_DEFAULT,
    JEV_COMPUTE_CLONES_MAX,
    JEV_COMPUTE_SWARM_AGENTS_DEFAULT,
    JEV_COMPUTE_SWARM_AGENTS_MAX,
    JEV_COMPUTE_SWARM_AGENTS_MIN,
    JEV_DONE_MAX_CONTINUATIONS,
    JEV_FAITHFUL_SCOPE_EXTRA_ITERATIONS,
    JEV_FAITHFUL_SCOPE_EXTRA_TOKENS,
    JEV_FAITHFUL_SCOPE_EXTRA_TOOL_CALLS,
    JEV_HANDOFF_MAX_ITERATIONS,
    JEV_HANDOFF_MAX_TOKENS,
    JEV_NOUL_YES_THRESHOLD,
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
from vidbyte.lib.dataclasses.skills import SkillDocument
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
class JevAlignmentSettings:
    """Select request-time skill guidance for JevAgent."""

    skills: tuple[SkillDocument | str, ...] = ()

    def __post_init__(self) -> None:
        # Normalizes caller skills once so every run reads the same named documents.
        object.__setattr__(self, "skills", self._normalized_skills())

    def _normalized_skills(self) -> tuple[SkillDocument, ...]:
        # @intent names-uniquely-identify-response-results
        # JevAgent.response exposes each decision by the configured name. Duplicate names would make two
        # different candidate bodies indistinguishable to callers and future source adapters.
        """Normalize caller strings and require unique stable names for every skill."""
        if isinstance(self.skills, (str, bytes)):
            raise ConfigurationError("JevAlignmentSettings.skills must be an iterable of SkillDocument or strings, not a string.")
        try:
            candidates = tuple(self.skills)
        except TypeError as exc:
            raise ConfigurationError("JevAlignmentSettings.skills must be an iterable of SkillDocument or strings.") from exc
        skills: list[SkillDocument] = []
        for index, candidate in enumerate(candidates, start=1):
            if isinstance(candidate, str):
                candidate = SkillDocument(
                    name=f"inline_skill_{index}",
                    description="Caller-supplied inline skill text.",
                    text=candidate,
                    source="inline",
                )
            if not isinstance(candidate, SkillDocument):
                raise ConfigurationError("JevAlignmentSettings.skills must contain only SkillDocument or string values.")
            skills.append(candidate)
        seen: set[str] = set()
        duplicates: set[str] = set()
        for skill in skills:
            if skill.name in seen:
                duplicates.add(skill.name)
            seen.add(skill.name)
        if duplicates:
            raise ConfigurationError("JevAlignmentSettings.skills must have unique document names.", details={"names": sorted(duplicates)})
        return tuple(skills)


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
    alignment: JevAlignmentSettings = field(default_factory=JevAlignmentSettings)

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
        if not isinstance(self.alignment, JevAlignmentSettings):
            raise ConfigurationError("JevAgentSettings.alignment must be a JevAlignmentSettings instance.")
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
    """Validated run-brief settings, enabled dynamic-compute options, and the clone and swarm sizes for the mid-run checkpoint.

    CLONE and SWARM are opt-in because they launch agents. Add CLONE to `dynamic_compute`, and `clones` sets how
    many copies of the main agent its one launch per run starts. Add SWARM, and `swarm_agents` caps how many
    helpers the main agent may assign in the plan it submits through the one-time `launch_swarm` tool.
    """

    brief: JevRunBriefSettings = field(default_factory=JevRunBriefSettings)
    dynamic_compute: tuple[JevDynamicComputeOption | str, ...] = (
        JevDynamicComputeOption.FRESH_AGENT,
        JevDynamicComputeOption.FORK_AGENT,
        JevDynamicComputeOption.SUBAGENT,
    )
    clones: int = JEV_COMPUTE_CLONES_DEFAULT
    swarm_agents: int = JEV_COMPUTE_SWARM_AGENTS_DEFAULT

    def __post_init__(self) -> None:
        if not isinstance(self.brief, JevRunBriefSettings):
            raise ConfigurationError("JevComputeSettings.brief must be a JevRunBriefSettings instance.")
        object.__setattr__(self, "dynamic_compute", JevComputeRegistry.validate(self.dynamic_compute))
        if isinstance(self.clones, bool) or not isinstance(self.clones, int) or not 1 <= self.clones <= JEV_COMPUTE_CLONES_MAX:
            raise ConfigurationError(f"JevComputeSettings.clones must be an integer from 1 through {JEV_COMPUTE_CLONES_MAX}.")
        if isinstance(self.swarm_agents, bool) or not isinstance(self.swarm_agents, int) or not JEV_COMPUTE_SWARM_AGENTS_MIN <= self.swarm_agents <= JEV_COMPUTE_SWARM_AGENTS_MAX:
            raise ConfigurationError(f"JevComputeSettings.swarm_agents must be an integer from {JEV_COMPUTE_SWARM_AGENTS_MIN} through {JEV_COMPUTE_SWARM_AGENTS_MAX}.")


@dataclass(frozen=True, slots=True)
class JevRuntimeSettings:
    """Validated Jev decision policy: Vidbyte-managed decisions, preflight flags, continuation settings, and the tool-selector threshold."""

    decision: DecisionModelConfig = field(default_factory=DecisionModelConfig.vidbyte_managed, repr=False)
    preflight: tuple[JevPreflightPreset | str, ...] = ()
    continual: JevContinualSettings = field(default_factory=JevContinualSettings)
    tool_selector_threshold: float = JEV_TOOL_SELECTOR_DEFAULT_THRESHOLD
    compute: JevComputeSettings | None = None
    skills_threshold: float = JEV_NOUL_YES_THRESHOLD

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
        self._validate_skills_threshold()

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

    def _validate_skills_threshold(self) -> None:
        # @intent boundary-probabilities-are-inclusive
        # Thresholds represent the minimum calibrated P(yes), so 0 and 1 are meaningful policies; booleans
        # are rejected even though Python treats them as integers.
        """Require a finite yes-probability cutoff for each skill selection."""
        value = self.skills_threshold
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ConfigurationError("JevRuntimeSettings.skills_threshold must be a finite probability between 0 and 1 inclusive.")
        object.__setattr__(self, "skills_threshold", float(value))

__all__ = ["JevAgentSettings", "JevAlignmentSettings", "JevComputeSettings", "JevContinualSettings", "JevRunBriefSettings", "JevRuntimeSettings"]
