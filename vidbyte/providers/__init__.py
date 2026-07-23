"""Context Protocol Header

Description:
    Central registration and factory registry for all supported SDK model provider adapters.
Purpose:
    Exposes a unified ModelProviders class factory to resolve and instantiate text, image, and video adapters dynamically.
Architecture:
    - ModelProviders: Static factory mappings.
Key Functions:
    - text: Resolves text adapters.
    - image: Resolves image adapters.
    - video: Resolves video adapters.
Relations:
    Used by ModalityDetector and runner modules to obtain provider adapters for executions.
Similar Files:
    - vidbyte/lib/agents/modality_detector.py
"""

from __future__ import annotations

from vidbyte.lib.config import AudioModelConfig, EmbeddingModelConfig, ImageModelConfig, TextModelConfig, VideoModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ProviderSelectionError
from vidbyte.providers.anthropic import AnthropicProvider
from vidbyte.providers.client import ProvidersClient
from vidbyte.providers.compatible import DeepSeekProvider, GLMProvider, KimiProvider, MiniMaxProvider, MistralProvider
from vidbyte.providers.elevenlabs import ElevenLabsProvider
from vidbyte.providers.gemini import GeminiProvider
from vidbyte.providers.openai import OpenAIProvider
from vidbyte.providers.openrouter import OpenRouterProvider
from vidbyte.providers.playai import PlayAIProvider
from vidbyte.providers.base import tool_spec_to_provider_schema
from vidbyte.providers.xai import XAIProvider


class ModelProviders:
    """Central factory for SDK provider adapters."""

    @staticmethod
    def text(config: TextModelConfig) -> OpenAIProvider | AnthropicProvider | GeminiProvider | XAIProvider | DeepSeekProvider | GLMProvider | MiniMaxProvider | KimiProvider | MistralProvider | OpenRouterProvider:
        # Return a text-capable adapter for the requested model provider.
        providers = {
            ModelProvider.OPENAI: OpenAIProvider,
            ModelProvider.ANTHROPIC: AnthropicProvider,
            ModelProvider.GEMINI: GeminiProvider,
            ModelProvider.XAI: XAIProvider,
            ModelProvider.DEEPSEEK: DeepSeekProvider,
            ModelProvider.GLM: GLMProvider,
            ModelProvider.MINIMAX: MiniMaxProvider,
            ModelProvider.KIMI: KimiProvider,
            ModelProvider.MISTRAL: MistralProvider,
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
    def audio(config: AudioModelConfig) -> OpenAIProvider | ElevenLabsProvider | PlayAIProvider:
        # Return an audio-capable adapter for TTS/STT provider APIs.
        providers = {
            ModelProvider.OPENAI: OpenAIProvider,
            ModelProvider.ELEVENLABS: ElevenLabsProvider,
            ModelProvider.PLAYAI: PlayAIProvider,
        }
        return ModelProviders._build_audio_provider(config, providers)

    @staticmethod
    def embedding(config: EmbeddingModelConfig) -> OpenAIProvider | GeminiProvider:
        # Return an embedding-capable adapter for vector embedding provider APIs.
        providers = {ModelProvider.OPENAI: OpenAIProvider, ModelProvider.GEMINI: GeminiProvider}
        return ModelProviders._build_embedding_provider(config, providers)

    @staticmethod
    def streaming_text(config: TextModelConfig) -> OpenAIProvider | AnthropicProvider:
        # Return a streaming-text-capable adapter for SSE-supporting providers.
        providers = {ModelProvider.OPENAI: OpenAIProvider, ModelProvider.ANTHROPIC: AnthropicProvider}
        return ModelProviders._build_text_provider(config, providers)

    @staticmethod
    def _build_text_provider(config: TextModelConfig, providers: dict[ModelProvider, type]):
        # Resolve and construct the text provider adapter.
        return ModelProviders._build_provider(config.normalized_provider(), providers, capability="text", text_config=config)

    @staticmethod
    def _build_image_provider(config: ImageModelConfig, providers: dict[ModelProvider, type]):
        # Resolve and construct the image provider adapter.
        return ModelProviders._build_provider(config.normalized_provider(), providers, capability="image", image_config=config)

    @staticmethod
    def _build_video_provider(config: VideoModelConfig, providers: dict[ModelProvider, type]):
        # Resolve and construct the video provider adapter.
        return ModelProviders._build_provider(config.normalized_provider(), providers, capability="video", video_config=config)

    @staticmethod
    def _build_audio_provider(config: AudioModelConfig, providers: dict[ModelProvider, type]):
        # Resolve and construct the audio provider adapter.
        return ModelProviders._build_provider(config.normalized_provider(), providers, capability="audio", audio_config=config)

    @staticmethod
    def _build_embedding_provider(config: EmbeddingModelConfig, providers: dict[ModelProvider, type]):
        # Resolve and construct the embedding provider adapter.
        return ModelProviders._build_provider(config.normalized_provider(), providers, capability="embedding", embedding_config=config)

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
    "ElevenLabsProvider",
    "GLMProvider",
    "GeminiProvider",
    "KimiProvider",
    "MiniMaxProvider",
    "MistralProvider",
    "ModelProviders",
    "OpenAIProvider",
    "OpenRouterProvider",
    "PlayAIProvider",
    "ProvidersClient",
    "XAIProvider",
    "get_image_provider",
    "get_text_provider",
    "get_video_provider",
    "tool_spec_to_provider_schema",
]

