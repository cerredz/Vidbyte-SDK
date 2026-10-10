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
    - PROVIDER_PRICING: Built-in rate table keyed by provider then model string.
    - PRICING_SOURCE_URL / PRICING_AS_OF: Audit metadata for the live source.
    - ModelPricingRegistry: Resolves (provider, model) to rates with prefix
      matching and supports caller overrides.
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


PRICING_AS_OF: str = "2026-10-10"
PRICING_SOURCE_URL: str = "https://developers.openai.com/api/docs/pricing"

# Rates verified against official provider pricing pages on PRICING_AS_OF.
# Providers/models with unverifiable rates are omitted so cost resolves to None
# instead of a guessed number (OpenRouter marketplace models, and alias-only
# default names such as grok-4 and openrouter/auto that do not name a priced SKU).
# threshold_inclusive marks providers whose over-threshold tier applies at exactly
# the threshold (xAI, "prompt >= 200k"); the default False keeps the strict ">"
# boundary used by OpenAI, Gemini, and MiniMax.

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

PROVIDER_PRICING: dict[ModelProvider, dict[str, ModelPricing]] = {
    # OpenAI charges the long-context tier (input x2, output x1.5) for the whole
    # request once prompt input exceeds 272k tokens; sub-272k uses the short rate.
    ModelProvider.OPENAI: {
        "gpt-5.6-sol": ModelPricing(input_per_million=5.0, output_per_million=30.0, cache_read_per_million=0.5, cache_write_per_million=6.25, threshold_tokens=272_000, input_over_threshold_per_million=10.0, output_over_threshold_per_million=45.0, tier_rates=OPENAI_GPT56_TIER_RATES["gpt-5.6-sol"]),
        "gpt-5.6-terra": ModelPricing(input_per_million=2.0, output_per_million=12.0, cache_read_per_million=0.2, cache_write_per_million=2.5, threshold_tokens=272_000, input_over_threshold_per_million=4.0, output_over_threshold_per_million=18.0, tier_rates=OPENAI_GPT56_TIER_RATES["gpt-5.6-terra"]),
        "gpt-5.6-luna": ModelPricing(input_per_million=0.2, output_per_million=1.2, cache_read_per_million=0.02, cache_write_per_million=0.25, threshold_tokens=272_000, input_over_threshold_per_million=0.4, output_over_threshold_per_million=1.8, tier_rates=OPENAI_GPT56_TIER_RATES["gpt-5.6-luna"]),
        "gpt-5.5": ModelPricing(input_per_million=5.0, output_per_million=30.0, cache_read_per_million=0.5, threshold_tokens=272_000, input_over_threshold_per_million=10.0, output_over_threshold_per_million=45.0),
        "gpt-5.5-pro": ModelPricing(input_per_million=30.0, output_per_million=180.0),
        "gpt-5.4": ModelPricing(input_per_million=2.5, output_per_million=15.0, cache_read_per_million=0.25, threshold_tokens=272_000, input_over_threshold_per_million=5.0, output_over_threshold_per_million=22.5),
        "gpt-5.4-mini": ModelPricing(input_per_million=0.75, output_per_million=4.5, cache_read_per_million=0.075),
        "gpt-5.4-nano": ModelPricing(input_per_million=0.2, output_per_million=1.25, cache_read_per_million=0.02),
        "gpt-5.4-pro": ModelPricing(input_per_million=30.0, output_per_million=180.0),
        # gpt-6-luna through the Decisions API (/v1/decisions), checked 2026-10-10 against the
        # Decisions guide https://developers.openai.com/api/docs/guides/decisions ("With `gpt-6-luna`,
        # input costs $0.10 per 1M tokens. You pay only for input tokens: there are no cache-read,
        # cache-write, or output-token charges." and "Regional processing premiums and long-context
        # input pricing multipliers apply. These rates apply to `/v1/decisions`"). The multiplier is
        # on the model page https://developers.openai.com/api/docs/models/gpt-6-luna: "Prompts with
        # more than 272K input tokens are priced at 2x input [...] for the full request", so input
        # over 272K is 0.20 (derived as 2x; no page prints it). The 10% regional processing premium
        # is not represented, as for every OpenAI row. The model is reached only through the
        # decisions adapter (it is not in the text runner catalog), so the decision rate is the one
        # this row carries (spec D-12).
        "gpt-6-luna": ModelPricing(input_per_million=0.10, output_per_million=0.0, threshold_tokens=272_000, input_over_threshold_per_million=0.20, output_over_threshold_per_million=0.0),
    },
    ModelProvider.ANTHROPIC: {
        # claude-sonnet-5 introductory pricing, in effect through 2026-08-31.
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
        "gemini-3.5-flash": ModelPricing(input_per_million=1.5, output_per_million=9.0, cache_read_per_million=0.15),
        "gemini-3.6-flash": ModelPricing(input_per_million=1.5, output_per_million=7.5, cache_read_per_million=0.15),
        "gemini-3.1-pro-preview": ModelPricing(input_per_million=2.0, output_per_million=12.0, cache_read_per_million=0.2, threshold_tokens=200_000, input_over_threshold_per_million=4.0, output_over_threshold_per_million=18.0),
    },
    # xAI applies the high tier at prompts >= 200k (inclusive), unlike the ">" boundary
    # used by the other tiered providers, so these entries set threshold_inclusive.
    ModelProvider.XAI: {
        "grok-4.5": ModelPricing(input_per_million=2.0, output_per_million=6.0, cache_read_per_million=0.3, threshold_tokens=200_000, input_over_threshold_per_million=4.0, output_over_threshold_per_million=12.0, threshold_inclusive=True),
        "grok-4.3": ModelPricing(input_per_million=1.25, output_per_million=2.5, cache_read_per_million=0.2, threshold_tokens=200_000, input_over_threshold_per_million=2.5, output_over_threshold_per_million=5.0, threshold_inclusive=True),
        "grok-build-0.1": ModelPricing(input_per_million=1.0, output_per_million=2.0, cache_read_per_million=0.2, threshold_tokens=200_000, input_over_threshold_per_million=2.0, output_over_threshold_per_million=4.0, threshold_inclusive=True),
    },
    ModelProvider.DEEPSEEK: {
        "deepseek-v4-pro": ModelPricing(input_per_million=0.435, output_per_million=0.87, cache_read_per_million=0.003625),
        "deepseek-v4-flash": ModelPricing(input_per_million=0.14, output_per_million=0.28, cache_read_per_million=0.0028),
    },
    # GLM first-party (Z.ai) rates; no context tiers published.
    ModelProvider.GLM: {
        "glm-5.2": ModelPricing(input_per_million=1.4, output_per_million=4.4, cache_read_per_million=0.26),
        "glm-5.1": ModelPricing(input_per_million=1.4, output_per_million=4.4, cache_read_per_million=0.26),
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
        "kimi-k2.7-code": ModelPricing(input_per_million=0.95, output_per_million=4.0, cache_read_per_million=0.19),
        "kimi-k2.7-code-highspeed": ModelPricing(input_per_million=1.9, output_per_million=8.0, cache_read_per_million=0.38),
    },
    # OpenRouter models are priced per-generation by the marketplace; the SDK
    # prefers the provider-reported usage.cost over table math for this provider.
    # For reference, the decision default typesafe/jev-1.13 is listed at "$0.042 per million input
    # tokens, $0 per million output tokens" on https://openrouter.ai/typesafe/jev-1.13/pricing
    # (retrieved 2026-10-10); no row is kept because usage.cost is authoritative (lint C009 declares
    # OPENROUTER priced per response).
    ModelProvider.OPENROUTER: {},
    # Meta Model API (OpenAI-compatible); Muse Spark 1.1 is flat-rate, no context tier.
    ModelProvider.META: {
        "muse-spark-1.1": ModelPricing(input_per_million=1.25, output_per_million=4.25, cache_read_per_million=0.15),
    },
    # TypeSafe Jev 1.13 (System One decision model), re-checked 2026-10-10 against TypeSafe's API
    # model docs https://docs.typesafe.ai/models.md (TypeSafe has no separate pricing page):
    # "Price (per Btok / per Mtok) | $42 / $0.042" and "Charged per input token. Output tokens are
    # free." The API reports only input_tokens and output_tokens
    # (https://docs.typesafe.ai/api.md#response-body) and publishes no cached-token rate, so no
    # cache_read rate applies. Responses name the versioned model that answered (jev-1.13.0), which
    # the "jev-1.13" prefix prices; the jev-latest and jev-preview aliases both point to it.
    ModelProvider.TYPESAFE: {
        "jev-1.13": ModelPricing(input_per_million=0.042, output_per_million=0.0),
        "jev-latest": ModelPricing(input_per_million=0.042, output_per_million=0.0),
        "jev-preview": ModelPricing(input_per_million=0.042, output_per_million=0.0),
    },
    # Perplexity Decisions API (System One wire), checked 2026-10-10 against the API pricing page
    # https://docs.perplexity.ai/docs/getting-started/pricing ("Decisions API Pricing", columns
    # $/1M input tokens | output tokens | per-request fee: "pplx-decider-v1.1-27b | $0.02 | Free |
    # None" and "pplx-decider-v1-27b | $0.02 | Free | None") and the API reference
    # https://docs.perplexity.ai/api-reference/decisions-post ("Input tokens are billed at $0.02 per
    # million; output tokens are free").
    ModelProvider.PERPLEXITY: {
        "pplx-decider-v1.1-27b": ModelPricing(input_per_million=0.02, output_per_million=0.0),
        "pplx-decider-v1-27b": ModelPricing(input_per_million=0.02, output_per_million=0.0),
    },
    # Cloudflare Workers AI Clef decision models, checked 2026-10-10 against the Workers AI pricing
    # page https://developers.cloudflare.com/workers-ai/platform/pricing/ ("@cf/cloudflare/clef |
    # $0.240 per M input tokens" and "@cf/cloudflare/clef-flash | $0.038 per M input tokens") and the
    # model page https://developers.cloudflare.com/workers-ai/models/clef/ ("Clef models do not
    # charge for output tokens"). Workers AI bills these as neurons (21818 and 3455 per M input
    # tokens at $0.011 per 1,000 neurons), which is the same charge as the token price.
    ModelProvider.CLOUDFLARE: {
        "clef": ModelPricing(input_per_million=0.24, output_per_million=0.0),
        "clef-flash": ModelPricing(input_per_million=0.038, output_per_million=0.0),
    },
    # Microsoft-Decision-1 on Microsoft Foundry, checked 2026-10-10 against Microsoft's Azure Retail
    # Prices API (https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices):
    # https://prices.azure.com/api/retail/prices?$filter=productName%20eq%20%27Microsoft%20Decision%20Models%27
    # returns one meter, "Microsoft Decision 1 1M Tokens", at retailPrice 0.042 USD per "1M" in all
    # 37 regions (effective 2026-10-01), with no output meter; Microsoft's announcement
    # https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/introducing-microsoft-decision-1-in-microsoft-foundry-for-decision-and-classific/4562742
    # lists "Input Tokens (#/1M) $0.042 | Output tokens (#/1M) N/A" for the US and EU Datazones. The
    # request `model` is the caller's deployment name, so this row prices only a deployment named
    # microsoft-decision-1.
    ModelProvider.FOUNDRY: {
        "microsoft-decision-1": ModelPricing(input_per_million=0.042, output_per_million=0.0),
    },
    # Liquid AI d1 (System One wire), retrieved 2026-10-10. Liquid publishes no API pricing page
    # (https://www.liquid.ai/pricing covers open-weight licensing only, https://console.liquid.ai/pricing
    # needs a login, and https://docs.liquid.ai/lfm/models/d1 states no rate), so the first-party
    # source is the methodology footnote of Liquid's own d1 announcement, dated 2026-10-05
    # (https://www.liquid.ai/blog/d1-decision-model): "d1's costs use $0.04 per million input
    # tokens"; its "Availability and pricing" section adds "d1 is billed on input tokens only, with no
    # output tokens". Output tokens are always 0 (https://docs.liquid.ai/lfm/models/d1). The
    # longest-prefix match also prices an explicit `d1:free` here.
    ModelProvider.LIQUID: {
        "d1": ModelPricing(input_per_million=0.04, output_per_million=0.0),
    },
    # Baseten Mercury Decide (inception/mercury-decide). Baseten publishes no price for this model:
    # its Model APIs pricing page https://www.baseten.co/pricing/ has no Mercury Decide row and the
    # model page https://www.baseten.co/library/mercury-decide/ states none (both checked
    # 2026-10-10). By the user's decision (2026-10-10), this row uses Inception's published price for
    # Mercury Decide on Inception's own API, retrieved 2026-10-10 from
    # https://docs.inceptionlabs.ai/get-started/models ("Mercury Decide | ~~$0.04~~ → $0.02 | $0 |
    # $0 | v1/decisions", columns input / cached input / output per 1M tokens) and
    # https://docs.inceptionlabs.ai/capabilities/decisions ("Mercury Decide costs $0.02 per million
    # input tokens (50% off the regular $0.04 price). Only input tokens are billed"). The $0.02 rate
    # is promotional: Inception states no end date for the discount (the regular price is $0.04),
    # and Baseten may bill its route at a different rate.
    ModelProvider.BASETEN: {
        "inception/mercury-decide": ModelPricing(input_per_million=0.02, output_per_million=0.0),
    },
    # meraGPT Decider 1 (System One wire), retrieved 2026-10-10 from the models and pricing table
    # https://meragpt.com/docs/models ("decider-1 | sd-1 | 4,096 | $0.04 / 1M | $0.00 / 1M |
    # Available"), the model card https://meragpt.com/models/decider-1 ("input price $0.04 / 1M
    # tokens", "output price $0.00 / 1M tokens"), https://meragpt.com/#pricing, and the public
    # catalogue https://meragpt.com/v1/models ("input_usd_per_million_tokens":0.04,
    # "output_usd_per_million_tokens":0, "aliases":["sd-1","state-decider-1"]). sd-1 is the
    # documented alias of decider-1 and is the id the SDK sends and records.
    ModelProvider.MERAGPT: {
        "sd-1": ModelPricing(input_per_million=0.04, output_per_million=0.0),
    },
    # Celeris celeris-1-decision (System One wire), retrieved 2026-10-10 from the API pricing page
    # https://docs.celeris.ai/pricing.md (columns input / cached input / output): "celeris-1-decision |
    # US$0.04 per million | US$0.04 per million | Free". Cached input costs the input rate, which an
    # unset cache_read rate already bills, so the row sets no cache field.
    ModelProvider.CELERIS: {
        "celeris-1-decision": ModelPricing(input_per_million=0.04, output_per_million=0.0),
    },
    # Nace.AI Drex (System One wire), retrieved 2026-10-10 from the pricing page
    # https://console.nace.ai/docs/drex/reference/pricing ("Per 1M input tokens, drex-v1.0 $ 0.04" and
    # "Per 1M input tokens, drex-v1.5 $ 0.05"; "There is no per-request fee and no charge per
    # question") and the models page https://console.nace.ai/docs/drex/reference/models ("drex-latest
    # is an alias. It currently points to drex-v1.5." and "The response model reports the pinned
    # version that answered, never the alias"), so alias calls are priced on the pinned rows here.
    ModelProvider.NACE: {
        "drex-v1.5": ModelPricing(input_per_million=0.05, output_per_million=0.0),
        "drex-v1.0": ModelPricing(input_per_million=0.04, output_per_million=0.0),
    },
    # Upstage Solar Decide (System One wire, beta), retrieved 2026-10-10 from the model page
    # https://console.upstage.ai/docs/models/solar-decide ("$ 0.1 /1M tokens Input Token", "Free
    # Output Token", "$ 0.1 /1M tokens Cached Token"). Cached tokens cost the input rate, which an
    # unset cache_read rate already bills, so the row sets no cache field.
    ModelProvider.UPSTAGE: {
        "solar-decide": ModelPricing(input_per_million=0.10, output_per_million=0.0),
    },
    # Inception Mercury Decide on Inception's own API (System One body on /decisions), retrieved
    # 2026-10-10 from the models and pricing page https://docs.inceptionlabs.ai/get-started/models
    # ("Mercury Decide | ~~$0.04~~ → $0.02 | $0 | $0 | v1/decisions", columns input / cached input /
    # output per 1M tokens) and https://docs.inceptionlabs.ai/capabilities/decisions ("Mercury Decide
    # costs $0.02 per million input tokens (50% off the regular $0.04 price). Only input tokens are
    # billed"). The $0.02 rate is promotional, with no stated end date; the regular price is $0.04.
    ModelProvider.INCEPTION: {
        "mercury-decide": ModelPricing(input_per_million=0.02, output_per_million=0.0),
    },
    # Hanzo Kai (System One body on /decisions), retrieved 2026-10-10 from the pricing page
    # https://hanzo.ai/pricing ("Kai starter Hanzo's decision model. $0.021 per million input tokens,
    # half of Jev's $0.042. Output is free.") and the decisions docs https://docs.hanzo.ai/docs/decisions
    # ("kai $0.021 per million input tokens ( usage.input_tokens ); output is free").
    ModelProvider.HANZO: {
        "kai": ModelPricing(input_per_million=0.021, output_per_million=0.0),
    },
    # Vansa vansa-3.4 (System One wire), retrieved 2026-10-10 from the pricing page
    # https://vansa.org/pricing ("$0.034" per 1 million input tokens, output-token cost "None", and
    # prepaid credit at "$0.034/1M input tokens" for "Any amount from $1 to $1,000"). This is the
    # prepaid list rate; the monthly plans' lower effective rates are not represented.
    ModelProvider.VANSA: {
        "vansa-3.4": ModelPricing(input_per_million=0.034, output_per_million=0.0),
    },
    # ZooData Instinct (System One wire), retrieved 2026-10-10 from the docs
    # https://instinct.zoowork.ai/docs/ ("instinct US$0.03 per million input tokens", "instinct-dual-4b
    # US$0.01 per million input tokens", "instinct-tuned-4b US$0.01 per million input tokens", and
    # "Output tokens are free on all models"). These are the paid host's rates; calls sent to the
    # free preview host by endpoint override are priced here too.
    ModelProvider.ZOODATA: {
        "instinct": ModelPricing(input_per_million=0.03, output_per_million=0.0),
        "instinct-dual-4b": ModelPricing(input_per_million=0.01, output_per_million=0.0),
        "instinct-tuned-4b": ModelPricing(input_per_million=0.01, output_per_million=0.0),
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
        # Returns exact or longest-prefix pricing for the model, else None. The
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
        prefix_matches = [(key, pricing) for key, pricing in models.items() if canonical_model.startswith(key)]
        if not prefix_matches:
            return None
        return max(prefix_matches, key=lambda item: len(item[0]))[1]

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
    "OPENAI_GPT56_TIER_RATES",
    "PRICING_AS_OF",
    "PRICING_SOURCE_URL",
    "PROVIDER_PRICING",
]
