"""FILE: vidbyte/agents/jev/settings.py

PURPOSE: Defines the validated, immutable public settings accepted by JevAgent, including its optional typed completion criteria.
ROLE IN CODEBASE: JevAgent passes this object to JevRuntime; done_criteria values come from vidbyte/agents/jev/done_criteria and are evaluated only at model finish attempts.
ARCHITECTURE NOTE: Named Jev capabilities remain explicit settings rather than a generic decisions map; the settings object is the sole public constructor input.
FUNCTION INVENTORY: __post_init__ validates and normalizes settings; _validate_done_criteria snapshots completion policy; helper methods validate provider and model fields.
COMMON MODIFICATION PATTERNS: Add new Jev capabilities as validated typed settings, then implement their fixed policy in JevRuntime or a Jev-owned package.
WHAT NOT TO DO: Do not construct a provider runner or evaluate per-run criteria in settings; runtime construction and run-local policy belong to JevRuntime.
KNOWN EDGE CASES: The generative provider cannot be TypeSafe; secrets remain excluded from repr; strings and invalid objects are rejected as done criteria.
RELATED DOCS: docs/design/jev-agent-scaffold.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_done_criteria.py, and scripts/test-jev-done-criteria.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from vidbyte.agents.jev.done_criteria import JevDoneCriterion
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
    done_criteria: tuple[JevDoneCriterion, ...] = ()

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
        self._validate_done_criteria()

    def _validate_done_criteria(self) -> None:
        # Snapshots criteria so callers cannot mutate Jev completion policy after settings construction.
        if isinstance(self.done_criteria, (str, bytes)):
            raise ConfigurationError("JevAgentSettings.done_criteria must contain JevDoneCriterion instances, not a string.")
        try:
            criteria = tuple(self.done_criteria)
        except TypeError as exc:
            raise ConfigurationError("JevAgentSettings.done_criteria must be an iterable of JevDoneCriterion instances.") from exc
        if any(not isinstance(criterion, JevDoneCriterion) for criterion in criteria):
            raise ConfigurationError("JevAgentSettings.done_criteria must contain only JevDoneCriterion instances.")
        object.__setattr__(self, "done_criteria", criteria)

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
