from __future__ import annotations

from vidbyte.lib.config import ModelProvider
from vidbyte.providers.client import ProvidersClient
from vidbyte.providers.openai import OpenAIProvider
from vidbyte.providers.anthropic import AnthropicProvider
from vidbyte.providers.gemini import GeminiProvider
from vidbyte.providers.xai import XAIProvider


def get_text_provider(provider: ModelProvider) -> OpenAIProvider | AnthropicProvider | GeminiProvider | XAIProvider:
    if provider == ModelProvider.OPENAI:
        return OpenAIProvider()
    if provider == ModelProvider.ANTHROPIC:
        return AnthropicProvider()
    if provider == ModelProvider.GEMINI:
        return GeminiProvider()
    if provider == ModelProvider.XAI:
        return XAIProvider()
    raise ValueError(f"Unsupported text provider: {provider.value}")


def get_image_provider(provider: ModelProvider) -> OpenAIProvider | XAIProvider:
    if provider == ModelProvider.OPENAI:
        return OpenAIProvider()
    if provider == ModelProvider.XAI:
        return XAIProvider()
    raise ValueError(f"Unsupported image provider: {provider.value}")


def get_video_provider(provider: ModelProvider) -> OpenAIProvider:
    if provider == ModelProvider.OPENAI:
        return OpenAIProvider()
    raise ValueError(f"Unsupported video provider: {provider.value}")

__all__ = [
    "AnthropicProvider",
    "GeminiProvider",
    "OpenAIProvider",
    "ProvidersClient",
    "XAIProvider",
    "get_image_provider",
    "get_text_provider",
    "get_video_provider",
]
