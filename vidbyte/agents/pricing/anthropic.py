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
    - cost_usd: Bills cache writes at the 5-minute cache-write rate, except the
      cache_creation.ephemeral_1h_input_tokens part, which bills at 2x the
      active input rate; prices at the reported speed, multiplies US-only
      inference by 1.1, and adds $0.01 per server-side web search.
    - _rates_for_speed: Swaps in the row's fast tier when usage.speed is
      "fast"; None for an unknown speed or a model with no fast rate.
    - _inference_geo_multiplier: 1.1 for usage.inference_geo "us", 1.0 for
      "global", "not_available" or no report; None for an unknown geography.
Relations:
    Registered in vidbyte/agents/pricing/base.py; rates from PROVIDER_PRICING,
    fast rates from its tier_rates (ANTHROPIC_FAST_MODE_RATES).
Similar Files:
    - vidbyte/agents/pricing/openai.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.agents.pricing.base import ProviderUsage
from vidbyte.lib.constants.pricing import (
    ANTHROPIC_CACHE_WRITE_1H_INPUT_MULTIPLIER,
    ANTHROPIC_US_INFERENCE_GEO_MULTIPLIER,
    ANTHROPIC_WEB_SEARCH_USD_PER_REQUEST,
)
from vidbyte.lib.enums.usage import AnthropicInferenceGeo, AnthropicSpeed
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
        # Price at the speed and geography the response reports, since a
        # workspace can default to US-only inference with nothing on the
        # request. A value the pricebook cannot price leaves the call
        # unpriced, never billed at standard rates.
        speed_pricing = self._rates_for_speed(pricing)
        geo_multiplier = self._inference_geo_multiplier()
        if speed_pricing is None or geo_multiplier is None:
            return None
        # @intent anthropic-cache-rates-follow-shared-pricing
        # A 0.0 rate is a priced free bucket (only None falls back), and both cache
        # rates scale with the active input tier, exactly as effective_rates prices
        # cache reads for every other provider.
        input_rate, output_rate, cache_read_rate = self.effective_rates(speed_pricing)
        cache_write_rate = speed_pricing.cache_write_per_million
        if cache_write_rate is None:
            cache_write_rate = input_rate
        # @intent free-base-rate-never-divides
        # A 0.0 base input rate (a free model) leaves the tier ratio undefined, so its cache rate applies unscaled.
        elif speed_pricing.input_per_million != 0.0:
            cache_write_rate = cache_write_rate * (input_rate / speed_pricing.input_per_million)
        # @intent anthropic-1h-cache-write-is-2x-input
        # cache_write_rate is the 5-minute write; the cache_creation breakdown names the
        # 1-hour part, which Anthropic bills at 2x the active input rate. With no
        # breakdown every write stays at the 5-minute rate, as before.
        cache_writes = self.cache_creation_input_tokens or 0
        one_hour_writes = min(self.nested_int(self.raw, "cache_creation", "ephemeral_1h_input_tokens") or 0, cache_writes)
        # Each server-side web search the response reports bills a flat
        # fee; a null server_tool_use means no server tool ran.
        web_searches = self.nested_int(self.raw, "server_tool_use", "web_search_requests") or 0
        # US-only inference costs 1.1x on every token bucket, on top of
        # fast mode, caching and the prompt-length tier; 1.0 leaves the
        # cost bit-for-bit unchanged. The search fee is added after it,
        # because it is not a token price.
        return (
            (self.input_tokens or 0) * input_rate
            + (cache_writes - one_hour_writes) * cache_write_rate
            + one_hour_writes * input_rate * ANTHROPIC_CACHE_WRITE_1H_INPUT_MULTIPLIER
            + (self.cache_read_input_tokens or 0) * cache_read_rate
            + (self.output_tokens or 0) * output_rate
        ) / 1_000_000 * geo_multiplier + web_searches * ANTHROPIC_WEB_SEARCH_USD_PER_REQUEST

    def _rates_for_speed(self, pricing: ModelPricing) -> ModelPricing | None:
        # Returns the rates for the speed usage.speed reports; None when
        # that speed is unknown or this model has no rate for it.
        # @intent unknown-or-unrated-speed-is-unpriced
        # Fast mode is a premium (Opus 5.5 bills $8 / $40, not $4 /
        # $20), so a speed this row cannot price must stay unpriced, as
        # an unknown model does, instead of billing at standard rates.
        # A missing or null report means the call ran at standard speed.
        reported = self.raw.get("speed")
        if reported is None:
            return pricing
        try:
            speed = AnthropicSpeed(reported)
        except (TypeError, ValueError):
            return None
        if speed is AnthropicSpeed.STANDARD:
            return pricing
        tier = (pricing.tier_rates or {}).get(speed.value)
        if tier is None:
            return None
        # Fast pricing covers the full context window, so no
        # prompt-length threshold carries over.
        return ModelPricing(
            input_per_million=tier["input_per_million"],
            output_per_million=tier["output_per_million"],
            cache_read_per_million=tier.get("cached_input_per_million"),
            cache_write_per_million=tier.get("cache_write_per_million"),
        )

    def _inference_geo_multiplier(self) -> float | None:
        # Returns the data-residency multiplier for usage.inference_geo;
        # None when the reported geography is unknown.
        # @intent unknown-inference-geo-is-unpriced
        # A geography Anthropic adds later may carry its own multiplier,
        # so it stays unpriced rather than billing at 1x. A missing or
        # null report, global routing, and the "not_available" that
        # pre-4.6 models report all bill at standard rates.
        reported = self.raw.get("inference_geo")
        if reported is None:
            return 1.0
        try:
            geo = AnthropicInferenceGeo(reported)
        except (TypeError, ValueError):
            return None
        return ANTHROPIC_US_INFERENCE_GEO_MULTIPLIER if geo is AnthropicInferenceGeo.US else 1.0


__all__ = ["AnthropicUsage"]
