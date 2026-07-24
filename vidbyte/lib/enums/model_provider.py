"""Context Protocol Header

Description:
    Supported SDK model providers enumeration.
Purpose:
    Exposes supported provider string literals as a strongly-typed Enum at the SDK boundary.
Architecture:
    - ModelProvider: Enum mapping provider keys, and resolving each provider's
      token-usage parser class through one lazily-built map.
Key Functions:
    - ModelProvider.usage_class: Resolves this provider's ProviderUsage subclass.
Relations:
    Extensively used by ProviderModelRegistry, client configuration classes, and provider factories.
    UsageTracker resolves usage parsers through ModelProvider.usage_class.
Similar Files:
    - vidbyte/lib/enums/model_modality.py
"""

from __future__ import annotations

from enum import Enum
from functools import cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vidbyte.agents.pricing import ProviderUsage


class ModelProvider(str, Enum):
    """Supported SDK model providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    XAI = "xai"
    DEEPSEEK = "deepseek"
    GLM = "glm"
    MINIMAX = "minimax"
    KIMI = "kimi"
    META = "meta"
    MISTRAL = "mistral"
    OPENROUTER = "openrouter"
    ELEVENLABS = "elevenlabs"
    PLAYAI = "playai"

    def usage_class(self) -> type[ProviderUsage] | None:
        # Resolves this provider's token-usage parser class, or None when the
        # provider reports no billable usage (e.g. audio/image-only providers).
        return _usage_class_map().get(self)


@cache
def _usage_class_map() -> dict[ModelProvider, type[ProviderUsage]]:
    # Builds the provider -> ProviderUsage map once, on first resolution. The
    # pricing import is deferred to call time so this low-level enum module never
    # imports the higher-level agents.pricing package at load, avoiding both an
    # import cycle and a layering inversion. Compatible providers (xAI, DeepSeek,
    # GLM, MiniMax, Kimi, Meta, Mistral) share the chat-completions usage shape.
    from vidbyte.agents.pricing import AnthropicUsage, ChatCompletionUsage, GeminiUsage, OpenAIUsage, OpenRouterUsage

    return {
        ModelProvider.OPENAI: OpenAIUsage,
        ModelProvider.ANTHROPIC: AnthropicUsage,
        ModelProvider.GEMINI: GeminiUsage,
        ModelProvider.XAI: ChatCompletionUsage,
        ModelProvider.DEEPSEEK: ChatCompletionUsage,
        ModelProvider.GLM: ChatCompletionUsage,
        ModelProvider.MINIMAX: ChatCompletionUsage,
        ModelProvider.KIMI: ChatCompletionUsage,
        ModelProvider.META: ChatCompletionUsage,
        ModelProvider.MISTRAL: ChatCompletionUsage,
        ModelProvider.OPENROUTER: OpenRouterUsage,
    }


__all__ = [
    "ModelProvider",
]

