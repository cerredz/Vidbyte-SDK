"""Context Protocol Header

Description:
    Anthropic Messages API usage shape and cost formula.
Purpose:
    Parses Anthropic's input/output usage plus cache creation/read buckets, which
    are additive billable buckets rather than subsets of the reported input.
Architecture:
    - AnthropicUsage: ProviderUsage bound to ModelProvider.ANTHROPIC.
Relations:
    Registered in vidbyte/agents/pricing/base.py; rates from PROVIDER_PRICING.
Similar Files:
    - vidbyte/agents/pricing/openai.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.agents.pricing.base import ProviderUsage, usage_for
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.registries.pricing import ModelPricing


@usage_for(ModelProvider.ANTHROPIC)
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

    def cost_usd(self, pricing: ModelPricing | None) -> float | None:
        # Prices input, cache-write, cache-read, and output as separate buckets.
        if pricing is None or self.total_tokens is None:
            return None
        input_rate, output_rate, _ = self.effective_rates(pricing)
        cache_write_rate = pricing.cache_write_per_million or input_rate
        cache_read_rate = pricing.cache_read_per_million or input_rate
        return (
            (self.input_tokens or 0) * input_rate
            + (self.cache_creation_input_tokens or 0) * cache_write_rate
            + (self.cache_read_input_tokens or 0) * cache_read_rate
            + (self.output_tokens or 0) * output_rate
        ) / 1_000_000


__all__ = ["AnthropicUsage"]
