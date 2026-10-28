"""Context Protocol Header

Description:
    OpenAI Responses API usage shape and cost formula.
Purpose:
    Parses OpenAI's input/output/total usage with cached-input, cache-write and
    reasoning detail, pricing cached input as a discounted subset of input
    tokens and cache writes as a subset billed at the cache-write rate.
Architecture:
    - OpenAIUsage: ProviderUsage bound to ModelProvider.OPENAI.
Relations:
    Registered in vidbyte/agents/pricing/base.py; rates from PROVIDER_PRICING.
Similar Files:
    - vidbyte/agents/pricing/compatible.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.agents.pricing.base import ProviderUsage
from vidbyte.lib.registries.pricing import ModelPricing


@dataclass(frozen=True, slots=True)
class OpenAIUsage(ProviderUsage):
    """OpenAI Responses usage: cached input is a billed subset of input_tokens."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)
    cache_write_input_tokens: int | None = None

    @classmethod
    def from_usage_payload(cls, payload: Mapping[str, Any]) -> "OpenAIUsage | None":
        # Parses an OpenAI Responses usage dict; None when no token fields exist.
        usage = cls(
            input_tokens=cls.coerce_int(payload.get("input_tokens")),
            output_tokens=cls.coerce_int(payload.get("output_tokens")),
            total_tokens=cls.coerce_int(payload.get("total_tokens")),
            cached_input_tokens=cls.nested_int(payload, "input_tokens_details", "cached_tokens"),
            reasoning_tokens=cls.nested_int(payload, "output_tokens_details", "reasoning_tokens"),
            raw=payload,
            # Responses usage nests the count; Codex's translator keeps
            # it top-level.
            cache_write_input_tokens=cls._cache_write_count(payload),
        )
        if all(count is None for count in (usage.input_tokens, usage.output_tokens, usage.total_tokens)):
            return None
        return usage

    def cost_usd(self, pricing: ModelPricing | None) -> float | None:
        # Prices uncached input at input rate, cached input at the
        # cache-read rate, and cache writes at the cache-write rate.
        # @intent openai-cache-writes-bill-at-the-cache-write-rate
        # OpenAI reports cache writes inside input_tokens and bills them
        # at the cache-write rate (1.25x input on gpt-5.6 and gpt-6), so
        # the writes within the uncached input pay the gap between that
        # rate and the input rate, both scaled by the call's
        # long-context tier. This is the formula Vidbyte's gateway
        # applied as its own surcharge.
        cost = self.subset_billing_cost(pricing)
        if cost is None or pricing is None or pricing.cache_write_per_million is None or pricing.input_per_million <= 0:
            return cost
        writes = min(self.cache_write_input_tokens or 0, self.uncached_input_tokens or 0)
        if writes <= 0:
            return cost
        input_rate, _, _ = self.effective_rates(pricing)
        write_rate = pricing.cache_write_per_million * input_rate / pricing.input_per_million
        return cost + writes * (write_rate - input_rate) / 1_000_000

    @classmethod
    def _cache_write_count(cls, payload: Mapping[str, Any]) -> int | None:
        # Returns the cache-write token count from either usage shape,
        # else None.
        nested = cls.nested_int(payload, "input_tokens_details", "cache_write_tokens")
        return nested if nested is not None else cls.coerce_int(payload.get("cache_write_input_tokens"))


__all__ = ["OpenAIUsage"]
