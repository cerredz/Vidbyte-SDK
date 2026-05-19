from __future__ import annotations

from typing import Mapping

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.http import HttpTransport
from vidbyte.lib.runners.types import TextModelResponse
from vidbyte.providers import get_text_provider


class TextModelRunner:
    """Semantic runner for text generation models."""

    def __init__(
        self,
        config: TextModelConfig,
        *,
        transport: HttpTransport | None = None,
    ) -> None:
        config.validate()
        self._config = config
        self._transport = transport or HttpTransport()
        self._provider = get_text_provider(config.normalized_provider())

    def run(
        self,
        prompt: str,
        *,
        system: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> TextModelResponse:
        return self._provider.run_text(
            config=self._config,
            prompt=prompt,
            system=system,
            metadata=metadata,
            transport=self._transport,
        )

    def model_name(self) -> str:
        return self._config.model

    def print(self, response: TextModelResponse) -> None:
        print(response.text)
