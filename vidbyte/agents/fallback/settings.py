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
    - AgentFallbackSettings: Plain class with __init__-level validation.
    - resolved_models(): Normalizes every entry against the agent's primary model.
    - to_fallback(): Converts to the internal AgentFallback contract.
Relations:
    Imported by vidbyte.agents.base. Exported from vidbyte.agents.settings.
Similar Files:
    - vidbyte/agents/settings/loop.py: AgentLoopSettings follows the same plain-class pattern.
    - vidbyte/agents/fallback/chain.py: AgentFallback is the internal contract this converts to.
    - vidbyte/agents/fallback/policies.py: LatencyPolicy and CostBudgetPolicy, validated here.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from vidbyte.lib.dataclasses.agents import FallbackModel
from vidbyte.lib.enums import FallbackPolicyMode, ModelProvider
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.fallback.chain import AgentFallback


class AgentFallbackSettings:
    """Validated configuration object for an agent's ordered model fallback chain."""

    def __init__(self, *, models: Sequence[str | FallbackModel], fallback_on: tuple[type[BaseException], ...] | None = None, policies: Sequence[object] = (), policies_mode: FallbackPolicyMode | str = FallbackPolicyMode.ANY, enabled: bool = True) -> None:
        # Stores the declared chain, error filter, per-hop policies, and vote mode, then validates them immediately.
        self.models = tuple(models)
        self.fallback_on = fallback_on
        self.policies = tuple(policies)
        self.policies_mode = self._resolve_policies_mode(policies_mode)
        self.enabled = enabled
        self._validate()

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

    def _validate(self) -> None:
        # Raises ConfigurationError for any constraint violation found on this settings object.
        self._validate_models_not_empty()
        self._validate_entry_types()
        self._validate_error_types()
        self._validate_policy_hop_values()

    def _validate_models_not_empty(self) -> None:
        # An empty chain is a mistake; pass fallback=None to disable the feature entirely.
        if not self.models:
            raise ConfigurationError(
                "AgentFallbackSettings.models cannot be empty; pass fallback=None to run without a fallback chain."
            )

    def _validate_entry_types(self) -> None:
        # Each entry must be a non-blank model string or an explicit FallbackModel.
        for position, entry in enumerate(self.models):
            if isinstance(entry, FallbackModel):
                continue
            if not isinstance(entry, str) or not entry.strip():
                raise ConfigurationError(
                    f"AgentFallbackSettings.models[{position}] must be a non-empty model name or a FallbackModel, "
                    f"got {type(entry).__name__}."
                )

    def _validate_error_types(self) -> None:
        # Every declared trigger must be an exception class the runtime can match with isinstance.
        for entry in self.fallback_on or ():
            if not (isinstance(entry, type) and issubclass(entry, BaseException)):
                raise ConfigurationError(
                    f"AgentFallbackSettings.fallback_on entries must be exception classes, got {entry!r}."
                )

    def _validate_policy_hop_values(self) -> None:
        # Every per-hop policy must supply exactly one value per transition, and every value must be usable.
        expected = len(self.models)
        for policy in self.policies:
            hop_values = getattr(policy, "hop_values", None)
            if not callable(hop_values):
                continue
            values = tuple(hop_values())
            self._validate_policy_hop_count(policy, values, expected)
            self._validate_policy_hop_elements(policy, values)

    @staticmethod
    def _validate_policy_hop_count(policy: object, values: tuple[object, ...], expected: int) -> None:
        # A per-hop policy needs one value per transition: the chain has `expected` fallback
        # models, which prepended with the primary gives `expected` possible transitions.
        if len(values) == expected:
            return
        raise ConfigurationError(
            f"{type(policy).__name__} declares {len(values)} hop value(s), but this chain has "
            f"{expected} fallback model(s) ({expected + 1} total including the primary), which "
            f"means {expected} possible transitions. Every per-hop policy needs exactly one value "
            "per transition: one for the primary and one for each fallback except the last — the "
            "final model in the chain has nowhere left to fall back to, so it never gets one.",
            details={"policy": type(policy).__name__, "expected_hop_count": expected, "actual_hop_count": len(values)},
        )

    @staticmethod
    def _validate_policy_hop_elements(policy: object, values: tuple[object, ...]) -> None:
        # Every hop value must be a positive, non-bool number; a gap or a zero/negative ceiling can never fire correctly.
        for position, value in enumerate(values):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ConfigurationError(
                    f"{type(policy).__name__} hop value at position {position} must be a positive number, got {value!r}.",
                    details={"policy": type(policy).__name__, "position": position, "value": repr(value)},
                )

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
