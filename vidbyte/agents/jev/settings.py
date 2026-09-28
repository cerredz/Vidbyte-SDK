"""FILE: vidbyte/agents/jev/settings.py

PURPOSE: Defines JevAgent's two opinionated public configuration objects: JevAgentSettings for the agents that generate, and JevRuntimeSettings for Jev's own decision policy.
ROLE IN CODEBASE: JevAgent maps JevAgentSettings into BaseAgent and builds its preflight gate from both objects at construction, so JevRuntime never reads settings to decide what to ask.
ARCHITECTURE NOTE: The surface is intentionally closed; named Jev capabilities belong here as explicit settings instead of a generic decisions collection. JevAgentSettings holds the main agent and the JevSpecialist candidates Jev may hand a run to; JevRuntimeSettings holds the decision model, the preflight flags, and the tool-selector threshold.
COMMON MODIFICATION PATTERNS: Add a generative-agent field to JevAgentSettings or a Jev policy setting to JevRuntimeSettings, then implement its fixed policy in vidbyte/agents/jev/gate/ without exposing runtime replacement hooks.
KNOWN EDGE CASES: The generative provider cannot be TypeSafe because Jev is a decision model; neither generative nor decision API keys appear in repr output. Specialist titles must be unique because each one is a Choice option name. Preflight presets are validated by JevPreflightRegistry at construction, so no TypeSafe key is needed until a run asks Jev; the tool-selector threshold rejects booleans, non-finite values, and out-of-range probabilities.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-tool-selector.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, tests/test_jev_tool_selector.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.constants.jev import (
    JEV_SPECIALIST_MAX_COUNT,
    JEV_TOOL_SELECTOR_DEFAULT_THRESHOLD,
    JEV_TOOL_SELECTOR_MAX_THRESHOLD,
    JEV_TOOL_SELECTOR_MIN_THRESHOLD,
)
from vidbyte.lib.dataclasses.jev import JevSpecialist
from vidbyte.lib.dataclasses.model_configs import DecisionModelConfig
from vidbyte.lib.enums import JevPreflightPreset, ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev import JevPreflightRegistry
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
class JevRuntimeSettings:
    """Validated Jev decision policy: the TypeSafe model, the preflight flags, and the tool-selector threshold."""

    decision: DecisionModelConfig = field(default_factory=DecisionModelConfig, repr=False)
    preflight: tuple[JevPreflightPreset | str, ...] = ()
    tool_selector_threshold: float = JEV_TOOL_SELECTOR_DEFAULT_THRESHOLD

    def __post_init__(self) -> None:
        # Rejects invalid decision policy before JevAgent builds its preflight gate.
        if not isinstance(self.decision, DecisionModelConfig):
            raise ConfigurationError("JevRuntimeSettings.decision must be a DecisionModelConfig instance.")
        object.__setattr__(self, "preflight", JevPreflightRegistry.validate(self.preflight))
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


__all__ = ["JevAgentSettings", "JevRuntimeSettings"]
