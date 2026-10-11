"""Context Protocol Header

Description:
    Anthropic Messages API usage shape and cost formula.
Purpose:
    Parses Anthropic's input/output usage plus cache creation/read buckets, which
    are additive billable buckets rather than subsets of the reported input.
Architecture:
    - AnthropicUsage: ProviderUsage bound to ModelProvider.ANTHROPIC.
Key Functions:
    - cached_input_tokens: Maps cache_read_input_tokens onto the shared accessor.
    - total_prompt_tokens: Sums all three input-side buckets (Anthropic's
      input_tokens alone excludes both cache buckets).
    - _over_threshold: Compares that full prompt, not input_tokens, with a
      model's prompt-length tier (Claude Haiku 5.5's 100K tier).
Relations:
    Registered in vidbyte/agents/pricing/base.py; rates from PROVIDER_PRICING.
Similar Files:
    - vidbyte/agents/pricing/openai.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.agents.pricing.base import ProviderUsage
from vidbyte.lib.registries.pricing import ModelPricing


@dataclass(frozen=True, slots=True)
class AnthropicUsage(ProviderUsage):
    """Anthropic Messages usage: cache write/read tokens bill on top of input."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_usage_payload(cls, payload: Mapping[str, Any]) -> "AnthropicUsage | None":
        # Parses an Anthropic Messages usage dict; None when no token fields exist.
        usage = cls(
            input_tokens=cls.coerce_int(payload.get("input_tokens")),
            output_tokens=cls.coerce_int(payload.get("output_tokens")),
            cache_creation_input_tokens=cls.coerce_int(payload.get("cache_creation_input_tokens")),
            cache_read_input_tokens=cls.coerce_int(payload.get("cache_read_input_tokens")),
            raw=payload,
        )
        if usage.total_tokens is None:
            return None
        return usage

    @property
    def total_tokens(self) -> int | None:
        # Sums all four additive buckets; None when the payload had none of them.
        parts = (self.input_tokens, self.output_tokens, self.cache_creation_input_tokens, self.cache_read_input_tokens)
        if all(part is None for part in parts):
            return None
        return sum(part or 0 for part in parts)

    @property
    def cached_input_tokens(self) -> int | None:
        # Maps Anthropic's cache-read bucket onto the shared cached-input accessor.
        return self.cache_read_input_tokens

    @property
    def total_prompt_tokens(self) -> int | None:
        # Anthropic's input_tokens excludes both cache buckets (additive billing),
        # so the prompt total is all three buckets combined.
        parts = (self.input_tokens, self.cache_creation_input_tokens, self.cache_read_input_tokens)
        if all(part is None for part in parts):
            return None
        return sum(part or 0 for part in parts)

    def _over_threshold(self, pricing: ModelPricing) -> bool:
        # True when the whole prompt crosses the prompt-length tier.
        # @intent anthropic-tier-counts-cached-prompt
        # Anthropic prices Haiku 5.5 by a prompt length that counts "all
        # of its input tokens, including cache reads and cache writes",
        # while input_tokens here excludes both, so a cache-heavy prompt
        # would otherwise bill at the cheaper tier.
        prompt_tokens = self.total_prompt_tokens
        if pricing.threshold_tokens is None or prompt_tokens is None:
            return False
        if pricing.threshold_inclusive:
            return prompt_tokens >= pricing.threshold_tokens
        return prompt_tokens > pricing.threshold_tokens

    def cost_usd(self, pricing: ModelPricing | None) -> float | None:
        # Prices input, cache-write, cache-read, and output as separate buckets.
        if pricing is None or self.total_tokens is None:
            return None
        # @intent anthropic-cache-rates-follow-shared-pricing
        # A 0.0 rate is a priced free bucket (only None falls back), and both cache
        # rates scale with the active input tier, exactly as effective_rates prices
        # cache reads for every other provider.
        input_rate, output_rate, cache_read_rate = self.effective_rates(pricing)
        cache_write_rate = pricing.cache_write_per_million
        if cache_write_rate is None:
            cache_write_rate = input_rate
        # @intent free-base-rate-never-divides
        # A 0.0 base input rate (a free model) leaves the tier ratio undefined, so its cache rate applies unscaled.
        elif pricing.input_per_million != 0.0:
            cache_write_rate = cache_write_rate * (input_rate / pricing.input_per_million)
        return (
            (self.input_tokens or 0) * input_rate
            + (self.cache_creation_input_tokens or 0) * cache_write_rate
            + (self.cache_read_input_tokens or 0) * cache_read_rate
            + (self.output_tokens or 0) * output_rate
        ) / 1_000_000


__all__ = ["AnthropicUsage"]
