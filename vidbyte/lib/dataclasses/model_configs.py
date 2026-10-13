"""Context Protocol Header

Description:
    Model execution configuration dataclasses for text, image, and video models.
Purpose:
    Stores model configurations and delegates API key and endpoint validation and resolution to ProviderModelRegistry.
Architecture:
    - TextModelConfig: dataclass for text/chat completions; matches its api_keys list to its provider at construction.
    - TextCredentials: the keys one text call sends, resolved for its mode.
    - ImageModelConfig: dataclass for image generation.
    - VideoModelConfig: dataclass for video generation tasks.
    - DecisionModelConfig: dataclass for calibrated decision models (TypeSafe Jev).
Key Functions:
    - credentials: Resolves a TextModelConfig's provider key and Vidbyte key for its mode (DIRECT, VIDBYTE_MANAGED, or AUTO).
    - resolved_api_key: Resolves the provider key; a text config in a gateway mode returns the non-secret placeholder instead.
    - resolved_endpoint: Resolves provider endpoint by delegating to ProviderModelRegistry.
Relations:
    Used by runners, agents, and strategies to initialize model executions.
Similar Files:
    - vidbyte/lib/models/registry.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.constants.jev import (
    JEV_DEFAULT_MODEL,
    JEV_DEFAULT_RETRY_COUNT,
    JEV_DEFAULT_TIMEOUT_SECONDS,
    JEV_MANAGED_GATEWAY_SUFFIX,
    JEV_MANAGED_RUN_CLOSE_PATH,
    JEV_NO_RETRIES,
    JEV_TIMEOUT_FLOOR_SECONDS,
    VIDBYTE_API_KEY_ENV_VAR,
    VIDBYTE_JEV_GATEWAY_ENDPOINT,
    VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND,
    VIDBYTE_MANAGED_KEY_PLACEHOLDER,
    VIDBYTE_MANAGED_TEXT_PROVIDERS,
    VIDBYTE_PROVIDER_KEY_MAX_LENGTH,
)
from vidbyte.lib.dataclasses.agents import ProviderKeys
from vidbyte.lib.enums import DecisionModelMode, ModelProvider, TextModelMode
from vidbyte.lib.errors import ConfigurationError, UnsupportedProviderError
from vidbyte.lib.registries.models import ProviderModelRegistry
from vidbyte.lib.registries.provider_keys import ProviderKeyMatcher

# The way out a text call names when no Vidbyte key is found.
TEXT_REMEDY: str = f"Pass vidbyte_api_key or set {VIDBYTE_API_KEY_ENV_VAR}, or use mode=TextModelMode.DIRECT to call the provider with your own key and no Vidbyte fee."


@dataclass(frozen=True, slots=True)
class TextModelConfig:
    provider: ModelProvider | str
    model: str
    api_keys: ProviderKeys = field(default_factory=ProviderKeys, repr=False)
    system: str | None = None
    messages: tuple[Mapping[str, Any], ...] = ()
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    stop_sequences: tuple[str, ...] = ()
    response_format: Mapping[str, Any] | None = None
    tools: tuple[Mapping[str, Any], ...] = ()
    tool_choice: str | Mapping[str, Any] | None = None
    tool_config: Mapping[str, Any] | None = None
    safety_settings: tuple[Mapping[str, Any], ...] = ()
    cached_content: str | None = None
    thinking_config: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] | None = None
    extra_body: Mapping[str, Any] | None = None
    endpoint: str | None = None
    timeout_seconds: float = 60.0
    mode: TextModelMode = TextModelMode.AUTO
    # Where the runtime's own exchange begins in messages; the provider puts the prompt there.
    prompt_index: int | None = None
    vidbyte_api_key: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Reject a bad prompt_index or mode, match the key list, and refuse what the gateway can never serve, as soon as the config is built."""
        # @intent prompt-sits-at-the-run-boundary
        if self.prompt_index is not None and (isinstance(self.prompt_index, bool) or not isinstance(self.prompt_index, int) or self.prompt_index < 0):
            raise ConfigurationError(f"prompt_index must be a non-negative int or None, got {self.prompt_index!r}.")
        # @intent text-mode-shape-fails-at-construction
        # Nothing here reads the environment: TextModelRunner rebuilds
        # the config on every call, so validate() settles the keys once.
        if not isinstance(self.mode, TextModelMode):
            raise ConfigurationError("mode must be a TextModelMode value.")
        # Match the developer's key list to this config's provider. A
        # record passed back in is only checked, so a rebuilt config
        # keeps the same keys.
        matched = ProviderKeyMatcher.match(self.api_keys, primary=self.provider, vidbyte_api_key=self.vidbyte_api_key, field_name="TextModelConfig.api_keys")
        object.__setattr__(self, "api_keys", matched)
        object.__setattr__(self, "vidbyte_api_key", matched.vidbyte_api_key)
        # Every mode but DIRECT goes through the gateway, so a provider
        # it does not serve, or a custom endpoint, is refused now.
        if self.mode is not TextModelMode.DIRECT:
            self._require_gateway_shape(self.normalized_provider())

    def normalized_provider(self) -> ModelProvider:
        # Convert strings to the canonical provider enum at the SDK boundary.
        try:
            return self.provider if isinstance(self.provider, ModelProvider) else ModelProvider(self.provider)
        except ValueError as exc:
            raise ConfigurationError(f"Unsupported model provider: {self.provider!r}") from exc

    def validate(self) -> None:
        # Validate request shape before provider code builds API payloads.
        self._require_model()
        self._validate_temperature()
        self._validate_top_p()
        self._validate_positive_int(self.max_output_tokens, field_name="max_output_tokens")
        self._validate_positive_float(self.timeout_seconds, field_name="timeout_seconds")
        # @intent keys-are-checked-before-any-request
        # Resolving the credentials refuses a missing or unsendable key
        # here, before any provider code builds a request.
        self.credentials()

    def credentials(self) -> TextCredentials:
        """Resolve the provider key and the Vidbyte key this config's calls send, by mode (spec table R)."""
        # @intent each-mode-reads-only-the-key-it-sends
        # DIRECT never reads the Vidbyte key and VIDBYTE_MANAGED never
        # reads the provider key, so no key is read, or sent, by a mode
        # that has no use for it.
        provider = self.normalized_provider()
        match self.mode:
            case TextModelMode.DIRECT:
                # Straight to the provider with the developer's own
                # key: no Vidbyte key and no Vidbyte fee, so a provider
                # key is required.
                provider_key = ProviderModelRegistry.find_provider_api_key(provider, self.api_keys)
                if provider_key is None:
                    self._refuse_missing_provider_key(provider)
                return TextCredentials(TextModelMode.DIRECT, provider_api_key=provider_key)
            case TextModelMode.VIDBYTE_MANAGED:
                # Through the gateway on Vidbyte's own provider account,
                # so only the Vidbyte key is read.
                vidbyte_key = ProviderModelRegistry.resolve_vidbyte_api_key(self.vidbyte_api_key, remedy=TEXT_REMEDY)
                return TextCredentials(TextModelMode.VIDBYTE_MANAGED, vidbyte_api_key=vidbyte_key)
            case TextModelMode.AUTO:
                # Through the gateway, which always needs the Vidbyte
                # key. The call relays the developer's provider key
                # when there is one, and is Vidbyte-paid otherwise.
                vidbyte_key = ProviderModelRegistry.resolve_vidbyte_api_key(self.vidbyte_api_key, remedy=TEXT_REMEDY)
                provider_key = ProviderModelRegistry.find_provider_api_key(provider, self.api_keys)
                if provider_key is not None:
                    self._require_relayable_length(provider, provider_key)
                return TextCredentials(TextModelMode.AUTO, provider_api_key=provider_key, vidbyte_api_key=vidbyte_key)
            case _:
                raise ConfigurationError("mode must be a TextModelMode value.")

    def resolved_api_key(self) -> str:
        """Return the key an adapter puts in its vendor auth header: the provider key in DIRECT, else the placeholder."""
        # @intent gateway-adapters-see-only-the-placeholder-key
        # Adapters build vendor auth from this value, so in a gateway
        # mode they get a non-secret stand-in, and neither the Vidbyte
        # key nor a relayed provider key ever enters a vendor header.
        # TextCredentials always holds a provider key in DIRECT, so the
        # placeholder serves the gateway modes only.
        provider_api_key = self.credentials().provider_api_key if self.mode is TextModelMode.DIRECT else None
        return provider_api_key if provider_api_key is not None else VIDBYTE_MANAGED_KEY_PLACEHOLDER

    def resolved_endpoint(self) -> str:
        # Prefer caller-provided endpoints for tests, proxies, and compatible APIs.
        return ProviderModelRegistry.resolve_endpoint(self.normalized_provider(), self.endpoint)

    def _require_model(self) -> None:
        # Model names are required by every provider adapter.
        if not self.model.strip():
            raise ConfigurationError("model must be non-empty.")

    def _require_gateway_shape(self, provider: ModelProvider) -> None:
        """Refuse a custom endpoint and any provider the gateway does not serve, before a gateway call can send the Vidbyte key."""
        # @intent gateway-keys-stay-on-the-gateway
        # The Vidbyte key and a relayed provider key must never follow a
        # caller URL or go to a vendor the gateway cannot serve; DIRECT
        # is the way to reach either.
        if self.endpoint is not None and (not isinstance(self.endpoint, str) or self.endpoint.strip()):
            raise ConfigurationError(
                "A custom endpoint is not allowed when text calls go through the Vidbyte gateway. Use mode=TextModelMode.DIRECT to send calls to your own endpoint.",
                details={"mode": self.mode.value},
            )
        if provider not in VIDBYTE_MANAGED_TEXT_PROVIDERS:
            supported = ", ".join(sorted(managed.value for managed in VIDBYTE_MANAGED_TEXT_PROVIDERS))
            raise UnsupportedProviderError(
                f"The Vidbyte gateway serves only: {supported}. Use mode=TextModelMode.DIRECT to call {provider.value} with your own key.",
                details={"provider": provider.value, "mode": self.mode.value},
            )

    def _refuse_missing_provider_key(self, provider: ModelProvider) -> None:
        """Raise the DIRECT error for a provider with no key, naming the providers the list does hold (M-8)."""
        env_var = ProviderModelRegistry.get_api_key_env_var(provider)
        held = ", ".join(member.value for member in self.api_keys.providers)
        hint = f" (api_keys holds keys for: {held})" if held else ""
        raise ConfigurationError(
            f"Missing API key for provider {provider.value}. Pass api_keys or set {env_var}.{hint}",
            details={"provider": provider.value, "mode": self.mode.value},
        )

    def _require_relayable_length(self, provider: ModelProvider, provider_key: str) -> None:
        """Refuse a provider key longer than the gateway relays (M-21)."""
        # @intent relayed-key-fits-the-gateway-header
        # The gateway refuses a provider-key header over its limit, so
        # the call fails here, before any request; DIRECT sends the key
        # straight to the vendor, which has no such limit.
        if len(provider_key) <= VIDBYTE_PROVIDER_KEY_MAX_LENGTH:
            return
        source = "api_keys" if self.api_keys.key_for(provider) is not None else ProviderModelRegistry.get_api_key_env_var(provider)
        raise ConfigurationError(
            f"The {provider.value} key from {source} has {len(provider_key)} characters, and the Vidbyte gateway relays keys of at most {VIDBYTE_PROVIDER_KEY_MAX_LENGTH} characters. Use mode=TextModelMode.DIRECT to send it straight to {provider.value}.",
            details={"provider": provider.value, "source": source, "length": len(provider_key)},
        )

    def _validate_temperature(self) -> None:
        # Most provider APIs accept temperature values in the inclusive 0-2 range.
        if self.temperature is not None and (self.temperature < 0 or self.temperature > 2):
            raise ConfigurationError("temperature must be between 0 and 2.")

    def _validate_top_p(self) -> None:
        # Keep nucleus sampling probability in its expected 0-1 range.
        if self.top_p is not None and (self.top_p < 0 or self.top_p > 1):
            raise ConfigurationError("top_p must be between 0 and 1.")

    def _validate_positive_int(self, value: int | None, *, field_name: str) -> None:
        # Optional integer limits must be positive when supplied.
        if value is not None and value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")

    def _validate_positive_float(self, value: float | None, *, field_name: str) -> None:
        # Optional floating-point limits must be positive when supplied.
        if value is not None and value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")


@dataclass(frozen=True, slots=True)
class TextCredentials:
    """The keys one text call sends, resolved for its mode by TextModelConfig.credentials()."""

    mode: TextModelMode
    provider_api_key: str | None = field(default=None, repr=False)
    vidbyte_api_key: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Refuse a combination of keys that the mode can never send."""
        # @intent credentials-fit-their-mode
        # DIRECT sends only a provider key and VIDBYTE_MANAGED only the
        # Vidbyte key; AUTO always sends the Vidbyte key and may relay a
        # provider key. Any other combination would send a key where its
        # mode never sends one. The message names no key.
        if not isinstance(self.mode, TextModelMode):
            raise ConfigurationError("TextCredentials.mode must be a TextModelMode value.")
        has_provider_key = isinstance(self.provider_api_key, str) and bool(self.provider_api_key.strip())
        has_vidbyte_key = isinstance(self.vidbyte_api_key, str) and bool(self.vidbyte_api_key.strip())
        if self.mode is TextModelMode.DIRECT:
            fits = has_provider_key and self.vidbyte_api_key is None
        elif self.mode is TextModelMode.VIDBYTE_MANAGED:
            fits = has_vidbyte_key and self.provider_api_key is None
        else:
            fits = has_vidbyte_key and (self.provider_api_key is None or has_provider_key)
        if not fits:
            raise ConfigurationError(
                f"TextCredentials in {self.mode.value} mode cannot hold these keys: DIRECT holds only a provider key, VIDBYTE_MANAGED only a Vidbyte key, and AUTO a Vidbyte key with an optional provider key."
            )

    @property
    def uses_gateway(self) -> bool:
        """Return True when the call goes through the Vidbyte gateway, which is every mode but DIRECT."""
        return self.mode is not TextModelMode.DIRECT

    @property
    def relays(self) -> bool:
        """Return True when a gateway call carries the developer's own provider key."""
        return self.uses_gateway and self.provider_api_key is not None


@dataclass(frozen=True, slots=True)
class ImageModelConfig:
    provider: ModelProvider | str
    model: str
    api_key: str | None = None
    size: str | None = None
    quality: str | None = None
    response_format: str | None = None
    n: int | None = None
    background: str | None = None
    output_format: str | None = None
    output_compression: int | None = None
    extra_body: Mapping[str, Any] | None = None
    endpoint: str | None = None
    timeout_seconds: float = 120.0

    def normalized_provider(self) -> ModelProvider:
        # Convert strings to the canonical provider enum at the SDK boundary.
        try:
            return self.provider if isinstance(self.provider, ModelProvider) else ModelProvider(self.provider)
        except ValueError as exc:
            raise ConfigurationError(f"Unsupported model provider: {self.provider!r}") from exc

    def validate(self) -> None:
        # Validate image generation support and shared model fields.
        provider = self.normalized_provider()
        if provider not in {ModelProvider.OPENAI, ModelProvider.XAI}:
            raise UnsupportedProviderError("ImageModelRunner currently supports OpenAI and xAI image APIs.", details={"provider": provider.value})
        if not self.model.strip():
            raise ConfigurationError("model must be non-empty.")
        self._validate_positive_int(self.n, field_name="n")
        self._validate_positive_int(self.output_compression, field_name="output_compression")
        self._validate_positive_float(self.timeout_seconds, field_name="timeout_seconds")
        self.resolved_api_key()

    def resolved_api_key(self) -> str:
        # Resolve explicit keys before provider-specific environment variables.
        return ProviderModelRegistry.resolve_api_key(self.normalized_provider(), self.api_key)

    def resolved_endpoint(self) -> str:
        # Prefer caller-provided endpoints for tests, proxies, and compatible APIs.
        return ProviderModelRegistry.resolve_endpoint(self.normalized_provider(), self.endpoint)

    def _validate_positive_int(self, value: int | None, *, field_name: str) -> None:
        # Optional integer limits must be positive when supplied.
        if value is not None and value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")

    def _validate_positive_float(self, value: float | None, *, field_name: str) -> None:
        # Optional floating-point limits must be positive when supplied.
        if value is not None and value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")


@dataclass(frozen=True, slots=True)
class VideoModelConfig:
    provider: ModelProvider | str
    model: str
    api_key: str | None = None
    size: str | None = None
    seconds: int | None = None
    extra_body: Mapping[str, Any] | None = None
    endpoint: str | None = None
    timeout_seconds: float = 120.0

    def normalized_provider(self) -> ModelProvider:
        # Convert strings to the canonical provider enum at the SDK boundary.
        try:
            return self.provider if isinstance(self.provider, ModelProvider) else ModelProvider(self.provider)
        except ValueError as exc:
            raise ConfigurationError(f"Unsupported model provider: {self.provider!r}") from exc

    def validate(self) -> None:
        # Validate video job support and shared model fields.
        provider = self.normalized_provider()
        if provider != ModelProvider.OPENAI:
            raise UnsupportedProviderError("VideoModelRunner currently supports OpenAI video jobs only.", details={"provider": provider.value})
        if not self.model.strip():
            raise ConfigurationError("model must be non-empty.")
        self._validate_positive_int(self.seconds, field_name="seconds")
        self._validate_positive_float(self.timeout_seconds, field_name="timeout_seconds")
        self.resolved_api_key()

    def resolved_api_key(self) -> str:
        # Resolve explicit keys before provider-specific environment variables.
        return ProviderModelRegistry.resolve_api_key(self.normalized_provider(), self.api_key)

    def resolved_endpoint(self) -> str:
        # Prefer caller-provided endpoints for tests, proxies, and compatible APIs.
        return ProviderModelRegistry.resolve_endpoint(self.normalized_provider(), self.endpoint)

    def _validate_positive_int(self, value: int | None, *, field_name: str) -> None:
        # Optional integer limits must be positive when supplied.
        if value is not None and value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")

    def _validate_positive_float(self, value: float | None, *, field_name: str) -> None:
        # Optional floating-point limits must be positive when supplied.
        if value is not None and value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")


AUDIO_SUPPORTED_PROVIDERS: frozenset[ModelProvider] = frozenset({
    ModelProvider.OPENAI,
    ModelProvider.ELEVENLABS,
    ModelProvider.PLAYAI,
})

EMBEDDING_SUPPORTED_PROVIDERS: frozenset[ModelProvider] = frozenset({
    ModelProvider.OPENAI,
    ModelProvider.GEMINI,
})


@dataclass(frozen=True, slots=True)
class AudioModelConfig:
    provider: ModelProvider | str
    model: str
    api_key: str | None = None
    voice: str | None = None
    speed: float | None = None
    response_format: str | None = None
    language: str | None = None
    extra_body: Mapping[str, Any] | None = None
    endpoint: str | None = None
    timeout_seconds: float = 120.0

    def normalized_provider(self) -> ModelProvider:
        # Convert strings to the canonical provider enum at the SDK boundary.
        try:
            return self.provider if isinstance(self.provider, ModelProvider) else ModelProvider(self.provider)
        except ValueError as exc:
            raise ConfigurationError(f"Unsupported model provider: {self.provider!r}") from exc

    def validate(self) -> None:
        # Validate audio support and shared model fields.
        provider = self.normalized_provider()
        if provider not in AUDIO_SUPPORTED_PROVIDERS:
            raise UnsupportedProviderError(
                f"AudioModelRunner supports: {', '.join(p.value for p in AUDIO_SUPPORTED_PROVIDERS)}.",
                details={"provider": provider.value},
            )
        if not self.model.strip():
            raise ConfigurationError("model must be non-empty.")
        self._validate_speed()
        self._validate_positive_float(self.timeout_seconds, field_name="timeout_seconds")
        self.resolved_api_key()

    def resolved_api_key(self) -> str:
        # Resolve explicit keys before provider-specific environment variables.
        return ProviderModelRegistry.resolve_api_key(self.normalized_provider(), self.api_key)

    def resolved_endpoint(self) -> str:
        # Prefer caller-provided endpoints for tests, proxies, and compatible APIs.
        return ProviderModelRegistry.resolve_endpoint(self.normalized_provider(), self.endpoint)

    def _validate_speed(self) -> None:
        # OpenAI TTS accepts speed in the 0.25–4.0 range; enforce globally.
        if self.speed is not None and (self.speed < 0.25 or self.speed > 4.0):
            raise ConfigurationError("speed must be between 0.25 and 4.0.")

    def _validate_positive_float(self, value: float | None, *, field_name: str) -> None:
        # Optional floating-point limits must be positive when supplied.
        if value is not None and value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")


@dataclass(frozen=True, slots=True)
class EmbeddingModelConfig:
    provider: ModelProvider | str
    model: str
    api_key: str | None = None
    dimensions: int | None = None
    input_type: str | None = None
    extra_body: Mapping[str, Any] | None = None
    endpoint: str | None = None
    timeout_seconds: float = 60.0

    def normalized_provider(self) -> ModelProvider:
        # Convert strings to the canonical provider enum at the SDK boundary.
        try:
            return self.provider if isinstance(self.provider, ModelProvider) else ModelProvider(self.provider)
        except ValueError as exc:
            raise ConfigurationError(f"Unsupported model provider: {self.provider!r}") from exc

    def validate(self) -> None:
        # Validate embedding support and shared model fields.
        provider = self.normalized_provider()
        if provider not in EMBEDDING_SUPPORTED_PROVIDERS:
            raise UnsupportedProviderError(
                f"EmbeddingModelRunner supports: {', '.join(p.value for p in EMBEDDING_SUPPORTED_PROVIDERS)}.",
                details={"provider": provider.value},
            )
        if not self.model.strip():
            raise ConfigurationError("model must be non-empty.")
        self._validate_positive_int(self.dimensions, field_name="dimensions")
        self._validate_positive_float(self.timeout_seconds, field_name="timeout_seconds")
        self.resolved_api_key()

    def resolved_api_key(self) -> str:
        # Resolve explicit keys before provider-specific environment variables.
        return ProviderModelRegistry.resolve_api_key(self.normalized_provider(), self.api_key)

    def resolved_endpoint(self) -> str:
        # Prefer caller-provided endpoints for tests, proxies, and compatible APIs.
        return ProviderModelRegistry.resolve_endpoint(self.normalized_provider(), self.endpoint)

    def _validate_positive_int(self, value: int | None, *, field_name: str) -> None:
        # Optional integer limits must be positive when supplied.
        if value is not None and value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")

    def _validate_positive_float(self, value: float | None, *, field_name: str) -> None:
        # Optional floating-point limits must be positive when supplied.
        if value is not None and value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")


DECISION_SUPPORTED_PROVIDERS: frozenset[ModelProvider] = frozenset({
    ModelProvider.TYPESAFE,
})


@dataclass(frozen=True, slots=True)
class DecisionModelConfig:
    """Configuration for one decision model using TypeSafe directly or Vidbyte's managed gateway."""

    provider: ModelProvider | str = ModelProvider.TYPESAFE
    model: str = JEV_DEFAULT_MODEL
    api_key: str | None = field(default=None, repr=False)
    endpoint: str | None = None
    timeout_seconds: float = JEV_DEFAULT_TIMEOUT_SECONDS
    retry_count: int = JEV_DEFAULT_RETRY_COUNT
    mode: DecisionModelMode = DecisionModelMode.TYPESAFE

    def __post_init__(self) -> None:
        # Rejects shape errors at construction so a bad config never waits for its first call.
        # @intent decision-config-shape-fails-at-construction
        # The API key is deliberately not resolved here so disabled Jev features need no credential;
        # active callers validate it when they build the decision runner and apply their failure policy.
        provider = self.normalized_provider()
        if provider not in DECISION_SUPPORTED_PROVIDERS:
            raise UnsupportedProviderError(
                f"DecisionModelRunner supports: {', '.join(p.value for p in DECISION_SUPPORTED_PROVIDERS)}.",
                details={"provider": provider.value},
            )
        if not isinstance(self.mode, DecisionModelMode):
            raise ConfigurationError("mode must be a DecisionModelMode value.")
        if self.mode is DecisionModelMode.VIDBYTE_MANAGED and self.endpoint is not None:
            if not isinstance(self.endpoint, str) or self.endpoint.strip():
                raise ConfigurationError("A custom endpoint is not allowed for VIDBYTE_MANAGED decision mode.")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ConfigurationError("model must be non-empty.")
        if not isinstance(self.timeout_seconds, (int, float)) or self.timeout_seconds <= JEV_TIMEOUT_FLOOR_SECONDS:
            raise ConfigurationError("timeout_seconds must be greater than zero.")
        if isinstance(self.retry_count, bool) or not isinstance(self.retry_count, int) or self.retry_count < JEV_NO_RETRIES:
            raise ConfigurationError("retry_count must be a non-negative integer.")

    def normalized_provider(self) -> ModelProvider:
        # Convert strings to the canonical provider enum at the SDK boundary.
        # @intent decision-provider-coerced-once
        # Callers may pass the provider as a string; coercing here keeps every later lookup
        # (support check, key, endpoint) keyed on the enum's frozen set of providers.
        try:
            return self.provider if isinstance(self.provider, ModelProvider) else ModelProvider(self.provider)
        except ValueError as exc:
            raise ConfigurationError(f"Unsupported model provider: {self.provider!r}") from exc

    def validate(self) -> None:
        # Resolves the API key; shape checks already ran when the config was constructed.
        self.resolved_api_key()

    def resolved_api_key(self) -> str:
        # Resolves the selected mode's key source without exposing the credential in errors.
        # @intent managed-mode-never-falls-back-to-typesafe-key
        # A managed call must use a Vidbyte live key; only direct mode may resolve TYPESAFE_API_KEY.
        if self.mode is DecisionModelMode.VIDBYTE_MANAGED:
            if self.api_key is not None and not isinstance(self.api_key, str):
                raise ConfigurationError("api_key must be a string in VIDBYTE_MANAGED decision mode.", details={"error_kind": VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND})
            return ProviderModelRegistry.resolve_vidbyte_api_key(self.api_key)
        # Resolves explicit TypeSafe keys before the provider-specific environment variable.
        # @intent explicit-key-wins-over-environment
        # Direct mode preserves the existing TypeSafe key resolution for standalone runners.
        return ProviderModelRegistry.resolve_api_key(self.normalized_provider(), self.api_key)

    def resolved_endpoint(self) -> str:
        # Pins managed credentials to Vidbyte while preserving direct provider endpoint overrides.
        # @intent managed-key-stays-on-vidbyte-host
        # Direct TypeSafe proxies remain configurable, but the Vidbyte bearer credential never follows a caller URL.
        if self.mode is DecisionModelMode.VIDBYTE_MANAGED:
            return VIDBYTE_JEV_GATEWAY_ENDPOINT
        # @intent explicit-endpoint-wins-over-default
        # Proxies and test servers remain available for direct TypeSafe calls.
        return ProviderModelRegistry.resolve_endpoint(self.normalized_provider(), self.endpoint)

    def resolved_run_close_url(self, run_id: str) -> str:
        """Return the gateway close URL for one managed Jev run."""
        if self.mode is not DecisionModelMode.VIDBYTE_MANAGED:
            raise ConfigurationError("Only a managed DecisionModelConfig has runs to close.")
        root = self.resolved_endpoint().removesuffix(JEV_MANAGED_GATEWAY_SUFFIX)
        return f"{root}{JEV_MANAGED_RUN_CLOSE_PATH.format(run_id=run_id)}"

    @classmethod
    def vidbyte_managed(cls) -> DecisionModelConfig:
        # Builds the pinned Vidbyte gateway configuration used by JevAgent by default.
        # @intent jev-defaults-to-managed-gateway
        # Keeping this factory separate leaves standalone DecisionModelConfig defaulted to direct TypeSafe access.
        return cls(mode=DecisionModelMode.VIDBYTE_MANAGED)


__all__ = [
    "AUDIO_SUPPORTED_PROVIDERS",
    "DECISION_SUPPORTED_PROVIDERS",
    "DecisionModelConfig",
    "EMBEDDING_SUPPORTED_PROVIDERS",
    "AudioModelConfig",
    "EmbeddingModelConfig",
    "ImageModelConfig",
    "TextCredentials",
    "TextModelConfig",
    "VideoModelConfig",
]
