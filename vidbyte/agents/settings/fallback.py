"""Context Protocol Header

Description:
    Defines AgentFallbackSettings, the canonical configuration object for an
    agent's ordered model fallback chain.
Purpose:
    Gives developers one validated place to declare prioritized backup models,
    accepting bare model names, provider-prefixed names, or explicit FallbackModel
    entries, and converting them into the internal AgentFallback contract.
Architecture:
    - AgentFallbackSettings: Plain class with __init__-level validation,
      including a strict boolean enabled switch so false-like strings cannot enable fallback.
    - resolved_models(): Normalizes every entry against the agent's primary model.
    - named_providers(): The providers the entries name, which the agent matches its keys against.
    - to_fallback(): Converts to the internal AgentFallback contract, with the agent's matched keys and mode.
Relations:
    Imported by vidbyte.agents.base. Exported from vidbyte.agents.settings.
Similar Files:
    - vidbyte/agents/settings/loop.py: AgentLoopSettings follows the same plain-class pattern.
    - vidbyte/agents/fallback.py: AgentFallback is the internal contract this converts to.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from vidbyte.lib.dataclasses.agents import FallbackModel, ProviderKeys
from vidbyte.lib.enums import ModelProvider, TextModelMode
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.fallback import AgentFallback


def _require_boolean_enabled(value: bool) -> bool:
    # @intent fallback-enabled-is-not-truthiness
    # A string such as "false" would otherwise enable a fallback chain at run time.
    if not isinstance(value, bool):
        raise ConfigurationError("AgentFallbackSettings.enabled must be a boolean.")
    return value


def _require_model_sequence(models: Sequence[str | FallbackModel]) -> Sequence[str | FallbackModel]:
    # @intent name-lists-reject-bare-strings
    # A typo like ("deepseek-reasoner") is a str, so tuple() would make a chain of one-character models.
    if isinstance(models, (str, bytes)):
        raise ConfigurationError("AgentFallbackSettings.models must be a sequence of models, not a string.")
    return models


class AgentFallbackSettings:
    """Validated configuration object for an agent's ordered model fallback chain."""

    def __init__(self, *, models: Sequence[str | FallbackModel], fallback_on: tuple[type[BaseException], ...] | None = None, enabled: bool = True) -> None:
        # Stores the declared chain and error filter as instance attributes, then validates them immediately.
        self.models = tuple(_require_model_sequence(models))
        self.fallback_on = fallback_on
        self.enabled = _require_boolean_enabled(enabled)
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

    def named_providers(self) -> tuple[str, ...]:
        """Return the providers this chain's entries name, in order and without repeats; bare names and a disabled chain name none."""
        # @intent backup-providers-are-matched-with-the-agent
        # The agent matches its key list against these names, so a key
        # for a backup's provider binds to that provider. A bare name
        # runs on the agent's own provider, already matched, and a
        # disabled chain makes no call, so neither adds a name.
        if not self.enabled:
            return ()
        names: list[str] = []
        for position, entry in enumerate(self.models):
            provider = entry.provider if isinstance(entry, FallbackModel) else self._split_provider_prefix(entry.strip(), position)[0]
            if provider is not None and provider not in names:
                names.append(provider)
        return tuple(names)

    def to_fallback(
        self,
        *,
        primary: FallbackModel,
        timeout_seconds: float | None = None,
        api_keys: ProviderKeys = ProviderKeys(),
        model_mode: TextModelMode = TextModelMode.AUTO,
    ) -> AgentFallback | None:
        """Convert these settings into the internal AgentFallback, or None when disabled."""
        from vidbyte.agents.fallback import DEFAULT_FALLBACK_ERRORS, AgentFallback

        if not self.enabled:
            return None
        # @intent children-carry-the-matched-keys
        # The chain gets the agent's matched record and mode as they
        # are, so each backup sends only the key matched to its own
        # provider; the entries themselves hold no key.
        return AgentFallback(
            self.resolved_models(primary=primary),
            fallback_on=self.fallback_on if self.fallback_on is not None else DEFAULT_FALLBACK_ERRORS,
            timeout_seconds=timeout_seconds,
            api_keys=api_keys,
            model_mode=model_mode,
        )

    def _resolve_entry(self, entry: str | FallbackModel, primary: FallbackModel, position: int) -> FallbackModel:
        # Turns one declared entry into a fully specified FallbackModel, inheriting from the primary where unstated.
        if isinstance(entry, FallbackModel):
            return entry
        provider, model = self._split_provider_prefix(entry.strip(), position)
        # A bare name stays on the agent's provider; a prefixed name switches to the provider it names.
        resolved_provider = provider if provider is not None else self._inherited_provider(primary, entry, position)
        return FallbackModel(provider=resolved_provider, model=model, temperature=primary.temperature)

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
        # @intent openrouter-keeps-its-own-model-ids
        # OpenRouter's own ids such as 'openrouter/auto' include the prefix on the wire, so, as in
        # Runner, only strip it when what follows is itself a vendor/model slug.
        if provider == ModelProvider.OPENROUTER.value and "/" not in remainder:
            return provider, f"{provider}/{remainder.strip()}"
        return provider, remainder.strip()

    @staticmethod
    def _inherited_provider(primary: FallbackModel, entry: str, position: int) -> str:
        # @intent bare-backup-name-needs-the-agent-provider
        # A bare model name runs on the agent's own provider and so on
        # the key matched to it. With no provider to inherit there is
        # no route and no key to choose, so the entry is refused here.
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
