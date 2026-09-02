from __future__ import annotations

from typing import Any, Mapping

from vidbyte.lib.config import EmbeddingModelConfig
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.http import HttpTransport
from vidbyte.lib.runners.types import EmbeddingResponse
from vidbyte.providers import ModelProviders


class EmbeddingModelRunner:
    """Semantic runner for dense vector embedding models."""

    def __init__(self, config: EmbeddingModelConfig | None = None, *, provider: ModelProvider | str | None = None, model: str | None = None, transport: HttpTransport | None = None, **config_options: Any) -> None:
        # Coerce config from kwargs if not supplied directly, then validate and build provider.
        config = self._coerce_config(config, provider=provider, model=model, config_options=config_options)
        config.validate()
        self._config = config
        self._transport = transport or HttpTransport()
        self._provider = ModelProviders.embedding(config)

    def run(self, texts: str | list[str]) -> EmbeddingResponse:
        # Normalize texts to a list and call the provider embedding endpoint.
        normalized = self._normalize_texts(texts)
        return self._provider.run_embedding(texts=normalized, transport=self._transport)

    def model_name(self) -> str:
        # Return the configured model identifier string.
        return self._config.model

    def _normalize_texts(self, texts: str | list[str]) -> list[str]:
        # Convert a bare string to a single-item list; reject empty lists.
        if isinstance(texts, str):
            return [texts]
        as_list = list(texts)
        if not as_list:
            raise ConfigurationError("texts must be non-empty.")
        return as_list

    def _coerce_config(self, config: EmbeddingModelConfig | None, *, provider: ModelProvider | str | None, model: str | None, config_options: Mapping[str, Any]) -> EmbeddingModelConfig:
        # Return config as-is if supplied; otherwise build one from provider+model kwargs.
        if config is not None:
            return config
        if provider is None or model is None:
            raise ConfigurationError("EmbeddingModelRunner requires either config or provider and model.")
        return EmbeddingModelConfig(provider=provider, model=model, **dict(config_options))
