from __future__ import annotations

from typing import Any, Mapping

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.http import HttpTransport
from vidbyte.lib.runners.types import TextModelResponse
from vidbyte.providers import ModelProviders


class TextModelRunner:
    """Semantic runner for text generation models."""

    def __init__(
        self,
        config: TextModelConfig | None = None,
        *,
        provider: ModelProvider | str | None = None,
        model: str | None = None,
        transport: HttpTransport | None = None,
        **config_options: Any,
    ) -> None:
        config = self._coerce_config(config, provider=provider, model=model, config_options=config_options)
        config.validate()
        self._config = config
        self._transport = transport or HttpTransport()
        self._provider = ModelProviders.text(config)

    def run(
        self,
        prompt: str,
        *,
        system: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> TextModelResponse:
        return self._provider.run_text(
            prompt=prompt,
            system=system,
            metadata=metadata,
            transport=self._transport,
        )

    def model_name(self) -> str:
        return self._config.model

    def print(self, response: TextModelResponse) -> None:
        print(response.text)

    def _coerce_config(
        self,
        config: TextModelConfig | None,
        *,
        provider: ModelProvider | str | None,
        model: str | None,
        config_options: Mapping[str, Any],
    ) -> TextModelConfig:
        if config is not None:
            return config
        if provider is None or model is None:
            raise ConfigurationError("TextModelRunner requires either config or provider and model.")
        return TextModelConfig(provider=provider, model=model, **dict(config_options))
