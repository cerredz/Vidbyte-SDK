from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import replace
from typing import Any, Mapping

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.constants.jev import (
    VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS,
    VIDBYTE_MANAGED_DEFAULT_MAX_OUTPUT_TOKENS,
)
from vidbyte.lib.enums import ModelProvider, TextModelMode
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError
from vidbyte.lib.http import HttpTransport
from vidbyte.lib.http.vidbyte_gateway import VidbyteGatewayTransport
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
        # Build the config from the arguments when none was passed.
        config = self._coerce_config(config, provider=provider, model=model, config_options=config_options)
        # Check the config before anything is sent; a managed config
        # also proves it holds a live Vidbyte key and suits the gateway.
        config.validate()
        # @intent managed-runner-is-pinned-at-construction
        # Pin a managed config once: explicit mode, the selected Vidbyte
        # key, the output cap the gateway requires, and a timeout no
        # shorter than the gateway's own upstream deadline (floor first,
        # so a NaN timeout becomes the floor). This keeps a managed
        # runner on the gateway after the environment changes; a BYOK
        # config is left as it was, so BYOK does not change.
        self._managed = config.is_vidbyte_managed()
        if self._managed:
            config = replace(
                config,
                mode=TextModelMode.VIDBYTE_MANAGED,
                api_key=config.resolved_vidbyte_api_key(),
                max_output_tokens=config.max_output_tokens or VIDBYTE_MANAGED_DEFAULT_MAX_OUTPUT_TOKENS,
                timeout_seconds=max(VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS, config.timeout_seconds),
            )
        # Keep the config, the caller's transport, and the provider
        # adapter that builds each native request.
        self._config = config
        self._transport = transport or HttpTransport()
        self._provider = ModelProviders.text(config)

    async def arun(self, prompt: str, *, system: str | None = None, metadata: Mapping[str, object] | None = None, tools: Iterable[Mapping[str, Any]] = (), tool_choice: str | Mapping[str, Any] | None = None, messages: Iterable[Mapping[str, Any]] = (), response_format: Mapping[str, Any] | None = None) -> TextModelResponse:
        """Async entry point; awaits the provider's HTTP call without blocking the event loop."""
        # Add this call's tools, messages, and output format.
        call_config = replace(
            self._config,
            tools=tuple(dict(tool) for tool in tools),
            tool_choice=tool_choice,
            messages=tuple(dict(message) for message in messages),
            response_format=response_format,
        )
        # @intent managed-calls-route-through-the-gateway-transport
        # The adapter still builds its native request; in managed state
        # a gateway transport built for this call alone replaces its
        # vendor URL and headers, so every managed call reaches the one
        # gateway route and concurrent calls never share a key.
        transport = self._transport
        if self._managed:
            transport = VidbyteGatewayTransport(
                self._transport,
                provider=call_config.normalized_provider(),
                model=call_config.model,
                api_key=call_config.resolved_vidbyte_api_key(),
            )
        # Let the provider adapter build, send, and parse the request.
        return await self._provider.run_text(
            prompt=prompt,
            system=system,
            metadata=metadata,
            transport=transport,
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
