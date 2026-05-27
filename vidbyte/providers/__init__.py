# Context Protocol Header
# Description: Provider namespace client factory and loader.
# Purpose: Serves as the central registry to build text, image, and video model provider adapters.
# Architecture: Static registry pattern mapping ModelProvider enums to specific classes.
# Key Functions: ModelProviders, get_text_provider, get_image_provider, get_video_provider.
# Codebase Relation: Connects runners to specific REST API adapter instances.
# Similar Files: vidbyte/lib/runners/text.py

from __future__ import annotations

from vidbyte.lib.config import ImageModelConfig, TextModelConfig, VideoModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ProviderSelectionError
from vidbyte.providers.anthropic import AnthropicProvider
from vidbyte.providers.client import ProvidersClient
from vidbyte.providers.compatible import DeepSeekProvider, GLMProvider, MiniMaxProvider
from vidbyte.providers.gemini import GeminiProvider
from vidbyte.providers.openai import OpenAIProvider
from vidbyte.providers.base import tool_spec_to_provider_schema
from vidbyte.providers.xai import XAIProvider
from vidbyte.providers.openrouter import OpenRouterProvider


class ModelProviders:
    """Central factory for SDK provider adapters."""

    @staticmethod
    def text(config: TextModelConfig) -> OpenAIProvider | AnthropicProvider | GeminiProvider | XAIProvider | DeepSeekProvider | GLMProvider | MiniMaxProvider | OpenRouterProvider:
        # Return a text-capable adapter for the requested model provider.
        providers = {
            ModelProvider.OPENAI: OpenAIProvider,
            ModelProvider.ANTHROPIC: AnthropicProvider,
            ModelProvider.GEMINI: GeminiProvider,
            ModelProvider.XAI: XAIProvider,
            ModelProvider.DEEPSEEK: DeepSeekProvider,
            ModelProvider.GLM: GLMProvider,
            ModelProvider.MINIMAX: MiniMaxProvider,
            ModelProvider.OPENROUTER: OpenRouterProvider,
        }
        return ModelProviders._build_text_provider(config, providers)

    @staticmethod
    def image(config: ImageModelConfig) -> OpenAIProvider | XAIProvider:
        # Return an image-capable adapter for providers with public image APIs.
        providers = {ModelProvider.OPENAI: OpenAIProvider, ModelProvider.XAI: XAIProvider}
        return ModelProviders._build_image_provider(config, providers)

    @staticmethod
    def video(config: VideoModelConfig) -> OpenAIProvider:
        # Return a video-capable adapter for providers with public video job APIs.
        providers = {ModelProvider.OPENAI: OpenAIProvider}
        return ModelProviders._build_video_provider(config, providers)

    @staticmethod
    def _build_text_provider(config: TextModelConfig, providers: dict[ModelProvider, type]):
        return ModelProviders._build_provider(config.normalized_provider(), providers, capability="text", text_config=config)

    @staticmethod
    def _build_image_provider(config: ImageModelConfig, providers: dict[ModelProvider, type]):
        return ModelProviders._build_provider(config.normalized_provider(), providers, capability="image", image_config=config)

    @staticmethod
    def _build_video_provider(config: VideoModelConfig, providers: dict[ModelProvider, type]):
        return ModelProviders._build_provider(config.normalized_provider(), providers, capability="video", video_config=config)

    @staticmethod
    def _build_provider(provider: ModelProvider, providers: dict[ModelProvider, type], *, capability: str, **kwargs: object):
        # Instantiate provider adapters through one audited selection path.
        provider_class = providers.get(provider)
        if provider_class is None:
            raise ProviderSelectionError(f"Unsupported {capability} provider: {provider.value}", details={"provider": provider.value, "capability": capability})
        return provider_class(**kwargs)


def get_text_provider(config: TextModelConfig):
    # Back-compatible wrapper around the central provider registry.
    return ModelProviders.text(config)


def get_image_provider(config: ImageModelConfig):
    # Back-compatible wrapper around the central provider registry.
    return ModelProviders.image(config)


def get_video_provider(config: VideoModelConfig):
    # Back-compatible wrapper around the central provider registry.
    return ModelProviders.video(config)


__all__ = [
    "AnthropicProvider",
    "DeepSeekProvider",
    "GLMProvider",
    "GeminiProvider",
    "MiniMaxProvider",
    "ModelProviders",
    "OpenAIProvider",
    "ProvidersClient",
    "OpenRouterProvider",
    "XAIProvider",
    "get_image_provider",
    "get_text_provider",
    "get_video_provider",
    "tool_spec_to_provider_schema",
]
