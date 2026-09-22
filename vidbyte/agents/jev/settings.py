"""FILE: vidbyte/agents/jev/settings.py

PURPOSE: Defines the single, opinionated public configuration object for JevAgent.
ROLE IN CODEBASE: JevAgentSettings is the only constructor input accepted by JevAgent and carries the future decision-model seam into JevRuntime.
ARCHITECTURE NOTE: The surface is intentionally closed; named Jev capabilities belong here as explicit settings instead of a generic decisions collection.
COMMON MODIFICATION PATTERNS: Add a validated named capability object, then implement its fixed policy in JevRuntime without exposing runtime replacement hooks.
KNOWN EDGE CASES: The generative provider cannot be TypeSafe because Jev is a decision model; neither generative nor decision API keys appear in repr output.
RELATED DOCS: docs/design/jev-agent-scaffold.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from vidbyte.agents.jev.presets import JevPreflightPreset, JevPreflightRegistry
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.dataclasses.model_configs import DecisionModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.security import PermissionPolicy


@dataclass(frozen=True, slots=True)
class JevAgentSettings:
    """Validated construction settings for the opinionated Jev agent."""

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
    decision: DecisionModelConfig = field(default_factory=DecisionModelConfig, repr=False)
    preflight: tuple[JevPreflightPreset | str, ...] = ()

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
        if not isinstance(self.decision, DecisionModelConfig):
            raise ConfigurationError("JevAgentSettings.decision must be a DecisionModelConfig instance.")
        self._normalize_preflight()

    def _normalize_preflight(self) -> None:
        # Converts strings to registered preset enums and rejects repeated work before any model call.
        if isinstance(self.preflight, (str, bytes)):
            raise ConfigurationError("JevAgentSettings.preflight must be an iterable of Jev preflight presets, not a string.")
        try:
            normalized = tuple(
                item if isinstance(item, JevPreflightPreset) else JevPreflightPreset(item)
                for item in self.preflight
            )
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("JevAgentSettings.preflight contains an unsupported preset.") from exc
        if len(set(normalized)) != len(normalized):
            raise ConfigurationError("JevAgentSettings.preflight cannot contain duplicate presets.")
        for preset in normalized:
            JevPreflightRegistry.resolve(preset)
        object.__setattr__(self, "preflight", normalized)

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


__all__ = ["JevAgentSettings"]
