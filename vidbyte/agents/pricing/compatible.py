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
        if all(count is None for count in (usage.input_tokens, usage.output_tokens, usage.total_tokens)):
            return None
        return usage

    @classmethod
    def _cached_input(cls, payload: Mapping[str, Any]) -> int | None:
        # Reads cached input from OpenAI-style details, DeepSeek, or Kimi fields,
        # returning the first source the provider actually reported.
        nested = cls.nested_int(payload, "prompt_tokens_details", "cached_tokens")
        if nested is not None:
            return nested
        cache_hit = cls.coerce_int(payload.get("prompt_cache_hit_tokens"))
        if cache_hit is not None:
            return cache_hit
        return cls.coerce_int(payload.get("cached_tokens"))

    @classmethod
    def _reasoning(cls, payload: Mapping[str, Any]) -> int | None:
        # Reads reasoning tokens from completion details when the provider reports them.
        return cls.nested_int(payload, "completion_tokens_details", "reasoning_tokens")

    def cost_usd(self, pricing: ModelPricing | None) -> float | None:
        # Prices uncached input at input rate and cached input at cache-read rate.
        return self.subset_billing_cost(pricing)


# xAI, DeepSeek, GLM, and MiniMax all speak the OpenAI chat-completions usage
# shape, so per the "one class per response shape" rule they share this class
# rather than each duplicating an identical parser. These aliases give every
# provider a discoverable, provider-named handle on the public surface.
XAIUsage = ChatCompletionUsage
DeepSeekUsage = ChatCompletionUsage
GLMUsage = ChatCompletionUsage
MiniMaxUsage = ChatCompletionUsage


__all__ = [
    "ChatCompletionUsage",
    "DeepSeekUsage",
    "GLMUsage",
    "MiniMaxUsage",
    "XAIUsage",
]
