"""Context Protocol Header

Description:
    Implements image generation using the OpenAI DALL-E 3 API.
Purpose:
    Provides an async-capable DALL-E 3 backend that wraps OpenAI's image
    generation endpoint using the existing HttpTransport.
Architecture:
    - OpenAIDalleBackend: Uses OPENAI_API_KEY env var, HttpTransport for HTTP.
    - Validates inputs, returns ImageGenResult with url and revised_prompt.
Relations:
    Related to vidbyte.lib.providers.image_gen.base and vidbyte.lib.http.transport.
"""

from __future__ import annotations

import asyncio
import json
import os

from vidbyte.lib.http.transport import HttpTransport
from vidbyte.lib.providers.image_gen.base import BaseImageGenBackend, ImageGenResult

DALLE_API_URL = "https://api.openai.com/v1/images/generations"
VALID_SIZES: frozenset[str] = frozenset({"1024x1024", "1792x1024", "1024x1792"})
VALID_STYLES: frozenset[str] = frozenset({"natural", "vivid"})


class OpenAIDalleBackend(BaseImageGenBackend):
    """OpenAI DALL-E 3 image generation backend."""

    def __init__(self) -> None:
        self._transport = HttpTransport()

    async def generate(self, prompt: str, size: str, style: str) -> ImageGenResult:
        if size not in VALID_SIZES:
            size = "1024x1024"
        if style not in VALID_STYLES:
            style = "natural"

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return ImageGenResult(url="", revised_prompt="OPENAI_API_KEY environment variable is not set.")

        headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, object] = {
            "model": "dall-e-3",
            "prompt": prompt,
            "size": size,
            "style": style,
            "n": 1,
        }

        response = await asyncio.to_thread(
            self._transport.request,
            method="POST",
            url=DALLE_API_URL,
            headers=headers,
            json_body=body,
        )

        if response.status_code not in (200, 201):
            return ImageGenResult(url="", revised_prompt=f"DALL-E API error ({response.status_code}): {response.body[:500]}")

        try:
            data = json.loads(response.body)
        except json.JSONDecodeError:
            return ImageGenResult(url="", revised_prompt="Failed to parse DALL-E API response.")

        image_data = (data.get("data") or [{}])[0]
        image_url = image_data.get("url", "")
        revised = image_data.get("revised_prompt")

        return ImageGenResult(url=image_url, revised_prompt=revised)

    async def is_available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))


__all__ = ["OpenAIDalleBackend"]
