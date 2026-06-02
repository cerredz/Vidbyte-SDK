from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import replace
from typing import Any, Mapping

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.errors import ConfigurationError, UnsupportedProviderError
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.http import HttpTransport
from vidbyte.providers import ModelProviders


class StreamingTextModelRunner:
    """Semantic runner for streaming text generation models via SSE."""

    STREAMING_SUPPORTED_PROVIDERS: frozenset[ModelProvider] = frozenset({
        ModelProvider.OPENAI,
        ModelProvider.ANTHROPIC,
    })

    def __init__(self, config: TextModelConfig | None = None, *, provider: ModelProvider | str | None = None, model: str | None = None, transport: HttpTransport | None = None, **config_options: Any) -> None:
        # Coerce config, validate provider supports streaming, then build the adapter.
        config = self._coerce_config(config, provider=provider, model=model, config_options=config_options)
        config.validate()
        self._validate_streaming_provider(config.normalized_provider())
        self._config = config
        self._transport = transport or HttpTransport()
        self._provider = ModelProviders.streaming_text(config)

    def stream(self, prompt: str, *, system: str | None = None, metadata: Mapping[str, object] | None = None, tools: Iterable[Mapping[str, Any]] | None = None, tool_choice: str | Mapping[str, Any] | None = None, messages: Iterable[Mapping[str, Any]] | None = None, response_format: Mapping[str, Any] | None = None) -> Iterator[str]:
        # Yield text chunk strings as they arrive from the provider SSE stream.
        call_config = replace(
            self._config,
            tools=tuple(dict(tool) for tool in tools) if tools is not None else self._config.tools,
            tool_choice=tool_choice if tool_choice is not None else self._config.tool_choice,
            messages=tuple(dict(message) for message in messages) if messages is not None else self._config.messages,
            response_format=dict(response_format) if response_format is not None else self._config.response_format,
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
