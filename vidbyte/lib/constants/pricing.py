"""FILE: vidbyte/lib/constants/pricing.py

PURPOSE: Defines fixed provider billing multipliers that apply to every model of a provider, so no per-model pricebook field is needed for them.
ROLE IN CODEBASE: Read by vidbyte/agents/pricing/anthropic.py (AnthropicUsage.cost_usd) to price Anthropic 1-hour prompt-cache writes.
ARCHITECTURE NOTE: Immutable constants only; per-model USD rates stay in vidbyte/lib/registries/pricing.py and the cost math stays in vidbyte/agents/pricing/.
COMMON MODIFICATION PATTERNS: Change a multiplier only when the provider's own pricing page changes it, citing that page in the constant's @intent comment.
KNOWN EDGE CASES: The 1-hour write multiplier scales the active input rate, so a prompt over a model's length tier (Claude Haiku 5.5 over 100K) doubles the tiered rate, not the base one.
RELATED DOCS: https://platform.claude.com/docs/en/about-claude/pricing; https://platform.claude.com/docs/en/build-with-claude/prompt-caching
TESTS: tests/features/sdk_model_catalog/test_catalog_pricing_contract.py
"""

from __future__ import annotations

# @intent anthropic-1h-cache-write-is-2x-input
# Anthropic bills a 1-hour cache write at "2x base input price" for every
# Claude model (https://platform.claude.com/docs/en/about-claude/pricing);
# the pricebook's cache_write rate is the 5-minute write (1.25x input).
ANTHROPIC_CACHE_WRITE_1H_INPUT_MULTIPLIER: float = 2.0

__all__ = ["ANTHROPIC_CACHE_WRITE_1H_INPUT_MULTIPLIER"]
