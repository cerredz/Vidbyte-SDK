from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import replace
from typing import Any, Mapping

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.dataclasses.skills import (
    _USE_CONFIGURED_CLAUDE_SESSION,
    ClaudeSkillReference,
    ClaudeSkillSession,
    _ClaudeSessionDefault,
)
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError, UnsupportedProviderError
from vidbyte.lib.http import SyncHttpTransport
from vidbyte.providers import ModelProviders


class StreamingTextModelRunner:
    """Semantic runner for streaming text generation models via SSE."""

    STREAMING_SUPPORTED_PROVIDERS: frozenset[ModelProvider] = frozenset({
        ModelProvider.OPENAI,
        ModelProvider.ANTHROPIC,
    })

    def __init__(self, config: TextModelConfig | None = None, *, provider: ModelProvider | str | None = None, model: str | None = None, transport: SyncHttpTransport | None = None, **config_options: Any) -> None:
        # Coerce config, validate provider supports streaming, then build the adapter.
        config = self._coerce_config(config, provider=provider, model=model, config_options=config_options)
        config.validate()
        self._validate_streaming_provider(config.normalized_provider())
        self._config = config
        self._transport = transport or SyncHttpTransport()
        self._provider = ModelProviders.streaming_text(config)

    def stream(self, prompt: str, *, system: str | None = None, metadata: Mapping[str, object] | None = None, tools: Iterable[Mapping[str, Any]] = (), tool_choice: str | Mapping[str, Any] | None = None, messages: Iterable[Mapping[str, Any]] = (), claude_skills: Iterable[ClaudeSkillReference] | None = None, claude_skill_session: ClaudeSkillSession | None | _ClaudeSessionDefault = _USE_CONFIGURED_CLAUDE_SESSION) -> Iterator[str]:
        # Yield text chunk strings as they arrive from the provider SSE stream.
        native_skills = self._config.claude_skills if claude_skills is None else tuple(claude_skills)
        native_session = self._config.claude_skill_session if claude_skill_session is _USE_CONFIGURED_CLAUDE_SESSION else claude_skill_session
        if native_skills or native_session is not None:
            raise UnsupportedProviderError("Streaming Claude-native skill requests are not supported.", details={"provider": self._config.normalized_provider().value})
        call_config = replace(
            self._config,
            tools=tuple(dict(tool) for tool in tools),
            tool_choice=tool_choice,
            messages=tuple(dict(message) for message in messages),
            claude_skills=native_skills,
            claude_skill_session=native_session,
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
