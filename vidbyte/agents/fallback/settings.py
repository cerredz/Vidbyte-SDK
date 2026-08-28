"""Context Protocol Header

FILE: vidbyte/agents/fallback/settings.py
PURPOSE: Converts developer-facing fallback declarations into the shared,
         validated AgentFallbackConfig consumed by the internal chain.
ROLE IN CODEBASE: BaseAgent and public settings imports use this module; it
                  resolves bare/provider-prefixed model names against the primary
                  model, then hands the normalized contract to chain.py.
ARCHITECTURE NOTE: This class retains early, friendly construction errors, while
                    AgentFallbackConfig owns rules shared with direct callers of
                    the internal chain.
FUNCTION INVENTORY:
    - __init__/_validate: validate the public declaration immediately.
    - resolved_models: prepend and normalize the primary model.
    - to_fallback: build AgentFallbackConfig and AgentFallback.
    - _resolve_entry/_split_provider_prefix: normalize one model entry.
COMMON MODIFICATION PATTERNS: Add a public input normalization rule here only
    when it is specific to settings syntax; add shared invariants to dataclasses.
WHAT NOT TO DO: Do not construct AgentFallback with loose keyword arguments or
    reimplement policy-kind/value validation outside AgentFallbackConfig.
KNOWN EDGE CASES: Declared fallback models exclude the primary, so policy arrays
    have len(models) entries here and len(resolved_models)-1 entries downstream.
COMMON ERRORS: FallbackConfigurationError for invalid names, providers, error
    filters, policy values, or disabled-chain declarations.
TEST FILES: Existing fallback settings/runtime tests and scripts/run_ci.py.
RELATED DOCS: docs/design/agent-fallback-policies.md
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from vidbyte.lib.dataclasses.agents import AgentFallbackConfig, FallbackModel
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import FallbackConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.fallback.chain import AgentFallback


class AgentFallbackSettings:
    """Validated configuration object for an agent's ordered model fallback chain."""

    def __init__(self, *, models: Sequence[str | FallbackModel], fallback_on: tuple[type[BaseException], ...] | None = None, policies: Sequence[object] = (), enabled: bool = True) -> None:
        # Stores the declared chain, error filter, and per-hop policies, then validates them immediately.
        self.models = tuple(models)
        self.fallback_on = fallback_on
        self.policies = tuple(policies)
        self.enabled = enabled
        self._validate()

    def _validate(self) -> None:
        # Raises FallbackConfigurationError for any constraint violation found on this settings object.
        self._validate_models_not_empty()
        self._validate_entry_types()
        self._validate_error_types()
        self._validate_policy_hop_values()

    def _validate_models_not_empty(self) -> None:
        # An empty chain is a mistake; pass fallback=None to disable the feature entirely.
        if not self.models:
            raise FallbackConfigurationError(
                "AgentFallbackSettings.models cannot be empty; pass fallback=None to run without a fallback chain."
            )

    def _validate_entry_types(self) -> None:
        # Each entry must be a non-blank model string or an explicit FallbackModel.
        for position, entry in enumerate(self.models):
            if isinstance(entry, FallbackModel):
                continue
            if not isinstance(entry, str) or not entry.strip():
                raise FallbackConfigurationError(
                    f"AgentFallbackSettings.models[{position}] must be a non-empty model name or a FallbackModel, "
                    f"got {type(entry).__name__}."
                )

    def _validate_error_types(self) -> None:
        # Every declared trigger must be an exception class the runtime can match with isinstance.
        for entry in self.fallback_on or ():
            if not (isinstance(entry, type) and issubclass(entry, BaseException)):
                raise FallbackConfigurationError(
                    f"AgentFallbackSettings.fallback_on entries must be exception classes, got {entry!r}."
                )

    def _validate_policy_hop_values(self) -> None:
        # Settings retains the early construction-time failure while the shared dataclass owns its rules.
        AgentFallbackConfig.validate_policies(self.policies, transition_count=len(self.models))

    def resolved_models(self, *, primary: FallbackModel) -> tuple[FallbackModel, ...]:
        """Return the full chain with the primary first and every entry normalized against it."""
        return (primary, *(self._resolve_entry(entry, primary, position) for position, entry in enumerate(self.models)))

    def to_fallback(self, *, primary: FallbackModel) -> AgentFallback | None:
        """Convert these settings into the internal AgentFallback, or None when disabled."""
        from vidbyte.agents.fallback.chain import DEFAULT_FALLBACK_ERRORS, AgentFallback

        if not self.enabled:
            return None
        config = AgentFallbackConfig(
            models=self.resolved_models(primary=primary),
            fallback_on=self.fallback_on if self.fallback_on is not None else DEFAULT_FALLBACK_ERRORS,
            policies=self.policies,
        )
        return AgentFallback(config)

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
            raise FallbackConfigurationError(
                f"AgentFallbackSettings.models[{position}] names provider {provider!r} but no model: {entry!r}."
            )
        return provider, remainder.strip()

    @staticmethod
    def _inherited_provider(primary: FallbackModel, entry: str, position: int) -> str:
        # A bare model name only works when the agent itself declares a provider to inherit.
        if not primary.provider:
            raise FallbackConfigurationError(
                f"AgentFallbackSettings.models[{position}] ({entry!r}) has no provider and the agent declares none; "
                "use 'provider/model' or a FallbackModel."
            )
        return primary.provider

    def __repr__(self) -> str:
        # Returns a compact developer-readable string showing declared entries without credentials.
        entries = ", ".join(entry.identity() if isinstance(entry, FallbackModel) else repr(entry) for entry in self.models)
        state = "" if self.enabled else ", enabled=False"
        return f"AgentFallbackSettings([{entries}]{state})"


__all__ = ["AgentFallbackSettings"]
