"""Context Protocol Header

Description:
    Defines AgentFallbackSettings, the canonical configuration object for an
    agent's ordered model fallback chain.
Purpose:
    Gives developers one validated place to declare prioritized backup models,
    accepting bare model names, provider-prefixed names, or explicit FallbackModel
    entries, and converting them into the internal AgentFallback contract.
Architecture:
    - AgentFallbackSettings: Plain class with __init__-level validation.
    - resolved_models(): Normalizes every entry against the agent's primary model.
    - to_fallback(): Converts to the internal AgentFallback contract.
Relations:
    Imported by vidbyte.agents.base. Exported from vidbyte.agents.settings.
Similar Files:
    - vidbyte/agents/settings/loop.py: AgentLoopSettings follows the same plain-class pattern.
    - vidbyte/agents/fallback.py: AgentFallback is the internal contract this converts to.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from vidbyte.lib.dataclasses.agents import FallbackModel
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.fallback import AgentFallback


class AgentFallbackSettings:
    """Validated configuration object for an agent's ordered model fallback chain."""

    def __init__(self, *, models: Sequence[str | FallbackModel], fallback_on: tuple[type[BaseException], ...] | None = None, enabled: bool = True) -> None:
        # Stores the declared chain and error filter as instance attributes, then validates them immediately.
        self.models = tuple(models)
        self.fallback_on = fallback_on
        self.enabled = enabled
        self._validate()

    def _validate(self) -> None:
        # Raises ConfigurationError for any constraint violation found on this settings object.
        self._validate_models_not_empty()
        self._validate_entry_types()
        self._validate_error_types()

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

    def resolved_models(self, *, primary: FallbackModel) -> tuple[FallbackModel, ...]:
        """Return the full chain with the primary first and every entry normalized against it."""
        return (primary, *(self._resolve_entry(entry, primary, position) for position, entry in enumerate(self.models)))

    def to_fallback(self, *, primary: FallbackModel) -> AgentFallback | None:
        """Convert these settings into the internal AgentFallback, or None when disabled."""
        from vidbyte.agents.fallback import DEFAULT_FALLBACK_ERRORS, AgentFallback

        if not self.enabled:
            return None
        return AgentFallback(
            self.resolved_models(primary=primary),
            fallback_on=self.fallback_on if self.fallback_on is not None else DEFAULT_FALLBACK_ERRORS,
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
        return f"AgentFallbackSettings([{entries}]{state})"


__all__ = ["AgentFallbackSettings"]
