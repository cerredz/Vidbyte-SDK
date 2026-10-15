"""Context Protocol Header

Description:
    Source-of-truth pricing table and lookup registry for provider text models.
Purpose:
    Centralizes per-model USD token rates so agent usage tracking can price model
    calls without scattering rate constants across providers or agents.
Architecture:
    - ModelPricing: Immutable per-model rate record (USD per million tokens),
      including optional service-tier metadata.
    - OPENAI_GPT56_TIER_RATES: Official GPT-5.6 Standard, Batch, Flex, and Fast
      rate metadata with short/long context fields.
    - OPENAI_GPT6_TIER_RATES: Official GPT-6 Standard, Batch, Flex, Fast, and
      (where offered) Ultrafast rate metadata with short/long context fields.
    - DEEPSEEK_TIME_OF_DAY_RATES: DeepSeek peak and off-peak rate metadata; the
      table itself carries the peak rate.
    - PROVIDER_PRICING: Built-in rate table keyed by provider then model string.
    - PRICING_SOURCE_URL / PRICING_AS_OF: Audit metadata for the live source.
    - ModelPricingRegistry: Resolves (provider, model) to rates with prefix
      matching limited to release suffixes and supports caller overrides.
Key Functions:
    - default: Builds a registry over the built-in PROVIDER_PRICING table.
    - resolve: Returns the ModelPricing for a provider/model, or None.
    - register: Adds or overrides rates for one provider/model entry.
Relations:
    Consumed by vidbyte/agents/pricing (per-provider cost formulas) and by
    UsageTracker, which prices each agent model call against the built-in table.
Similar Files:
    - vidbyte/lib/registries/models.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.registries.models import ProviderModelRegistry


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Per-model USD rates per million tokens; None marks unpriced components."""

    input_per_million: float
    output_per_million: float
    cache_read_per_million: float | None = None
    cache_write_per_million: float | None = None
    threshold_tokens: int | None = None
    input_over_threshold_per_million: float | None = None
    output_over_threshold_per_million: float | None = None
    threshold_inclusive: bool = False
    tier_rates: Mapping[str, Mapping[str, float]] | None = None


PRICING_AS_OF: str = "2026-10-11"
PRICING_SOURCE_URL: str = "https://developers.openai.com/api/docs/pricing"

# Rates verified against official provider pricing pages on PRICING_AS_OF.
# Providers/models with unverifiable rates are omitted so cost resolves to None
# instead of a guessed number (OpenRouter marketplace models, and alias-only
# default names such as grok-4 and openrouter/auto that do not name a priced SKU).
# threshold_inclusive marks providers whose over-threshold tier applies at exactly
# the threshold (xAI, "prompt >= 200k"); the default False keeps the strict ">"
# boundary used by OpenAI, Gemini, and MiniMax.

# GPT-5.6 Sol is priced at its regular rate. OpenAI serves it at a
# promotional $4 / $20 "at least through November 21, 2026"
# (https://developers.openai.com/api/docs/models/gpt-5.6-sol) and
# states no post-promotion rate, so the regular rate is the one it
# listed at the 2026-07-30 vintage: $5 / $0.50 / $6.25 / $30, Batch
# and Flex half that, Fast double.
OPENAI_GPT56_TIER_RATES: dict[str, dict[str, dict[str, float]]] = {
    "gpt-5.6-sol": {
        "standard": {"input_per_million": 5.0, "cached_input_per_million": 0.5, "cache_write_per_million": 6.25, "output_per_million": 30.0, "long_input_per_million": 10.0, "long_cached_input_per_million": 1.0, "long_cache_write_per_million": 12.5, "long_output_per_million": 45.0},
        "batch": {"input_per_million": 2.5, "cached_input_per_million": 0.25, "cache_write_per_million": 3.125, "output_per_million": 15.0, "long_input_per_million": 5.0, "long_cached_input_per_million": 0.5, "long_cache_write_per_million": 6.25, "long_output_per_million": 22.5},
        "flex": {"input_per_million": 2.5, "cached_input_per_million": 0.25, "cache_write_per_million": 3.125, "output_per_million": 15.0, "long_input_per_million": 5.0, "long_cached_input_per_million": 0.5, "long_cache_write_per_million": 6.25, "long_output_per_million": 22.5},
        "fast": {"input_per_million": 10.0, "cached_input_per_million": 1.0, "cache_write_per_million": 12.5, "output_per_million": 60.0},
    },
    "gpt-5.6-terra": {
        "standard": {"input_per_million": 2.0, "cached_input_per_million": 0.2, "cache_write_per_million": 2.5, "output_per_million": 12.0, "long_input_per_million": 4.0, "long_cached_input_per_million": 0.4, "long_cache_write_per_million": 5.0, "long_output_per_million": 18.0},
        "batch": {"input_per_million": 1.0, "cached_input_per_million": 0.1, "cache_write_per_million": 1.25, "output_per_million": 6.0, "long_input_per_million": 2.0, "long_cached_input_per_million": 0.2, "long_cache_write_per_million": 2.5, "long_output_per_million": 9.0},
        "flex": {"input_per_million": 1.0, "cached_input_per_million": 0.1, "cache_write_per_million": 1.25, "output_per_million": 6.0, "long_input_per_million": 2.0, "long_cached_input_per_million": 0.2, "long_cache_write_per_million": 2.5, "long_output_per_million": 9.0},
        "fast": {"input_per_million": 4.0, "cached_input_per_million": 0.4, "cache_write_per_million": 5.0, "output_per_million": 24.0},
    },
    "gpt-5.6-luna": {
        "standard": {"input_per_million": 0.2, "cached_input_per_million": 0.02, "cache_write_per_million": 0.25, "output_per_million": 1.2, "long_input_per_million": 0.4, "long_cached_input_per_million": 0.04, "long_cache_write_per_million": 0.5, "long_output_per_million": 1.8},
        "batch": {"input_per_million": 0.1, "cached_input_per_million": 0.01, "cache_write_per_million": 0.125, "output_per_million": 0.6, "long_input_per_million": 0.2, "long_cached_input_per_million": 0.02, "long_cache_write_per_million": 0.25, "long_output_per_million": 0.9},
        "flex": {"input_per_million": 0.1, "cached_input_per_million": 0.01, "cache_write_per_million": 0.125, "output_per_million": 0.6, "long_input_per_million": 0.2, "long_cached_input_per_million": 0.02, "long_cache_write_per_million": 0.25, "long_output_per_million": 0.9},
        "fast": {"input_per_million": 0.4, "cached_input_per_million": 0.04, "cache_write_per_million": 0.5, "output_per_million": 2.4},
    },
}

# GPT-6 tier rates from https://developers.openai.com/api/docs/pricing
# (Standard, Batch, Flex, Fast and Ultrafast tabs). That page's GPT-6
# Sol row shows short-context columns only, so its long-context fields
# apply the rule on
# https://developers.openai.com/api/docs/models/gpt-6-sol: over 272K
# input, "2x input and cache rates and 1.5x output".
OPENAI_GPT6_TIER_RATES: dict[str, dict[str, dict[str, float]]] = {
    "gpt-6-astra": {
        "standard": {"input_per_million": 10.0, "cached_input_per_million": 1.0, "cache_write_per_million": 12.5, "output_per_million": 50.0, "long_input_per_million": 20.0, "long_cached_input_per_million": 2.0, "long_cache_write_per_million": 25.0, "long_output_per_million": 75.0},
        "batch": {"input_per_million": 5.0, "cached_input_per_million": 0.5, "cache_write_per_million": 6.25, "output_per_million": 25.0, "long_input_per_million": 10.0, "long_cached_input_per_million": 1.0, "long_cache_write_per_million": 12.5, "long_output_per_million": 37.5},
        "flex": {"input_per_million": 5.0, "cached_input_per_million": 0.5, "cache_write_per_million": 6.25, "output_per_million": 25.0, "long_input_per_million": 10.0, "long_cached_input_per_million": 1.0, "long_cache_write_per_million": 12.5, "long_output_per_million": 37.5},
        "fast": {"input_per_million": 20.0, "cached_input_per_million": 2.0, "cache_write_per_million": 25.0, "output_per_million": 100.0, "long_input_per_million": 40.0, "long_cached_input_per_million": 4.0, "long_cache_write_per_million": 50.0, "long_output_per_million": 150.0},
        "ultrafast": {"input_per_million": 60.0, "cached_input_per_million": 6.0, "cache_write_per_million": 75.0, "output_per_million": 300.0, "long_input_per_million": 120.0, "long_cached_input_per_million": 12.0, "long_cache_write_per_million": 150.0, "long_output_per_million": 450.0},
    },
    "gpt-6.1-sol": {
        "standard": {"input_per_million": 2.0, "cached_input_per_million": 0.1, "cache_write_per_million": 2.5, "output_per_million": 10.0, "long_input_per_million": 4.0, "long_cached_input_per_million": 0.2, "long_cache_write_per_million": 5.0, "long_output_per_million": 15.0},
        "batch": {"input_per_million": 1.0, "cached_input_per_million": 0.05, "cache_write_per_million": 1.25, "output_per_million": 5.0, "long_input_per_million": 2.0, "long_cached_input_per_million": 0.1, "long_cache_write_per_million": 2.5, "long_output_per_million": 7.5},
        "flex": {"input_per_million": 1.0, "cached_input_per_million": 0.05, "cache_write_per_million": 1.25, "output_per_million": 5.0, "long_input_per_million": 2.0, "long_cached_input_per_million": 0.1, "long_cache_write_per_million": 2.5, "long_output_per_million": 7.5},
        "fast": {"input_per_million": 4.0, "cached_input_per_million": 0.2, "cache_write_per_million": 5.0, "output_per_million": 20.0, "long_input_per_million": 8.0, "long_cached_input_per_million": 0.4, "long_cache_write_per_million": 10.0, "long_output_per_million": 30.0},
        "ultrafast": {"input_per_million": 12.0, "cached_input_per_million": 0.6, "cache_write_per_million": 15.0, "output_per_million": 60.0, "long_input_per_million": 24.0, "long_cached_input_per_million": 1.2, "long_cache_write_per_million": 30.0, "long_output_per_million": 90.0},
    },
    "gpt-6-sol": {
        "standard": {"input_per_million": 2.0, "cached_input_per_million": 0.2, "cache_write_per_million": 2.5, "output_per_million": 10.0, "long_input_per_million": 4.0, "long_cached_input_per_million": 0.4, "long_cache_write_per_million": 5.0, "long_output_per_million": 15.0},
        "batch": {"input_per_million": 1.0, "cached_input_per_million": 0.1, "cache_write_per_million": 1.25, "output_per_million": 5.0, "long_input_per_million": 2.0, "long_cached_input_per_million": 0.2, "long_cache_write_per_million": 2.5, "long_output_per_million": 7.5},
        "flex": {"input_per_million": 1.0, "cached_input_per_million": 0.1, "cache_write_per_million": 1.25, "output_per_million": 5.0, "long_input_per_million": 2.0, "long_cached_input_per_million": 0.2, "long_cache_write_per_million": 2.5, "long_output_per_million": 7.5},
        "fast": {"input_per_million": 4.0, "cached_input_per_million": 0.4, "cache_write_per_million": 5.0, "output_per_million": 20.0, "long_input_per_million": 8.0, "long_cached_input_per_million": 0.8, "long_cache_write_per_million": 10.0, "long_output_per_million": 30.0},
    },
    "gpt-6-luna": {
        "standard": {"input_per_million": 0.1, "cached_input_per_million": 0.01, "cache_write_per_million": 0.125, "output_per_million": 0.5, "long_input_per_million": 0.2, "long_cached_input_per_million": 0.02, "long_cache_write_per_million": 0.25, "long_output_per_million": 0.75},
        "batch": {"input_per_million": 0.05, "cached_input_per_million": 0.005, "cache_write_per_million": 0.0625, "output_per_million": 0.25, "long_input_per_million": 0.1, "long_cached_input_per_million": 0.01, "long_cache_write_per_million": 0.125, "long_output_per_million": 0.375},
        "flex": {"input_per_million": 0.05, "cached_input_per_million": 0.005, "cache_write_per_million": 0.0625, "output_per_million": 0.25, "long_input_per_million": 0.1, "long_cached_input_per_million": 0.01, "long_cache_write_per_million": 0.125, "long_output_per_million": 0.375},
        "fast": {"input_per_million": 0.2, "cached_input_per_million": 0.02, "cache_write_per_million": 0.25, "output_per_million": 1.0, "long_input_per_million": 0.4, "long_cached_input_per_million": 0.04, "long_cache_write_per_million": 0.5, "long_output_per_million": 1.5},
    },
}

# DeepSeek bills a peak rate from 01:00-04:00 and 06:00-10:00 UTC on
# weekdays and half of it at all other hours
# (https://api-docs.deepseek.com/quick_start/pricing). The cost formulas
# have no clock, so PROVIDER_PRICING carries the peak rate (a call is
# never under-billed) and this metadata keeps both.
DEEPSEEK_TIME_OF_DAY_RATES: dict[str, dict[str, dict[str, float]]] = {
    "deepseek-flash": {
        "peak": {"input_per_million": 0.3, "cached_input_per_million": 0.006, "output_per_million": 1.2},
        "off_peak": {"input_per_million": 0.15, "cached_input_per_million": 0.003, "output_per_million": 0.6},
    },
    "deepseek-v4-pro": {
        "peak": {"input_per_million": 1.32, "cached_input_per_million": 0.044, "output_per_million": 3.96},
        "off_peak": {"input_per_million": 0.66, "cached_input_per_million": 0.022, "output_per_million": 1.98},
    },
}

PROVIDER_PRICING: dict[ModelProvider, dict[str, ModelPricing]] = {
    # OpenAI charges the long-context tier (input x2, output x1.5) for the whole
    # request once prompt input exceeds 272k tokens; sub-272k uses the short rate.
    ModelProvider.OPENAI: {
        # GPT-6 Standard rates from
        # https://developers.openai.com/api/docs/pricing and each
        # model's page under
        # https://developers.openai.com/api/docs/models/. Cache writes
        # bill at 1.25x input; GPT-6.1 Sol caches at 5% of input.
        "gpt-6-astra": ModelPricing(input_per_million=10.0, output_per_million=50.0, cache_read_per_million=1.0, cache_write_per_million=12.5, threshold_tokens=272_000, input_over_threshold_per_million=20.0, output_over_threshold_per_million=75.0, tier_rates=OPENAI_GPT6_TIER_RATES["gpt-6-astra"]),
        "gpt-6.1-sol": ModelPricing(input_per_million=2.0, output_per_million=10.0, cache_read_per_million=0.1, cache_write_per_million=2.5, threshold_tokens=272_000, input_over_threshold_per_million=4.0, output_over_threshold_per_million=15.0, tier_rates=OPENAI_GPT6_TIER_RATES["gpt-6.1-sol"]),
        "gpt-6-sol": ModelPricing(input_per_million=2.0, output_per_million=10.0, cache_read_per_million=0.2, cache_write_per_million=2.5, threshold_tokens=272_000, input_over_threshold_per_million=4.0, output_over_threshold_per_million=15.0, tier_rates=OPENAI_GPT6_TIER_RATES["gpt-6-sol"]),
        "gpt-6-luna": ModelPricing(input_per_million=0.1, output_per_million=0.5, cache_read_per_million=0.01, cache_write_per_million=0.125, threshold_tokens=272_000, input_over_threshold_per_million=0.2, output_over_threshold_per_million=0.75, tier_rates=OPENAI_GPT6_TIER_RATES["gpt-6-luna"]),
        # Regular rate, not the current promotion; see
        # OPENAI_GPT56_TIER_RATES.
        "gpt-5.6-sol": ModelPricing(input_per_million=5.0, output_per_million=30.0, cache_read_per_million=0.5, cache_write_per_million=6.25, threshold_tokens=272_000, input_over_threshold_per_million=10.0, output_over_threshold_per_million=45.0, tier_rates=OPENAI_GPT56_TIER_RATES["gpt-5.6-sol"]),
        "gpt-5.6-terra": ModelPricing(input_per_million=2.0, output_per_million=12.0, cache_read_per_million=0.2, cache_write_per_million=2.5, threshold_tokens=272_000, input_over_threshold_per_million=4.0, output_over_threshold_per_million=18.0, tier_rates=OPENAI_GPT56_TIER_RATES["gpt-5.6-terra"]),
        "gpt-5.6-luna": ModelPricing(input_per_million=0.2, output_per_million=1.2, cache_read_per_million=0.02, cache_write_per_million=0.25, threshold_tokens=272_000, input_over_threshold_per_million=0.4, output_over_threshold_per_million=1.8, tier_rates=OPENAI_GPT56_TIER_RATES["gpt-5.6-luna"]),
        "gpt-5.5": ModelPricing(input_per_million=5.0, output_per_million=30.0, cache_read_per_million=0.5, threshold_tokens=272_000, input_over_threshold_per_million=10.0, output_over_threshold_per_million=45.0),
        "gpt-5.5-pro": ModelPricing(input_per_million=30.0, output_per_million=180.0),
        "gpt-5.4": ModelPricing(input_per_million=2.5, output_per_million=15.0, cache_read_per_million=0.25, threshold_tokens=272_000, input_over_threshold_per_million=5.0, output_over_threshold_per_million=22.5),
        "gpt-5.4-mini": ModelPricing(input_per_million=0.75, output_per_million=4.5, cache_read_per_million=0.075),
        "gpt-5.4-nano": ModelPricing(input_per_million=0.2, output_per_million=1.25, cache_read_per_million=0.02),
        "gpt-5.4-pro": ModelPricing(input_per_million=30.0, output_per_million=180.0),
    },
    ModelProvider.ANTHROPIC: {
        # Claude 5.x rates from
        # https://platform.claude.com/docs/en/about-claude/pricing and
        # each model's page, e.g.
        # https://platform.claude.com/docs/en/models/opus-5-5/overview.
        # cache_write is the 5-minute write. Cache hits cost 2.5% of
        # input on Fable 5.1 and Mythos 5.1 (verification-only access)
        # and 5% on Opus 5.5 and Sonnet 5.5.
        "claude-fable-5-1": ModelPricing(input_per_million=10.0, output_per_million=50.0, cache_read_per_million=0.25, cache_write_per_million=12.5),
        "claude-mythos-5-1": ModelPricing(input_per_million=10.0, output_per_million=50.0, cache_read_per_million=0.25, cache_write_per_million=12.5),
        "claude-opus-5-5": ModelPricing(input_per_million=4.0, output_per_million=20.0, cache_read_per_million=0.2, cache_write_per_million=5.0),
        "claude-sonnet-5-5": ModelPricing(input_per_million=2.0, output_per_million=10.0, cache_read_per_million=0.1, cache_write_per_million=2.5),
        # Haiku 5.5 charges 5x for a prompt over 100,000 tokens, and the
        # prompt counts cache reads and writes ("Long context pricing"
        # on the pricing page); AnthropicUsage compares the full prompt.
        "claude-haiku-5-5": ModelPricing(input_per_million=0.1, output_per_million=0.5, cache_read_per_million=0.01, cache_write_per_million=0.125, threshold_tokens=100_000, input_over_threshold_per_million=0.5, output_over_threshold_per_million=2.5),
        "claude-opus-5": ModelPricing(input_per_million=5.0, output_per_million=25.0, cache_read_per_million=0.5, cache_write_per_million=6.25),
        "claude-fable-5": ModelPricing(input_per_million=10.0, output_per_million=50.0, cache_read_per_million=1.0, cache_write_per_million=12.5),
        "claude-mythos-5": ModelPricing(input_per_million=10.0, output_per_million=50.0, cache_read_per_million=1.0, cache_write_per_million=12.5),
        # Sonnet 5's introductory window ended 2026-08-31 and the
        # pricing page still lists $2 / $10, its regular rate now.
        "claude-sonnet-5": ModelPricing(input_per_million=2.0, output_per_million=10.0, cache_read_per_million=0.2, cache_write_per_million=2.5),
        "claude-sonnet-4-6": ModelPricing(input_per_million=3.0, output_per_million=15.0, cache_read_per_million=0.3, cache_write_per_million=3.75),
        "claude-sonnet-4-5": ModelPricing(input_per_million=3.0, output_per_million=15.0, cache_read_per_million=0.3, cache_write_per_million=3.75),
        "claude-opus-4-8": ModelPricing(input_per_million=5.0, output_per_million=25.0, cache_read_per_million=0.5, cache_write_per_million=6.25),
        "claude-opus-4-7": ModelPricing(input_per_million=5.0, output_per_million=25.0, cache_read_per_million=0.5, cache_write_per_million=6.25),
        "claude-opus-4-6": ModelPricing(input_per_million=5.0, output_per_million=25.0, cache_read_per_million=0.5, cache_write_per_million=6.25),
        "claude-opus-4-5": ModelPricing(input_per_million=5.0, output_per_million=25.0, cache_read_per_million=0.5, cache_write_per_million=6.25),
        "claude-haiku-4-5": ModelPricing(input_per_million=1.0, output_per_million=5.0, cache_read_per_million=0.1, cache_write_per_million=1.25),
    },
    ModelProvider.GEMINI: {
        # Paid-tier text rates from
        # https://ai.google.dev/gemini-api/docs/pricing. 3.8 and 3.6
        # Flash bill at their regular $1.50 / $7.50 (cache $0.15),
        # listed "starting January 1, 2027"; until then Google serves
        # a promotional $0.75 / $3.75 "through December 31, 2026".
        "gemini-3.8-flash": ModelPricing(input_per_million=1.5, output_per_million=7.5, cache_read_per_million=0.15),
        "gemini-3.6-flash": ModelPricing(input_per_million=1.5, output_per_million=7.5, cache_read_per_million=0.15),
        # 3.5 Flash is deprecated and "All requests to gemini-3.5-flash
        # are automatically routed to gemini-3.6-flash", so it bills at
        # the 3.6 Flash rate. Source:
        # https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash
        "gemini-3.5-flash": ModelPricing(input_per_million=1.5, output_per_million=7.5, cache_read_per_million=0.15),
        "gemini-3.5-flash-lite": ModelPricing(input_per_million=0.3, output_per_million=2.5, cache_read_per_million=0.03),
        # Text, image, and video rate; audio input costs $0.50 (cache
        # $0.05).
        "gemini-3.1-flash-lite": ModelPricing(input_per_million=0.25, output_per_million=1.5, cache_read_per_million=0.025),
        "gemini-3.1-pro-preview": ModelPricing(input_per_million=2.0, output_per_million=12.0, cache_read_per_million=0.2, threshold_tokens=200_000, input_over_threshold_per_million=4.0, output_over_threshold_per_million=18.0),
    },
    # xAI applies the high tier at prompts >= 200k (inclusive), unlike the ">" boundary
    # used by the other tiered providers, so these entries set threshold_inclusive.
    ModelProvider.XAI: {
        # Grok 4.7 and 4.6 from https://docs.x.ai/developers/models and
        # https://docs.x.ai/developers/models/grok-4.7: "Requests whose
        # prompt reaches 200k tokens are billed at the higher rate".
        "grok-4.7": ModelPricing(input_per_million=2.0, output_per_million=6.0, cache_read_per_million=0.5, threshold_tokens=200_000, input_over_threshold_per_million=4.0, output_over_threshold_per_million=12.0, threshold_inclusive=True),
        "grok-4.6": ModelPricing(input_per_million=2.0, output_per_million=6.0, cache_read_per_million=0.5, threshold_tokens=200_000, input_over_threshold_per_million=4.0, output_over_threshold_per_million=12.0, threshold_inclusive=True),
        "grok-4.5": ModelPricing(input_per_million=2.0, output_per_million=6.0, cache_read_per_million=0.3, threshold_tokens=200_000, input_over_threshold_per_million=4.0, output_over_threshold_per_million=12.0, threshold_inclusive=True),
        "grok-4.3": ModelPricing(input_per_million=1.25, output_per_million=2.5, cache_read_per_million=0.2, threshold_tokens=200_000, input_over_threshold_per_million=2.5, output_over_threshold_per_million=5.0, threshold_inclusive=True),
        "grok-build-0.1": ModelPricing(input_per_million=1.0, output_per_million=2.0, cache_read_per_million=0.2, threshold_tokens=200_000, input_over_threshold_per_million=2.0, output_over_threshold_per_million=4.0, threshold_inclusive=True),
    },
    # Peak rates; see DEEPSEEK_TIME_OF_DAY_RATES for the off-peak half.
    # deepseek-v4-flash is a legacy name whose requests "are served by
    # the DeepSeek-V4.1-Flash model and billed at the Flash price".
    ModelProvider.DEEPSEEK: {
        "deepseek-flash": ModelPricing(input_per_million=0.3, output_per_million=1.2, cache_read_per_million=0.006, tier_rates=DEEPSEEK_TIME_OF_DAY_RATES["deepseek-flash"]),
        "deepseek-v4-flash": ModelPricing(input_per_million=0.3, output_per_million=1.2, cache_read_per_million=0.006, tier_rates=DEEPSEEK_TIME_OF_DAY_RATES["deepseek-flash"]),
        "deepseek-v4-pro": ModelPricing(input_per_million=1.32, output_per_million=3.96, cache_read_per_million=0.044, tier_rates=DEEPSEEK_TIME_OF_DAY_RATES["deepseek-v4-pro"]),
    },
    # GLM first-party (Z.ai) rates; no context tiers published.
    ModelProvider.GLM: {
        # GLM-5.3 family from https://docs.z.ai/guides/overview/pricing;
        # model codes from https://docs.z.ai/guides/vlm/glm-5.3-flash.
        "glm-5.3": ModelPricing(input_per_million=1.4, output_per_million=4.4, cache_read_per_million=0.26),
        "glm-5.3-flash": ModelPricing(input_per_million=0.15, output_per_million=0.5, cache_read_per_million=0.03),
        "glm-5.3-flashx": ModelPricing(input_per_million=0.37, output_per_million=1.25, cache_read_per_million=0.075),
        "glm-5.2": ModelPricing(input_per_million=1.4, output_per_million=4.4, cache_read_per_million=0.26),
        "glm-5.1": ModelPricing(input_per_million=1.4, output_per_million=4.4, cache_read_per_million=0.26),
        # No longer listed on the Z.ai pricing page as of 2026-10-11;
        # the rate is kept from the 2026-07-30 vintage.
        "glm-5-turbo": ModelPricing(input_per_million=1.2, output_per_million=4.0, cache_read_per_million=0.24),
        "glm-5": ModelPricing(input_per_million=1.0, output_per_million=3.2, cache_read_per_million=0.2),
        "glm-4.7": ModelPricing(input_per_million=0.6, output_per_million=2.2, cache_read_per_million=0.11),
        "glm-4.6": ModelPricing(input_per_million=0.6, output_per_million=2.2, cache_read_per_million=0.11),
        "glm-4.5": ModelPricing(input_per_million=0.6, output_per_million=2.2, cache_read_per_million=0.11),
    },
    # MiniMax M3 standard-tier rates reflect the "permanent 50% off" promo over the
    # $0.60/$2.40 list price; the >512k long-context tier doubles input and output.
    ModelProvider.MINIMAX: {
        "MiniMax-M3": ModelPricing(input_per_million=0.3, output_per_million=1.2, cache_read_per_million=0.06, threshold_tokens=512_000, input_over_threshold_per_million=0.6, output_over_threshold_per_million=2.4),
        "MiniMax-M2.7-highspeed": ModelPricing(input_per_million=0.6, output_per_million=2.4, cache_read_per_million=0.06, cache_write_per_million=0.375),
        "MiniMax-M2.7": ModelPricing(input_per_million=0.3, output_per_million=1.2, cache_read_per_million=0.06, cache_write_per_million=0.375),
    },
    ModelProvider.KIMI: {
        # Rates from https://platform.kimi.ai/docs/pricing/chat. Kimi
        # K3's 5-minute cache write costs the input rate ($3.00); its
        # 1-hour write ($6.00) is not modelled.
        "kimi-k3": ModelPricing(input_per_million=3.0, output_per_million=15.0, cache_read_per_million=0.3, cache_write_per_million=3.0),
        "kimi-k2.6": ModelPricing(input_per_million=0.95, output_per_million=4.0, cache_read_per_million=0.16),
        "kimi-k2.7-code": ModelPricing(input_per_million=0.95, output_per_million=4.0, cache_read_per_million=0.19),
        "kimi-k2.7-code-highspeed": ModelPricing(input_per_million=1.9, output_per_million=8.0, cache_read_per_million=0.38),
    },
    # OpenRouter models are priced per-generation by the marketplace; the SDK
    # prefers the provider-reported usage.cost over table math for this provider.
    ModelProvider.OPENROUTER: {},
    # Meta Model API (OpenAI-compatible); Muse Spark 1.1 is flat-rate, no context tier.
    ModelProvider.META: {
        # Standard and Contributor tiers from
        # https://dev.meta.ai/docs/pricing-rate-limits ("no long-context
        # premium"). Contributor models let Meta train on your prompts.
        "muse-spark-1.3": ModelPricing(input_per_million=1.25, output_per_million=4.25, cache_read_per_million=0.15),
        "muse-spark-1.2": ModelPricing(input_per_million=1.25, output_per_million=4.25, cache_read_per_million=0.15),
        "muse-spark-1.1": ModelPricing(input_per_million=1.25, output_per_million=4.25, cache_read_per_million=0.15),
        "muse-spark-1.3-contributor": ModelPricing(input_per_million=0.1, output_per_million=0.2, cache_read_per_million=0.002),
        "muse-spark-1.2-contributor": ModelPricing(input_per_million=0.1, output_per_million=0.2, cache_read_per_million=0.002),
    },
    # Each model's page on https://docs.mistral.ai/models/ (for example
    # https://docs.mistral.ai/models/mistral-medium-3-5-26-04) lists its
    # API names and price. Medium 3.5, Small 4 and Large 3 publish no
    # cached rate, so cached tokens bill at the input rate. Large 4 is
    # priced at its regular $1.36 / $4.18 (cache $0.14); the public
    # preview is on sale at $0.68 / $2.09.
    ModelProvider.MISTRAL: {
        "mistral-medium-3-5": ModelPricing(input_per_million=1.5, output_per_million=7.5),
        "mistral-medium-latest": ModelPricing(input_per_million=1.5, output_per_million=7.5),
        "mistral-small-2603": ModelPricing(input_per_million=0.15, output_per_million=0.6),
        "mistral-small-latest": ModelPricing(input_per_million=0.15, output_per_million=0.6),
        "mistral-large-2512": ModelPricing(input_per_million=0.5, output_per_million=1.5),
        "mistral-large-latest": ModelPricing(input_per_million=0.5, output_per_million=1.5),
        "mistral-large-4": ModelPricing(input_per_million=1.36, output_per_million=4.18, cache_read_per_million=0.14),
        "mistral-large-4-0": ModelPricing(input_per_million=1.36, output_per_million=4.18, cache_read_per_million=0.14),
    },
    # TypeSafe Jev 1.13 (System One decision model), checked 2026-09-21 against
    # https://docs.typesafe.ai/models.md: "$42 / $0.042" per Btok / per Mtok, "Charged per
    # input token. Output tokens are free." The API reports only input_tokens and
    # output_tokens (https://docs.typesafe.ai/api.md#response-body) and publishes no cached-
    # token rate, so no cache_read rate applies. Responses name the versioned model that
    # answered (jev-1.13.0), which the "jev-1.13" prefix prices; both aliases point to it.
    ModelProvider.TYPESAFE: {
        "jev-1.13": ModelPricing(input_per_million=0.042, output_per_million=0.0),
        "jev-latest": ModelPricing(input_per_million=0.042, output_per_million=0.0),
        "jev-preview": ModelPricing(input_per_million=0.042, output_per_million=0.0),
    },
}


class ModelPricingRegistry:
    """Resolves (provider, model) pairs to ModelPricing with override support."""

    _EMPTY_TABLE: ClassVar[dict[str, ModelPricing]] = {}

    def __init__(self, table: Mapping[ModelProvider, Mapping[str, ModelPricing]] | None = None) -> None:
        # Copy the source table so register() never mutates shared class state.
        source = table if table is not None else PROVIDER_PRICING
        self._table: dict[ModelProvider, dict[str, ModelPricing]] = {provider: dict(models) for provider, models in source.items()}

    @classmethod
    def default(cls) -> "ModelPricingRegistry":
        # Returns an independent registry over the built-in PROVIDER_PRICING table.
        return cls(PROVIDER_PRICING)

    def resolve(self, provider: ModelProvider, model: str) -> ModelPricing | None:
        # Returns exact pricing for the model, else the longest key it is a
        # release of (dated snapshot, -latest, or patch version), else None. The
        # provider is strictly a ModelProvider (the enum's frozen set of keys);
        # callers coerce any raw provider string once, at the ingestion boundary.
        if not isinstance(provider, ModelProvider) or not isinstance(model, str) or not model.strip():
            return None
        models = self._table.get(provider, self._EMPTY_TABLE)
        requested_model = model.strip()
        exact = models.get(requested_model)
        if exact is not None:
            return exact
        canonical_model = ProviderModelRegistry.normalize_model(provider, requested_model)
        exact = models.get(canonical_model)
        if exact is not None:
            return exact
        # Fall back to the longest priced key the model is a release of, so a
        # differently named variant with no row of its own stays unpriced.
        prefix_matches = [
            (key, pricing)
            for key, pricing in models.items()
            if canonical_model.startswith(key) and self._is_release_suffix(canonical_model[len(key):])
        ]
        if not prefix_matches:
            return None
        return max(prefix_matches, key=lambda item: len(item[0]))[1]

    @staticmethod
    def _is_release_suffix(remainder: str) -> bool:
        # @intent prefix-pricing-covers-releases-not-variants
        # A dated snapshot (-20251001), -latest, or a patch version (.0) is the same
        # SKU; a lettered suffix (-flash, -mini, -pro) names a different SKU, which
        # this table omits rather than guesses, so its cost resolves to None.
        if remainder == "-latest":
            return True
        return not (len(remainder) >= 2 and remainder[0] == "-" and remainder[1].isalpha())

    def register(self, provider: ModelProvider, model: str, pricing: ModelPricing) -> None:
        # Adds or overrides one provider/model entry after validating inputs; the
        # provider must be a ModelProvider rather than an arbitrary string.
        if not isinstance(provider, ModelProvider):
            raise ConfigurationError("provider must be a ModelProvider.")
        if not isinstance(model, str) or not model.strip():
            raise ConfigurationError("model must be a non-empty string.")
        if not isinstance(pricing, ModelPricing):
            raise ConfigurationError("pricing must be a ModelPricing instance.")
        self._table.setdefault(provider, {})[model] = pricing


__all__ = [
    "ModelPricing",
    "ModelPricingRegistry",
    "DEEPSEEK_TIME_OF_DAY_RATES",
    "OPENAI_GPT56_TIER_RATES",
    "OPENAI_GPT6_TIER_RATES",
    "PRICING_AS_OF",
    "PRICING_SOURCE_URL",
    "PROVIDER_PRICING",
]
