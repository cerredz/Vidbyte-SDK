"""FILE: vidbyte/lib/runners/text.py

PURPOSE: Runs one text model call through its provider adapter, routing it by the config's resolved credentials: DIRECT goes straight to the provider with the caller's own key, and AUTO and VIDBYTE_MANAGED go through the Vidbyte gateway, relaying the caller's provider key when the credentials hold one.
ROLE IN CODEBASE: The text runner every agent, fallback, and paradigm builds through Runner and ModalityDetector; TextModelConfig.credentials() decides the keys, VidbyteGatewayTransport carries a gateway call, and the provider adapters in vidbyte/providers build and parse the native request.
ARCHITECTURE NOTE: A gateway runner resolves its TextCredentials once, at construction, and builds one VidbyteGatewayTransport for each call, so the keys it sends never change with the environment and are never shared between concurrent calls. A DIRECT runner leaves its config as it was and the adapter resolves the provider key for each call.
COMMON MODIFICATION PATTERNS: A new mode changes TextModelConfig.credentials() and the uses_gateway branch here together; a new gateway requirement (an output cap, a timeout floor) is pinned in __init__ beside the existing ones.
KNOWN EDGE CASES: The timeout floor is applied first, so a NaN timeout becomes the floor. A missing Vidbyte key in a gateway mode, or a missing provider key in DIRECT, raises when the runner is built, before any request.
RELATED DOCS: docs/spec/byok-api-keys/spec.md (sections 5 and 9.2 table R; INV-12, INV-16, INV-20); docs/spec/managed-generative-models/spec.md.
TESTS: tests/features/sdk_provider_keys/test_provider_keys_modes.py, tests/features/sdk_provider_keys/test_provider_keys_wire_contract.py, and tests/features/sdk_managed_text/.
"""

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
from vidbyte.lib.enums import ModelProvider
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
        # Check the config before anything is sent, which also proves
        # the keys its mode needs are present and sendable.
        config.validate()
        # @intent gateway-runner-is-pinned-at-construction
        # Resolve the keys once, so a gateway runner keeps sending the
        # same Vidbyte key and relayed provider key after the
        # environment changes. A gateway config also gets the output
        # cap the gateway requires and a timeout no shorter than the
        # gateway's own upstream deadline (floor first, so a NaN
        # timeout becomes the floor); a DIRECT config is left as it was.
        self._credentials = config.credentials()
        if self._credentials.uses_gateway:
            config = replace(
                config,
                max_output_tokens=config.max_output_tokens or VIDBYTE_MANAGED_DEFAULT_MAX_OUTPUT_TOKENS,
                timeout_seconds=max(VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS, config.timeout_seconds),
            )
        # Keep the config, the caller's transport, and the provider
        # adapter that builds each native request.
        self._config = config
        self._transport = transport or HttpTransport()
        self._provider = ModelProviders.text(config)

    async def arun(self, prompt: str, *, system: str | None = None, metadata: Mapping[str, object] | None = None, tools: Iterable[Mapping[str, Any]] = (), tool_choice: str | Mapping[str, Any] | None = None, messages: Iterable[Mapping[str, Any]] = (), response_format: Mapping[str, Any] | None = None, prompt_index: int | None = None) -> TextModelResponse:
        """Async entry point; awaits the provider's HTTP call without blocking the event loop."""
        # Add this call's tools, messages, where the prompt goes among them, and output format.
        call_config = replace(
            self._config,
            tools=tuple(dict(tool) for tool in tools),
            tool_choice=tool_choice,
            messages=tuple(dict(message) for message in messages),
            response_format=response_format,
            prompt_index=prompt_index,
        )
        # @intent gateway-calls-route-through-one-transport-per-call
        # The adapter still builds its native request; for a gateway
        # call, a gateway transport built for this call alone replaces
        # its vendor URL and headers, carrying the pinned Vidbyte key
        # and, on a relay call, the pinned provider key. Every gateway
        # call reaches the one gateway route and concurrent calls never
        # share a transport.
        transport = self._transport
        if self._credentials.uses_gateway:
            transport = VidbyteGatewayTransport(
                self._transport,
                provider=call_config.normalized_provider(),
                model=call_config.model,
                api_key=self._credentials.vidbyte_api_key,  # type: ignore[arg-type]
                provider_api_key=self._credentials.provider_api_key,
            )
        # Let the provider adapter build, send, and parse the request.
        return await self._provider.run_text(
            prompt=prompt,
            system=system,
            metadata=metadata,
            transport=transport,
            config=call_config,
        )

    def run(self, prompt: str, *, system: str | None = None, metadata: Mapping[str, object] | None = None, tools: Iterable[Mapping[str, Any]] = (), tool_choice: str | Mapping[str, Any] | None = None, messages: Iterable[Mapping[str, Any]] = (), response_format: Mapping[str, Any] | None = None, prompt_index: int | None = None) -> TextModelResponse:
        # Synchronous wrapper; raises if called from inside a running event loop.
        try:
            asyncio.get_running_loop()
            raise AgentExecutionError("TextModelRunner.run() cannot be called from an active event loop; use await arun().")
        except RuntimeError:
            pass
        return asyncio.run(self.arun(prompt, system=system, metadata=metadata, tools=tools, tool_choice=tool_choice, messages=messages, response_format=response_format, prompt_index=prompt_index))

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
