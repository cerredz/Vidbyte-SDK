"""FILE: vidbyte/agents/jev/settings.py

PURPOSE: Defines the single, opinionated public configuration object for JevAgent and the settings of its named capabilities.
ROLE IN CODEBASE: JevAgentSettings is the only constructor input accepted by JevAgent and carries the future decision-model seam into JevRuntime.
ARCHITECTURE NOTE: The surface is intentionally closed; named Jev capabilities belong here as explicit settings instead of a generic decisions collection.
COMMON MODIFICATION PATTERNS: Add a validated named capability object, then implement its fixed policy in JevRuntime without exposing runtime replacement hooks.
KNOWN EDGE CASES: The generative provider cannot be TypeSafe because Jev is a decision model; neither generative nor decision API keys appear in repr output. A dynamic_compaction value with every trigger off counts as disabled.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-dynamic-compaction.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_dynamic_compaction.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.constants.jev_compaction import (
    JEV_COMPACTION_DEFAULT_MIN_RECLAIM_TOKENS,
    JEV_COMPACTION_MIN_RECLAIM_TOKENS_FLOOR,
)
from vidbyte.lib.dataclasses.model_configs import DecisionModelConfig
from vidbyte.lib.enums import JevCompactionTriggerKey, ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.security import PermissionPolicy


@dataclass(frozen=True, slots=True)
class JevDynamicCompactionSettings:
    """Which ways of finding finished work JevAgent may compact, and the smallest saving worth a history rewrite."""

    unit_of_work: bool = False
    min_reclaim_tokens: int = JEV_COMPACTION_DEFAULT_MIN_RECLAIM_TOKENS

    def __post_init__(self) -> None:
        # Rejects non-boolean trigger flags and a non-positive reclaim bound before any run starts.
        # @intent one-flag-per-trigger
        # Each way of finding a boundary is one boolean so users enable ways, never tune questions; all enabled
        # triggers share one ledger, one Jev request per step, and one compaction policy.
        for key in JevCompactionTriggerKey:
            if type(getattr(self, key.value)) is not bool:
                raise ConfigurationError(f"JevDynamicCompactionSettings.{key.value} must be True or False.")
        value = self.min_reclaim_tokens
        if isinstance(value, bool) or not isinstance(value, int) or value < JEV_COMPACTION_MIN_RECLAIM_TOKENS_FLOOR:
            raise ConfigurationError(f"JevDynamicCompactionSettings.min_reclaim_tokens must be an integer of at least {JEV_COMPACTION_MIN_RECLAIM_TOKENS_FLOOR}.")

    def enabled_triggers(self) -> tuple[JevCompactionTriggerKey, ...]:
        """Return the enabled triggers in declaration order."""
        return tuple(key for key in JevCompactionTriggerKey if getattr(self, key.value))

    def is_enabled(self) -> bool:
        """Return whether at least one trigger is on."""
        return bool(self.enabled_triggers())


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
    dynamic_compaction: JevDynamicCompactionSettings | None = None

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
        if self.dynamic_compaction is not None and not isinstance(self.dynamic_compaction, JevDynamicCompactionSettings):
            raise ConfigurationError("JevAgentSettings.dynamic_compaction must be a JevDynamicCompactionSettings instance or None.")

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


__all__ = ["JevAgentSettings", "JevDynamicCompactionSettings"]
