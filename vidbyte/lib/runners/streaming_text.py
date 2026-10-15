"""FILE: vidbyte/lib/runners/streaming_text.py

PURPOSE: Streams text from a provider over server-sent events, only in TextModelMode.DIRECT, straight from the provider with the caller's own key.
ROLE IN CODEBASE: The streaming counterpart of TextModelRunner; ModelProviders.streaming_text builds the adapter (OpenAI or Anthropic) that sends the request and yields text chunks.
ARCHITECTURE NOTE: The gateway cannot bill a stream and refuses one, so every gateway mode (AUTO and VIDBYTE_MANAGED) is refused at construction, before validate() resolves or reads any key; a DIRECT config is validated and streams as before.
COMMON MODIFICATION PATTERNS: A provider that can stream joins STREAMING_SUPPORTED_PROVIDERS together with its adapter's stream_text; the refusal's way forward names it automatically.
KNOWN EDGE CASES: For a provider that cannot stream, the refusal does not suggest DIRECT, because DIRECT would not make it stream either.
RELATED DOCS: docs/spec/byok-api-keys/spec.md (INV-11, D-10, table M row M-15).
TESTS: tests/features/sdk_provider_keys/test_provider_keys_modes.py and tests/test_streaming_text_runner.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import replace
from typing import Any, Mapping

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.errors import ConfigurationError, UnsupportedProviderError
from vidbyte.lib.enums import ModelProvider, TextModelMode
from vidbyte.lib.http import SyncHttpTransport
from vidbyte.providers import ModelProviders


class StreamingTextModelRunner:
    """Semantic runner for streaming text generation models via SSE."""

    STREAMING_SUPPORTED_PROVIDERS: frozenset[ModelProvider] = frozenset({
        ModelProvider.OPENAI,
        ModelProvider.ANTHROPIC,
    })

    def __init__(self, config: TextModelConfig | None = None, *, provider: ModelProvider | str | None = None, model: str | None = None, transport: SyncHttpTransport | None = None, **config_options: Any) -> None:
        # Build the config from the arguments when none was passed.
        config = self._coerce_config(config, provider=provider, model=model, config_options=config_options)
        # Refuse every gateway mode first, before any key is read, so
        # the caller learns why and how to stream with their own key.
        self._refuse_gateway_streaming(config)
        # Check the DIRECT config and that its provider can stream, then
        # build the adapter.
        config.validate()
        self._validate_streaming_provider(config.normalized_provider())
        self._config = config
        self._transport = transport or SyncHttpTransport()
        self._provider = ModelProviders.streaming_text(config)

    def stream(self, prompt: str, *, system: str | None = None, metadata: Mapping[str, object] | None = None, tools: Iterable[Mapping[str, Any]] = (), tool_choice: str | Mapping[str, Any] | None = None, messages: Iterable[Mapping[str, Any]] = (), prompt_index: int | None = None) -> Iterator[str]:
        # Yield text chunk strings as they arrive from the provider SSE stream.
        call_config = replace(
            self._config,
            tools=tuple(dict(tool) for tool in tools),
            tool_choice=tool_choice,
            messages=tuple(dict(message) for message in messages),
            prompt_index=prompt_index,
        )
        yield from self._provider.stream_text(
            prompt=prompt,
            system=system,
            metadata=metadata,
            transport=self._transport,
            config=call_config,
        )

    def model_name(self) -> str:
        # Return the configured model identifier string.
        return self._config.model

    def _refuse_gateway_streaming(self, config: TextModelConfig) -> None:
        """Raise UnsupportedProviderError at init time for every mode but DIRECT."""
        # @intent gateway-streaming-is-refused-before-any-request
        # The gateway cannot bill a stream and refuses one; refusing
        # here reads no key, sends nothing, and names both ways forward.
        if config.mode is TextModelMode.DIRECT:
            return
        provider = config.normalized_provider()
        # Offer DIRECT as a way to stream only for a provider this
        # runner can stream; for any other provider that advice would
        # just lead to the provider refusal below.
        way_forward = f"Set mode=TextModelMode.DIRECT to stream from {provider.value} with your own key, or use TextModelRunner, which sends the call through the Vidbyte gateway."
        if provider not in self.STREAMING_SUPPORTED_PROVIDERS:
            streaming = ", ".join(sorted(supported.value for supported in self.STREAMING_SUPPORTED_PROVIDERS))
            way_forward = f"Use TextModelRunner: streaming supports only {streaming}, so TextModelMode.DIRECT would not make {provider.value} stream either."
        raise UnsupportedProviderError(
            f"StreamingTextModelRunner streams only straight from the provider, and this config's mode is TextModelMode.{config.mode.name}. {way_forward}",
            details={"provider": provider.value, "mode": config.mode.value},
        )

    def _validate_streaming_provider(self, provider: ModelProvider) -> None:
        # Raise UnsupportedProviderError at init time when the provider cannot stream.
        if provider not in self.STREAMING_SUPPORTED_PROVIDERS:
            supported = ", ".join(p.value for p in self.STREAMING_SUPPORTED_PROVIDERS)
            raise UnsupportedProviderError(
                f"StreamingTextModelRunner supports: {supported}.",
                details={"provider": provider.value},
            )

    def _coerce_config(self, config: TextModelConfig | None, *, provider: ModelProvider | str | None, model: str | None, config_options: Mapping[str, Any]) -> TextModelConfig:
        # Return config as-is if supplied; otherwise build one from provider+model kwargs.
        if config is not None:
            return config
        if provider is None or model is None:
            raise ConfigurationError("StreamingTextModelRunner requires either config or provider and model.")
        return TextModelConfig(provider=provider, model=model, **dict(config_options))
