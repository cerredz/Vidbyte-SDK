from __future__ import annotations

from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ProviderSelectionError
from vidbyte.providers.anthropic import AnthropicProvider
from vidbyte.providers.client import ProvidersClient
from vidbyte.providers.compatible import DeepSeekProvider, GLMProvider, MiniMaxProvider
from vidbyte.providers.gemini import GeminiProvider
from vidbyte.providers.openai import OpenAIProvider
from vidbyte.providers.xai import XAIProvider


class ModelProviders:
    """Central factory for SDK provider adapters."""

    @staticmethod
    def text(provider: ModelProvider) -> OpenAIProvider | AnthropicProvider | GeminiProvider | XAIProvider | DeepSeekProvider | GLMProvider | MiniMaxProvider:
        # Return a text-capable adapter for the requested model provider.
        providers = {
            ModelProvider.OPENAI: OpenAIProvider,
            ModelProvider.ANTHROPIC: AnthropicProvider,
            ModelProvider.GEMINI: GeminiProvider,
            ModelProvider.XAI: XAIProvider,
            ModelProvider.DEEPSEEK: DeepSeekProvider,
            ModelProvider.GLM: GLMProvider,
            ModelProvider.MINIMAX: MiniMaxProvider,
        }
        return ModelProviders._build_provider(provider, providers, capability="text")

    @staticmethod
    def image(provider: ModelProvider) -> OpenAIProvider | XAIProvider:
        # Return an image-capable adapter for providers with public image APIs.
        providers = {ModelProvider.OPENAI: OpenAIProvider, ModelProvider.XAI: XAIProvider}
        return ModelProviders._build_provider(provider, providers, capability="image")

    @staticmethod
    def video(provider: ModelProvider) -> OpenAIProvider:
        # Return a video-capable adapter for providers with public video job APIs.
        providers = {ModelProvider.OPENAI: OpenAIProvider}
        return ModelProviders._build_provider(provider, providers, capability="video")

    @staticmethod
    def _build_provider(provider: ModelProvider, providers: dict[ModelProvider, type], *, capability: str):
        # Instantiate provider adapters through one audited selection path.
        provider_class = providers.get(provider)
        if provider_class is None:
            raise ProviderSelectionError(f"Unsupported {capability} provider: {provider.value}", details={"provider": provider.value, "capability": capability})
        return provider_class()


def get_text_provider(provider: ModelProvider):
    # Back-compatible wrapper around the central provider registry.
    return ModelProviders.text(provider)


def get_image_provider(provider: ModelProvider):
    # Back-compatible wrapper around the central provider registry.
    return ModelProviders.image(provider)


def get_video_provider(provider: ModelProvider):
    # Back-compatible wrapper around the central provider registry.
    return ModelProviders.video(provider)


__all__ = [
    "AnthropicProvider",
    "DeepSeekProvider",
    "GLMProvider",
    "GeminiProvider",
    "MiniMaxProvider",
    "ModelProviders",
    "OpenAIProvider",
    "ProvidersClient",
    "XAIProvider",
    "get_image_provider",
    "get_text_provider",
    "get_video_provider",
]
