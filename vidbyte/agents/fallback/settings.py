"""Context Protocol Header

Description:
    Defines AgentFallbackSettings, the canonical configuration object for an
    agent's ordered model fallback chain and its per-hop policies.
Purpose:
    Gives developers one validated place to declare prioritized backup models and
    per-hop trigger policies (deadlines, cost ceilings), accepting bare model
    names, provider-prefixed names, or explicit FallbackModel entries, and
    converting them into the internal AgentFallback contract.
Architecture:
    - AgentFallbackSettings: Thin developer-facing adapter; owns no validation itself.
    - AgentFallbackConfig (vidbyte.lib.dataclasses.agents): The strictly validated
      shape this class builds at construction and reads every attribute from.
    - resolved_models(): Normalizes every entry against the agent's primary model.
    - to_fallback(): Converts to the internal AgentFallback contract.
Relations:
    Imported by vidbyte.agents.base. Exported from vidbyte.agents.settings.
Similar Files:
    - vidbyte/agents/settings/loop.py: AgentLoopSettings follows the same plain-class pattern.
    - vidbyte/agents/fallback/chain.py: AgentFallback is the internal contract this converts to.
    - vidbyte/agents/fallback/policies.py: LatencyPolicy and CostBudgetPolicy, validated here.
    - vidbyte/lib/dataclasses/agents.py: AgentFallbackConfig owns the validation this class delegates to.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from vidbyte.lib.dataclasses.agents import AgentFallbackConfig, FallbackModel
from vidbyte.lib.enums import FallbackPolicyMode, ModelProvider
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.fallback.chain import AgentFallback


class AgentFallbackSettings:
    """Developer-facing configuration object for an agent's ordered model fallback chain.

    Accepts the loose, ergonomic constructor shape developers write (bare model
    names, a mode as a plain string, `fallback_on=None` meaning "use the chain
    default"), coerces it once into a strictly validated AgentFallbackConfig, and
    reads every attribute back from that config -- so a constructed instance is
    provably valid and this class carries no validation logic of its own.
    """

    def __init__(self, *, models: Sequence[str | FallbackModel], fallback_on: tuple[type[BaseException], ...] | None = None, policies: Sequence[object] = (), policies_mode: FallbackPolicyMode | str = FallbackPolicyMode.ANY, enabled: bool = True) -> None:
        # Coerces every loose argument into one concrete, strictly validated AgentFallbackConfig.
        self._config = AgentFallbackConfig(
            models=tuple(models),
            fallback_on=tuple(fallback_on) if fallback_on is not None else None,
            policies=tuple(policies),
            policies_mode=self._resolve_policies_mode(policies_mode),
            enabled=enabled,
        )

    @property
    def models(self) -> tuple[str | FallbackModel, ...]:
        """Return the declared chain entries, as passed at construction."""
        return self._config.models

    @property
    def fallback_on(self) -> tuple[type[BaseException], ...] | None:
        """Return the declared error filter, or None to use the chain's default."""
        return self._config.fallback_on

    @property
    def policies(self) -> tuple[object, ...]:
        """Return the declared per-hop and chain-wide policies."""
        return self._config.policies

    @property
    def policies_mode(self) -> FallbackPolicyMode:
        """Return the resolved checkpoint-policy vote mode."""
        return self._config.policies_mode

    @property
    def enabled(self) -> bool:
        """Return whether this settings object builds a live fallback chain."""
        return self._config.enabled

    @staticmethod
    def _resolve_policies_mode(policies_mode: FallbackPolicyMode | str) -> FallbackPolicyMode:
        # Coerces a mode string into the enum, raising ConfigurationError for any unknown value.
        try:
            return FallbackPolicyMode(policies_mode)
        except ValueError:
            raise ConfigurationError(
                f"AgentFallbackSettings.policies_mode must be a FallbackPolicyMode, got {policies_mode!r}.",
                details={"policies_mode": repr(policies_mode)},
            ) from None

    def resolved_models(self, *, primary: FallbackModel) -> tuple[FallbackModel, ...]:
        """Return the full chain with the primary first and every entry normalized against it."""
        return (primary, *(self._resolve_entry(entry, primary, position) for position, entry in enumerate(self.models)))

    def to_fallback(self, *, primary: FallbackModel) -> AgentFallback | None:
        """Convert these settings into the internal AgentFallback, or None when disabled."""
        from vidbyte.agents.fallback.chain import DEFAULT_FALLBACK_ERRORS, AgentFallback

        if not self.enabled:
            return None
        return AgentFallback(
            self.resolved_models(primary=primary),
            fallback_on=self.fallback_on if self.fallback_on is not None else DEFAULT_FALLBACK_ERRORS,
            policies=self.policies,
            policies_mode=self.policies_mode,
        )

    def _resolve_entry(self, entry: str | FallbackModel, primary: FallbackModel, position: int) -> FallbackModel:
        # Turns one declared entry into a fully specified FallbackModel, inheriting from the primary where unstated.
        if isinstance(entry, FallbackModel):
            return entry
        provider, model = self._split_provider_prefix(entry.strip(), position)
        return FallbackModel(
            provider=provider if provider is not None else self._inherited_provider(primary, entry, position),
            model=model,
            api_key=primary.api_key,
            temperature=primary.temperature,
        )

    @staticmethod
    def _split_provider_prefix(entry: str, position: int) -> tuple[str | None, str]:
        # Splits 'provider/model' when the prefix names a real provider, leaving vendor-style ids like 'meta/llama' intact.
        if "/" not in entry:
            return None, entry
        prefix, remainder = entry.split("/", 1)
        try:
            provider = ModelProvider(prefix.strip().lower()).value
        except ValueError:
            return None, entry
        if not remainder.strip():
            raise ConfigurationError(
                f"AgentFallbackSettings.models[{position}] names provider {provider!r} but no model: {entry!r}."
            )
        return provider, remainder.strip()

    @staticmethod
    def _inherited_provider(primary: FallbackModel, entry: str, position: int) -> str:
        # A bare model name only works when the agent itself declares a provider to inherit.
        if not primary.provider:
            raise ConfigurationError(
                f"AgentFallbackSettings.models[{position}] ({entry!r}) has no provider and the agent declares none; "
                "use 'provider/model' or a FallbackModel."
            )
        return primary.provider

    def __repr__(self) -> str:
        # Returns a compact developer-readable string showing declared entries without credentials.
        entries = ", ".join(entry.identity() if isinstance(entry, FallbackModel) else repr(entry) for entry in self.models)
        state = "" if self.enabled else ", enabled=False"
        mode = "" if self.policies_mode is FallbackPolicyMode.ANY else f", policies_mode=FallbackPolicyMode.{self.policies_mode.name}"
        return f"AgentFallbackSettings([{entries}]{state}{mode})"


__all__ = ["AgentFallbackSettings"]
