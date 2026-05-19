from __future__ import annotations

from typing import Any, Mapping

from vidbyte.lib.config import ImageModelConfig, ModelProvider, TextModelConfig, VideoModelConfig
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http import HttpTransport
from vidbyte.lib.runners.types import GeneratedImage, ImageModelResponse, TextModelResponse, VideoModelJob
from vidbyte.providers.base import bearer_headers, parse_json_response


class OpenAIProvider:
    provider = ModelProvider.OPENAI

    def run_text(
        self,
        *,
        config: TextModelConfig,
        prompt: str,
        system: str | None,
        metadata: Mapping[str, object] | None,
        transport: HttpTransport,
    ) -> TextModelResponse:
        payload: dict[str, Any] = {
            "model": config.model,
            "input": prompt,
        }
        instructions = system or config.system
        if instructions:
            payload["instructions"] = instructions
        if config.temperature is not None:
            payload["temperature"] = config.temperature
        if config.max_output_tokens is not None:
            payload["max_output_tokens"] = config.max_output_tokens
        if config.response_format is not None:
            payload["text"] = {"format": config.response_format}
        if metadata:
            payload["metadata"] = dict(metadata)

        response = transport.request(
            method="POST",
            url=f"{config.resolved_endpoint()}/responses",
            headers=bearer_headers(config.resolved_api_key()),
            json_body=payload,
            timeout_seconds=config.timeout_seconds,
        )
        parsed = parse_json_response(response, provider=self.provider.value)
        return TextModelResponse(
            provider=self.provider,
            model=config.model,
            text=_extract_response_text(parsed),
            raw=parsed,
            usage=parsed.get("usage") if isinstance(parsed.get("usage"), dict) else None,
        )

    def run_image(
        self,
        *,
        config: ImageModelConfig,
        prompt: str,
        transport: HttpTransport,
    ) -> ImageModelResponse:
        payload: dict[str, Any] = {"model": config.model, "prompt": prompt}
        if config.size:
            payload["size"] = config.size
        if config.quality:
            payload["quality"] = config.quality
        if config.response_format:
            payload["response_format"] = config.response_format

        response = transport.request(
            method="POST",
            url=f"{config.resolved_endpoint()}/images/generations",
            headers=bearer_headers(config.resolved_api_key()),
            json_body=payload,
            timeout_seconds=config.timeout_seconds,
        )
        parsed = parse_json_response(response, provider=self.provider.value)
        return ImageModelResponse(
            provider=self.provider,
            model=config.model,
            images=_extract_images(parsed),
            raw=parsed,
        )

    def create_video(
        self,
        *,
        config: VideoModelConfig,
        prompt: str,
        transport: HttpTransport,
    ) -> VideoModelJob:
        payload: dict[str, Any] = {"model": config.model, "prompt": prompt}
        if config.size:
            payload["size"] = config.size
        if config.seconds:
            payload["seconds"] = config.seconds

        response = transport.request(
            method="POST",
            url=f"{config.resolved_endpoint()}/videos",
            headers=bearer_headers(config.resolved_api_key()),
            json_body=payload,
            timeout_seconds=config.timeout_seconds,
        )
        parsed = parse_json_response(response, provider=self.provider.value)
        return _video_job_from_response(parsed, model=config.model)

    def get_video_status(
        self,
        *,
        config: VideoModelConfig,
        job_id: str,
        transport: HttpTransport,
    ) -> VideoModelJob:
        response = transport.request(
            method="GET",
            url=f"{config.resolved_endpoint()}/videos/{job_id}",
            headers=bearer_headers(config.resolved_api_key()),
            timeout_seconds=config.timeout_seconds,
        )
        parsed = parse_json_response(response, provider=self.provider.value)
        return _video_job_from_response(parsed, model=config.model)


def _extract_response_text(parsed: Mapping[str, Any]) -> str:
    output_text = parsed.get("output_text")
    if isinstance(output_text, str):
        return output_text

    chunks: list[str] = []
    output = parsed.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for content_item in content:
                if isinstance(content_item, dict):
                    text = content_item.get("text")
                    if isinstance(text, str):
                        chunks.append(text)

    if chunks:
        return "\n".join(chunks)

    raise ProviderRequestError(
        "OpenAI response did not include output text.",
        provider=ModelProvider.OPENAI.value,
        response_excerpt=str(parsed),
    )


def _extract_images(parsed: Mapping[str, Any]) -> tuple[GeneratedImage, ...]:
    data = parsed.get("data")
    if not isinstance(data, list):
        raise ProviderRequestError(
            "OpenAI image response did not include image data.",
            provider=ModelProvider.OPENAI.value,
            response_excerpt=str(parsed),
        )
    images: list[GeneratedImage] = []
    for item in data:
        if isinstance(item, dict):
            images.append(
                GeneratedImage(
                    url=item.get("url") if isinstance(item.get("url"), str) else None,
                    b64_json=item.get("b64_json") if isinstance(item.get("b64_json"), str) else None,
                    revised_prompt=(
                        item.get("revised_prompt")
                        if isinstance(item.get("revised_prompt"), str)
                        else None
                    ),
                )
            )
    return tuple(images)


def _video_job_from_response(parsed: Mapping[str, Any], *, model: str) -> VideoModelJob:
    job_id = parsed.get("id")
    status = parsed.get("status")
    if not isinstance(job_id, str) or not isinstance(status, str):
        raise ProviderRequestError(
            "OpenAI video response did not include job id and status.",
            provider=ModelProvider.OPENAI.value,
            response_excerpt=str(parsed),
        )
    return VideoModelJob(
        provider=ModelProvider.OPENAI,
        model=model,
        job_id=job_id,
        status=status,
        raw=parsed,
    )
