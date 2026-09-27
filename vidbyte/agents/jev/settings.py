"""FILE: vidbyte/agents/jev/settings.py

PURPOSE: Validates the single linear JevAgent configuration separately from TypeSafe preflight and tool-selection policy.
ROLE IN CODEBASE: JevAgent passes its generative settings to BaseAgent and gives JevRuntimeSettings to JevPreflightGate and JevRuntime; agent-selection metadata is validated by specialists.py.
ARCHITECTURE NOTE: JevAgentSettings configures the model that performs generation. Candidate specialists contain only names, descriptions, and metadata and never own executable agents.
FUNCTION INVENTORY: JevAgentSettings.__post_init__ normalizes and validates the main agent's inputs; JevRuntimeSettings.__post_init__ validates TypeSafe, preset, and tool-selector settings.
COMMON MODIFICATION PATTERNS: Add generative-agent fields to JevAgentSettings and global Jev policy to JevRuntimeSettings; add profile metadata to JevSpecialist.
WHAT NOT TO DO IN THIS FILE: 1. Do not define question enums; vidbyte/lib/enums/jev.py owns those. 2. Do not construct provider requests; vidbyte/providers/typesafe.py owns wire serialization.
KNOWN EDGE CASES: TypeSafe credentials are resolved only when a decision runs; numeric thresholds reject booleans and non-finite values.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/blob/main/skills/jev-agent/SKILL.md
TESTS: tests/test_jev_agent.py and tests/test_jev_preflight.py.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.constants.jev import (
    JEV_AGENT_MAX_COUNT,
    JEV_AGENT_MAX_DESCRIPTION_CHARS,
    JEV_AGENT_MAX_ROUTING_CHARS,
    JEV_MAX_OPTION_NAME_CHARS,
    JEV_TOOL_SELECTOR_DEFAULT_THRESHOLD,
    JEV_TOOL_SELECTOR_MAX_THRESHOLD,
    JEV_TOOL_SELECTOR_MIN_THRESHOLD,
)
from vidbyte.lib.dataclasses.jev import JevJson
from vidbyte.lib.dataclasses.model_configs import DecisionModelConfig
from vidbyte.lib.enums.jev import JevPreflightPreset
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev import JevPreflightRegistry
from vidbyte.tools.security import PermissionPolicy

if TYPE_CHECKING:
    from vidbyte.agents.jev.specialists import JevSpecialist


@dataclass(frozen=True, slots=True)
class JevAgentSettings:
    """Validated generation settings and decision-only candidate profile descriptions."""

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
    agents: Sequence[JevSpecialist] = ()

    def __post_init__(self) -> None:
        # @intent reject-invalid-agent-settings-at-construction
        # JevAgentSettings crosses the public SDK boundary and supplies model identity, tools, and permissions
        # to BaseAgent. Normalize and validate the complete shape before any provider runner or runtime exists,
        # so a malformed value cannot fail later as an unrelated model or tool error.
        # Normalize public provider strings and freeze candidate metadata before the agent is constructed.
        self._validate_text(self.name, "name")
        self._validate_text(self.system_prompt, "system_prompt")
        self._validate_text(self.model_name, "model_name")
        object.__setattr__(self, "provider", self._normalized_provider())
        if self.provider is ModelProvider.TYPESAFE:
            raise ConfigurationError("JevAgentSettings.provider must be a generative model provider, not TypeSafe.")
        object.__setattr__(self, "tools", self._normalize_tools())
        self._validate_temperature()
        self._validate_timeout()
        if not isinstance(self.permission_policy, PermissionPolicy):
            raise ConfigurationError("JevAgentSettings.permission_policy must be a PermissionPolicy instance.")
        if not isinstance(self.loop, AgentLoopSettings):
            raise ConfigurationError("JevAgentSettings.loop must be an AgentLoopSettings instance.")
        object.__setattr__(self, "agents", self._normalize_agents())

    def _normalize_tools(self) -> tuple[object, ...]:
        if isinstance(self.tools, (str, bytes)):
            raise ConfigurationError("JevAgentSettings.tools must be an iterable of tool objects, not a string.")
        try:
            return tuple(self.tools)
        except TypeError as exc:
            raise ConfigurationError("JevAgentSettings.tools must be an iterable of tool objects.") from exc

    def _normalize_agents(self) -> tuple[JevSpecialist, ...]:
        from vidbyte.agents.jev.specialists import JevSpecialist

        if isinstance(self.agents, (str, bytes)) or not isinstance(self.agents, Sequence):
            raise ConfigurationError("JevAgentSettings.agents must be a sequence of JevSpecialist values.")
        agents = tuple(self.agents)
        if len(agents) > JEV_AGENT_MAX_COUNT or any(not isinstance(agent, JevSpecialist) for agent in agents):
            raise ConfigurationError(f"JevAgentSettings.agents must contain at most {JEV_AGENT_MAX_COUNT} JevSpecialist values.")
        titles = tuple(agent.title for agent in agents)
        if any(len(agent.title) > JEV_MAX_OPTION_NAME_CHARS for agent in agents):
            raise ConfigurationError(f"JevSpecialist.title must be at most {JEV_MAX_OPTION_NAME_CHARS} characters.")
        if len(set(titles)) != len(titles):
            raise ConfigurationError("JevAgentSettings.agents must have unique titles.")
        if any(len(agent.description) > JEV_AGENT_MAX_DESCRIPTION_CHARS for agent in agents):
            raise ConfigurationError(f"JevSpecialist.description must be at most {JEV_AGENT_MAX_DESCRIPTION_CHARS} characters.")
        profile_chars = sum(len(agent.title) + len(agent.description) + JevJson.char_length(agent.metadata) for agent in agents)
        if profile_chars > JEV_AGENT_MAX_ROUTING_CHARS:
            raise ConfigurationError(f"JevAgentSettings.agents metadata must fit within {JEV_AGENT_MAX_ROUTING_CHARS} characters.")
        return agents

    def _normalized_provider(self) -> ModelProvider:
        # @intent keep-decision-and-generation-providers-distinct
        # TypeSafe is reserved for Jev decisions, not generative execution. Canonicalizing this input once lets
        # construction reject that mix-up before a text runner is selected.
        try:
            return self.provider if isinstance(self.provider, ModelProvider) else ModelProvider(self.provider)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"Unsupported model provider: {self.provider!r}") from exc

    @staticmethod
    def _validate_text(value: object, field_name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"JevAgentSettings.{field_name} must be a non-blank string.")

    def _validate_temperature(self) -> None:
        value = self.temperature
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 2.0):
            raise ConfigurationError("JevAgentSettings.temperature must be a finite number between 0 and 2.")

    def _validate_timeout(self) -> None:
        value = self.timeout_seconds
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0.0):
            raise ConfigurationError("JevAgentSettings.timeout_seconds must be a finite number greater than zero.")


@dataclass(frozen=True, slots=True)
class JevRuntimeSettings:
    """Validated TypeSafe decisions and runtime-wide Jev preflight controls."""

    decision: DecisionModelConfig = field(default_factory=DecisionModelConfig, repr=False)
    preflight: Sequence[JevPreflightPreset | str] = ()
    tool_selector_threshold: float = JEV_TOOL_SELECTOR_DEFAULT_THRESHOLD

    def __post_init__(self) -> None:
        if not isinstance(self.decision, DecisionModelConfig):
            raise ConfigurationError("JevRuntimeSettings.decision must be a DecisionModelConfig instance.")
        object.__setattr__(self, "preflight", JevPreflightRegistry.validate(self.preflight))
        value = self.tool_selector_threshold
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not JEV_TOOL_SELECTOR_MIN_THRESHOLD <= value <= JEV_TOOL_SELECTOR_MAX_THRESHOLD:
            raise ConfigurationError("JevRuntimeSettings.tool_selector_threshold must be a finite probability between 0 and 1 inclusive.")
        object.__setattr__(self, "tool_selector_threshold", float(value))


__all__ = ["JevAgentSettings", "JevRuntimeSettings"]
