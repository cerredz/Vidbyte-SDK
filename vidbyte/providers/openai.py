from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, Mapping

from vidbyte.lib.config import AudioModelConfig, EmbeddingModelConfig, ImageModelConfig, TextModelConfig, VideoModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ProviderConfigurationError, ProviderResponseError
from vidbyte.lib.http import HttpResponseParser, HttpTransport
from vidbyte.lib.runners.types import AudioModelResponse, EmbeddingResponse, GeneratedImage, ImageModelResponse, TextModelResponse, VideoModelJob


class OpenAIProvider:
    provider = ModelProvider.OPENAI

    def __init__(self, *, text_config: TextModelConfig | None = None, image_config: ImageModelConfig | None = None, video_config: VideoModelConfig | None = None, audio_config: AudioModelConfig | None = None, embedding_config: EmbeddingModelConfig | None = None, model: str | None = None, response_parser: HttpResponseParser | None = None, **config_options: Any) -> None:
        # Keep response parsing injectable for tests and alternate transports.
        self._text_config = text_config or self._build_text_config(model=model, config_options=config_options)
        self._image_config = image_config
        self._video_config = video_config
        self._audio_config = audio_config
        self._embedding_config = embedding_config
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

    def run_tts(self, *, text: str, transport: HttpTransport, config: AudioModelConfig | None = None) -> AudioModelResponse:
        # POST to /audio/speech and return raw audio bytes from the binary response.
        config = self._audio_config_for(config)
        payload: dict[str, Any] = {"model": config.model, "input": text, "voice": config.voice or "alloy", "response_format": config.response_format or "mp3"}
        if config.speed is not None:
            payload["speed"] = config.speed
        if config.extra_body:
            payload.update(dict(config.extra_body))
        response = transport.request_bytes(method="POST", url=f"{config.resolved_endpoint()}/audio/speech", headers=self._parser.bearer_headers(config.resolved_api_key()), json_body=payload, timeout_seconds=config.timeout_seconds)
        if not response.raw_bytes:
            raise ProviderResponseError("OpenAI TTS returned empty audio bytes.", provider=self.provider.value)
        return AudioModelResponse(provider=self.provider, model=config.model, audio_bytes=response.raw_bytes, transcript=None, raw={})

    def run_stt(self, *, audio: bytes, format: str, transport: HttpTransport, config: AudioModelConfig | None = None) -> AudioModelResponse:
        # Upload audio via multipart to /audio/transcriptions and extract the transcript string.
        config = self._audio_config_for(config)
        fields: dict[str, str] = {"model": config.model}
        if config.language:
            fields["language"] = config.language
        response = transport.upload_multipart(url=f"{config.resolved_endpoint()}/audio/transcriptions", headers=self._parser.bearer_headers(config.resolved_api_key()), fields=fields, file_field="file", file_bytes=audio, file_name=f"audio.{format}", file_content_type=f"audio/{format}", timeout_seconds=config.timeout_seconds)
        parsed = self._parser.parse_json_response(response, provider=self.provider.value)
        transcript = parsed.get("text")
        if not isinstance(transcript, str):
            raise ProviderResponseError("OpenAI STT response did not include a text field.", provider=self.provider.value, response_excerpt=str(parsed))
        return AudioModelResponse(provider=self.provider, model=config.model, audio_bytes=None, transcript=transcript, raw=parsed)

    def run_embedding(self, *, texts: list[str], transport: HttpTransport, config: EmbeddingModelConfig | None = None) -> EmbeddingResponse:
        # POST to /embeddings and return one float vector per input text, sorted by index.
        config = self._embedding_config_for(config)
        payload: dict[str, Any] = {"model": config.model, "input": texts}
        if config.dimensions is not None:
            payload["dimensions"] = config.dimensions
        if config.extra_body:
            payload.update(dict(config.extra_body))
        response = transport.request(method="POST", url=f"{config.resolved_endpoint()}/embeddings", headers=self._parser.bearer_headers(config.resolved_api_key()), json_body=payload, timeout_seconds=config.timeout_seconds)
        parsed = self._parser.parse_json_response(response, provider=self.provider.value)
        embeddings = self._extract_embeddings(parsed, expected_count=len(texts))
        return EmbeddingResponse(provider=self.provider, model=config.model, embeddings=embeddings, raw=parsed, usage=parsed.get("usage") if isinstance(parsed.get("usage"), dict) else None)

    def stream_text(self, *, prompt: str, system: str | None, metadata: Mapping[str, object] | None, transport: HttpTransport, config: TextModelConfig | None = None) -> Iterator[str]:
        # POST to /responses with stream=True and yield text deltas from SSE events.
        config = self._text_config_for(config)
        payload = self._create_text_payload(config, prompt, system, metadata)
        payload["stream"] = True
        for raw_line in transport.stream_request(method="POST", url=f"{config.resolved_endpoint()}/responses", headers=self._parser.bearer_headers(config.resolved_api_key()), json_body=payload, timeout_seconds=config.timeout_seconds):
            chunk = self._extract_stream_delta(raw_line)
            if chunk is not None:
                yield chunk

    def _audio_config_for(self, config: AudioModelConfig | None) -> AudioModelConfig:
        # Resolve audio config from call argument or stored instance config.
        resolved = config or self._audio_config
        if resolved is None:
            raise ProviderConfigurationError("OpenAIProvider requires an AudioModelConfig.", provider=self.provider.value)
        return resolved

    def _embedding_config_for(self, config: EmbeddingModelConfig | None) -> EmbeddingModelConfig:
        # Resolve embedding config from call argument or stored instance config.
        resolved = config or self._embedding_config
        if resolved is None:
            raise ProviderConfigurationError("OpenAIProvider requires an EmbeddingModelConfig.", provider=self.provider.value)
        return resolved

    def _extract_embeddings(self, parsed: Mapping[str, Any], *, expected_count: int) -> tuple[tuple[float, ...], ...]:
        # Sort data items by index and convert each embedding list to an immutable tuple.
        data = parsed.get("data")
        if not isinstance(data, list):
            raise ProviderResponseError("OpenAI embeddings response missing data list.", provider=self.provider.value, response_excerpt=str(parsed))
        if len(data) != expected_count:
            raise ProviderResponseError(f"OpenAI returned {len(data)} embeddings but {expected_count} were requested.", provider=self.provider.value, response_excerpt=str(parsed))
        sorted_items = sorted(data, key=lambda item: item.get("index", 0) if isinstance(item, dict) else 0)
        return tuple(tuple(float(v) for v in item["embedding"]) for item in sorted_items if isinstance(item, dict) and isinstance(item.get("embedding"), list))

    def _extract_stream_delta(self, raw_line: str) -> str | None:
        # Parse one SSE JSON line and return the text delta, or None for non-delta events.
        try:
            event = json.loads(raw_line)
        except (json.JSONDecodeError, ValueError):
            return None
        event_type = event.get("type", "")
        if event_type == "response.text.delta":
            delta = event.get("delta")
            return delta if isinstance(delta, str) else None
        if event_type in ("response.output_text.delta",):
            delta = event.get("delta")
            return delta if isinstance(delta, str) else None
        return None

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
