"""FILE: vidbyte/lib/constants/pricing.py

PURPOSE: Defines fixed provider billing multipliers and per-request fees that apply to every model of a provider, so no per-model pricebook field is needed for them.
ROLE IN CODEBASE: Read by vidbyte/agents/pricing/anthropic.py (AnthropicUsage.cost_usd) to price Anthropic 1-hour prompt-cache writes, US-only inference, and server-side web searches.
ARCHITECTURE NOTE: Immutable constants only; per-model USD rates stay in vidbyte/lib/registries/pricing.py and the cost math stays in vidbyte/agents/pricing/.
COMMON MODIFICATION PATTERNS: Change a multiplier only when the provider's own pricing page changes it, citing that page in the constant's @intent comment.
KNOWN EDGE CASES: The 1-hour write multiplier scales the active input rate, so a prompt over a model's length tier (Claude Haiku 5.5 over 100K) doubles the tiered rate, not the base one. The US-only multiplier scales the whole call after fast mode, caching and that tier.
RELATED DOCS: https://platform.claude.com/docs/en/about-claude/pricing; https://platform.claude.com/docs/en/build-with-claude/prompt-caching; https://platform.claude.com/docs/en/manage-claude/data-residency
TESTS: tests/features/sdk_model_catalog/test_catalog_pricing_contract.py; tests/features/sdk_model_usage/test_anthropic_price_modifiers.py; tests/features/sdk_model_usage/test_anthropic_web_search_pricing.py
"""

from __future__ import annotations

# @intent anthropic-1h-cache-write-is-2x-input
# Anthropic bills a 1-hour cache write at "2x base input price" for every
# Claude model (https://platform.claude.com/docs/en/about-claude/pricing);
# the pricebook's cache_write rate is the 5-minute write (1.25x input).
ANTHROPIC_CACHE_WRITE_1H_INPUT_MULTIPLIER: float = 2.0

# @intent anthropic-us-inference-is-1-1x-every-bucket
# US-only inference (usage.inference_geo "us") on Claude 4.6 and later
# "incurs a 1.1x multiplier on all token pricing categories, including
# input tokens, output tokens, cache writes, and cache reads", stacking
# with fast mode, caching and Haiku 5.5's over-100K prices
# (https://platform.claude.com/docs/en/about-claude/pricing). Global
# routing and older models ("not_available") bill at 1x.
ANTHROPIC_US_INFERENCE_GEO_MULTIPLIER: float = 1.1

# @intent anthropic-web-search-is-a-flat-per-request-fee
# "Web search is available on the Claude API for $10 USD per 1,000
# searches, plus standard token costs", counted by
# usage.server_tool_use.web_search_requests; a search that errors is not
# billed (https://platform.claude.com/docs/en/about-claude/pricing, "Web
# search tool"). The fee is not a token price, so data residency, fast
# mode and Haiku 5.5's long-context prices never scale it. Web fetch has
# no fee.
ANTHROPIC_WEB_SEARCH_USD_PER_REQUEST: float = 0.01

__all__ = ["ANTHROPIC_CACHE_WRITE_1H_INPUT_MULTIPLIER", "ANTHROPIC_US_INFERENCE_GEO_MULTIPLIER", "ANTHROPIC_WEB_SEARCH_USD_PER_REQUEST"]
