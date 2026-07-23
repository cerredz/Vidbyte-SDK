"""Context Protocol Header

Description:
    OpenAI-compatible chat-completions usage shape and cost formula.
Purpose:
    Parses prompt/completion/total usage for xAI, DeepSeek, GLM, MiniMax, and
    Kimi, including each provider's cached-input and reasoning detail variants.
Architecture:
    - ChatCompletionUsage: ProviderUsage bound to the compatible providers.
Relations:
    Registered in vidbyte/agents/pricing/base.py; extended by OpenRouterUsage.
Similar Files:
    - vidbyte/agents/pricing/openai.py
    - vidbyte/agents/pricing/openrouter.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.agents.pricing.base import ProviderUsage, usage_for
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.registries.pricing import ModelPricing


@usage_for(ModelProvider.XAI)
@usage_for(ModelProvider.DEEPSEEK)
@usage_for(ModelProvider.GLM)
@usage_for(ModelProvider.MINIMAX)
@usage_for(ModelProvider.KIMI)
@usage_for(ModelProvider.META)
@dataclass(frozen=True, slots=True)
class ChatCompletionUsage(ProviderUsage):
    """Chat-completions usage: cached input is a billed subset of prompt_tokens."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_usage_payload(cls, payload: Mapping[str, Any]) -> "ChatCompletionUsage | None":
        # Parses a chat-completions usage dict; None when no token fields exist.
        usage = cls(
            input_tokens=cls.coerce_int(payload.get("prompt_tokens")),
            output_tokens=cls.coerce_int(payload.get("completion_tokens")),
            total_tokens=cls.coerce_int(payload.get("total_tokens")),
            cached_input_tokens=cls._cached_input(payload),
            reasoning_tokens=cls._reasoning(payload),
            raw=payload,
        )
        if usage.input_tokens is None and usage.output_tokens is None and usage.total_tokens is None:
            return None
        return usage

    @classmethod
    def _cached_input(cls, payload: Mapping[str, Any]) -> int | None:
        # Reads cached input from OpenAI-style details, DeepSeek, or Kimi fields.
        details = payload.get("prompt_tokens_details")
        if isinstance(details, Mapping):
            cached = cls.coerce_int(details.get("cached_tokens"))
            if cached is not None:
                return cached
        cache_hit = cls.coerce_int(payload.get("prompt_cache_hit_tokens"))
        if cache_hit is not None:
            return cache_hit
        return cls.coerce_int(payload.get("cached_tokens"))

    @classmethod
    def _reasoning(cls, payload: Mapping[str, Any]) -> int | None:
        # Reads reasoning tokens from completion details when the provider reports them.
        details = payload.get("completion_tokens_details")
        if not isinstance(details, Mapping):
            return None
        return cls.coerce_int(details.get("reasoning_tokens"))

    def cost_usd(self, pricing: ModelPricing | None) -> float | None:
        # Prices uncached input at input rate and cached input at cache-read rate.
        return self.subset_billing_cost(pricing)


__all__ = ["ChatCompletionUsage"]
