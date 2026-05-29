from __future__ import annotations

from typing import Any, Mapping

from vidbyte.lib.config import ImageModelConfig, TextModelConfig, VideoModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ProviderConfigurationError, ProviderResponseError
from vidbyte.lib.http import HttpResponseParser, HttpTransport
from vidbyte.lib.runners.types import GeneratedImage, ImageModelResponse, TextModelResponse, VideoModelJob


class OpenAIProvider:
    provider = ModelProvider.OPENAI

    def __init__(
        self,
        *,
        text_config: TextModelConfig | None = None,
        image_config: ImageModelConfig | None = None,
        video_config: VideoModelConfig | None = None,
        model: str | None = None,
        response_parser: HttpResponseParser | None = None,
        **config_options: Any,
    ) -> None:
        # Keep response parsing injectable for tests and alternate transports.
        self._text_config = text_config or self._build_text_config(model=model, config_options=config_options)
        self._image_config = image_config
        self._video_config = video_config
        self._parser = response_parser or HttpResponseParser()

    async def run_text(self, *, prompt: str, system: str | None, metadata: Mapping[str, object] | None, transport: HttpTransport, config: TextModelConfig | None = None) -> TextModelResponse:
        # Execute OpenAI Responses API with tools, metadata, and structured output support.
        config = self._text_config_for(config)
        response = await transport.request(method="POST", url=f"{config.resolved_endpoint()}/responses", headers=self._parser.bearer_headers(config.resolved_api_key()), json_body=self._create_text_payload(config, prompt, system, metadata), timeout_seconds=config.timeout_seconds)
        parsed = self._parser.parse_json_response(response, provider=self.provider.value)
        return TextModelResponse(provider=self.provider, model=config.model, text=self._extract_response_text(parsed), raw=parsed, usage=parsed.get("usage") if isinstance(parsed.get("usage"), dict) else None)

    async def run_image(self, *, prompt: str, transport: HttpTransport, config: ImageModelConfig | None = None) -> ImageModelResponse:
        # Execute OpenAI image generation endpoint with generation controls.
        config = self._image_config_for(config)
        response = await transport.request(method="POST", url=f"{config.resolved_endpoint()}/images/generations", headers=self._parser.bearer_headers(config.resolved_api_key()), json_body=self._create_image_payload(config, prompt), timeout_seconds=config.timeout_seconds)
        parsed = self._parser.parse_json_response(response, provider=self.provider.value)
        return ImageModelResponse(provider=self.provider, model=config.model, images=self._extract_images(parsed), raw=parsed)

    async def create_video(self, *, prompt: str, transport: HttpTransport, config: VideoModelConfig | None = None) -> VideoModelJob:
        # Create an asynchronous OpenAI video job without hiding polling behavior.
        config = self._video_config_for(config)
        response = await transport.request(method="POST", url=f"{config.resolved_endpoint()}/videos", headers=self._parser.bearer_headers(config.resolved_api_key()), json_body=self._create_video_payload(config, prompt), timeout_seconds=config.timeout_seconds)
        parsed = self._parser.parse_json_response(response, provider=self.provider.value)
        return self._video_job_from_response(parsed, model=config.model)

    async def get_video_status(self, *, job_id: str, transport: HttpTransport, config: VideoModelConfig | None = None) -> VideoModelJob:
        # Retrieve the latest status for an existing OpenAI video job.
        config = self._video_config_for(config)
        response = await transport.request(method="GET", url=f"{config.resolved_endpoint()}/videos/{job_id}", headers=self._parser.bearer_headers(config.resolved_api_key()), timeout_seconds=config.timeout_seconds)
        parsed = self._parser.parse_json_response(response, provider=self.provider.value)
        return self._video_job_from_response(parsed, model=config.model)

    def _text_config_for(self, config: TextModelConfig | None) -> TextModelConfig:
        resolved = config or self._text_config
        if resolved is None:
            raise ProviderConfigurationError("OpenAIProvider requires a TextModelConfig.", provider=self.provider.value)
        return resolved

    def _image_config_for(self, config: ImageModelConfig | None) -> ImageModelConfig:
        resolved = config or self._image_config
        if resolved is None:
            raise ProviderConfigurationError("OpenAIProvider requires an ImageModelConfig.", provider=self.provider.value)
        return resolved

    def _video_config_for(self, config: VideoModelConfig | None) -> VideoModelConfig:
        resolved = config or self._video_config
        if resolved is None:
            raise ProviderConfigurationError("OpenAIProvider requires a VideoModelConfig.", provider=self.provider.value)
        return resolved

    def _build_text_config(self, *, model: str | None, config_options: Mapping[str, Any]) -> TextModelConfig | None:
        if model is None:
            return None
        return TextModelConfig(provider=self.provider, model=model, **dict(config_options))

    def _create_text_payload(self, config: TextModelConfig, prompt: str, system: str | None, metadata: Mapping[str, object] | None) -> dict[str, Any]:
        # Build a Responses API payload with prompt, instructions, tools, and controls.
        payload: dict[str, Any] = {"model": config.model, "input": self._create_input(config, prompt)}
        self._attach_instructions(payload, config, system)
        self._attach_sampling(payload, config)
        self._attach_tools(payload, config)
        self._attach_response_format(payload, config)
        self._attach_metadata(payload, config, metadata)
        self._attach_extra_body(payload, config)
        return payload

    def _create_input(self, config: TextModelConfig, prompt: str) -> str | list[Mapping[str, Any]]:
        # Preserve multi-turn Responses inputs when callers provide message history.
        if config.messages:
            return [dict(message) for message in config.messages] + [{"role": "user", "content": prompt}]
        return prompt

    def _attach_instructions(self, payload: dict[str, Any], config: TextModelConfig, system: str | None) -> None:
        # Responses API uses instructions for system/developer guidance.
        instructions = system or config.system
        if instructions:
            payload["instructions"] = instructions

    def _attach_sampling(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Add shared generation controls only when users configure them.
        if config.temperature is not None:
            payload["temperature"] = config.temperature
        if config.top_p is not None:
            payload["top_p"] = config.top_p
        if config.max_output_tokens is not None:
            payload["max_output_tokens"] = config.max_output_tokens

    def _attach_tools(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # OpenAI Responses supports built-in and function tools plus tool_choice.
        if config.tools:
            payload["tools"] = [dict(tool) for tool in config.tools]
        if config.tool_choice is not None:
            payload["tool_choice"] = config.tool_choice

    def _attach_response_format(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Structured response formats are nested under text.format for Responses.
        if config.response_format is not None:
            payload["text"] = {"format": dict(config.response_format)}

    def _attach_metadata(self, payload: dict[str, Any], config: TextModelConfig, metadata: Mapping[str, object] | None) -> None:
        # Merge runner-call metadata with static config metadata.
        combined = {**dict(config.metadata or {}), **dict(metadata or {})}
        if combined:
            payload["metadata"] = combined

    def _attach_extra_body(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Allow new OpenAI fields without changing the SDK surface each time.
        if config.extra_body:
            payload.update(dict(config.extra_body))

    def _create_image_payload(self, config: ImageModelConfig, prompt: str) -> dict[str, Any]:
        # Build image generation payloads including newer output controls.
        payload: dict[str, Any] = {"model": config.model, "prompt": prompt}
        for key in ("size", "quality", "response_format", "n", "background", "output_format", "output_compression"):
            value = getattr(config, key)
            if value is not None:
                payload[key] = value
        if config.extra_body:
            payload.update(dict(config.extra_body))
        return payload

    def _create_video_payload(self, config: VideoModelConfig, prompt: str) -> dict[str, Any]:
        # Build video job payloads while preserving future OpenAI video fields.
        payload: dict[str, Any] = {"model": config.model, "prompt": prompt}
        if config.size:
            payload["size"] = config.size
        if config.seconds:
            payload["seconds"] = config.seconds
        if config.extra_body:
            payload.update(dict(config.extra_body))
        return payload

    def _extract_response_text(self, parsed: Mapping[str, Any]) -> str:
        # Normalize output_text or text content from Responses API output items.
        output_text = parsed.get("output_text")
        if isinstance(output_text, str):
            return output_text
        chunks: list[str] = []
        output = parsed.get("output")
        if isinstance(output, list):
            for item in output:
                self._collect_output_text(chunks, item)
        if chunks:
            return "\n".join(chunks)
        if self._has_tool_calls(parsed):
            return ""
        raise ProviderResponseError("OpenAI response did not include output text.", provider=self.provider.value, response_excerpt=str(parsed))

    def _collect_output_text(self, chunks: list[str], item: object) -> None:
        # Collect text leaves from one Responses API output item.
        if not isinstance(item, dict):
            return
        content = item.get("content")
        if not isinstance(content, list):
            return
        for content_item in content:
            if isinstance(content_item, dict) and isinstance(content_item.get("text"), str):
                chunks.append(content_item["text"])

    def _has_tool_calls(self, parsed: Mapping[str, Any]) -> bool:
        output = parsed.get("output")
        if isinstance(output, list) and any(isinstance(item, dict) and item.get("type") in {"function_call", "tool_call"} for item in output):
            return True
        choices = parsed.get("choices")
        if not isinstance(choices, list):
            return False
        for choice in choices:
            message = choice.get("message") if isinstance(choice, dict) else None
            if isinstance(message, dict) and isinstance(message.get("tool_calls"), list):
                return True
        return False

    def _extract_images(self, parsed: Mapping[str, Any]) -> tuple[GeneratedImage, ...]:
        # Normalize OpenAI image data entries into SDK image objects.
        data = parsed.get("data")
        if not isinstance(data, list):
            raise ProviderResponseError("OpenAI image response did not include image data.", provider=self.provider.value, response_excerpt=str(parsed))
        return tuple(self._image_from_item(item) for item in data if isinstance(item, dict))

    def _image_from_item(self, item: Mapping[str, Any]) -> GeneratedImage:
        # Convert one provider image record into the SDK image dataclass.
        return GeneratedImage(url=item.get("url") if isinstance(item.get("url"), str) else None, b64_json=item.get("b64_json") if isinstance(item.get("b64_json"), str) else None, revised_prompt=item.get("revised_prompt") if isinstance(item.get("revised_prompt"), str) else None)

    def _video_job_from_response(self, parsed: Mapping[str, Any], *, model: str) -> VideoModelJob:
        # Convert one OpenAI video job response into the SDK job dataclass.
        job_id = parsed.get("id")
        status = parsed.get("status")
        if not isinstance(job_id, str) or not isinstance(status, str):
            raise ProviderResponseError("OpenAI video response did not include job id and status.", provider=self.provider.value, response_excerpt=str(parsed))
        return VideoModelJob(provider=self.provider, model=model, job_id=job_id, status=status, raw=parsed)


__all__ = [
    "OpenAIProvider",
]
