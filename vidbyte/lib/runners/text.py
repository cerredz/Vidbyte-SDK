from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import Any

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError
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

    async def arun(self, prompt: str, *, system: str | None = None, metadata: Mapping[str, object] | None = None, tools: Iterable[Mapping[str, Any]] = (), tool_choice: str | Mapping[str, Any] | None = None, messages: Iterable[Mapping[str, Any]] = (), response_format: Mapping[str, Any] | None = None) -> TextModelResponse:
        # Async entry point; awaits the provider's HTTP call without blocking the event loop.
        call_config = replace(
            self._config,
            tools=tuple(dict(tool) for tool in tools),
            tool_choice=tool_choice,
            messages=tuple(dict(message) for message in messages),
            response_format=response_format,
        )
        return await self._provider.run_text(
            prompt=prompt,
            system=system,
            metadata=metadata,
            transport=self._transport,
            config=call_config,
        )

    def run(self, prompt: str, *, system: str | None = None, metadata: Mapping[str, object] | None = None, tools: Iterable[Mapping[str, Any]] = (), tool_choice: str | Mapping[str, Any] | None = None, messages: Iterable[Mapping[str, Any]] = (), response_format: Mapping[str, Any] | None = None) -> TextModelResponse:
        # Synchronous wrapper; raises if called from inside a running event loop.
        try:
            asyncio.get_running_loop()
            raise AgentExecutionError("TextModelRunner.run() cannot be called from an active event loop; use await arun().")
        except RuntimeError:
            pass
        return asyncio.run(self.arun(prompt, system=system, metadata=metadata, tools=tools, tool_choice=tool_choice, messages=messages, response_format=response_format))

    def model_name(self) -> str:
        return self._config.model

    def print(self, response: TextModelResponse) -> None:
        print(response.text)

    def _coerce_config(self, config: TextModelConfig | None, *, provider: ModelProvider | str | None, model: str | None, config_options: Mapping[str, Any]) -> TextModelConfig:
        if config is not None:
            return config
        if provider is None or model is None:
            raise ConfigurationError("TextModelRunner requires either config or provider and model.")
        return TextModelConfig(provider=provider, model=model, **dict(config_options))
