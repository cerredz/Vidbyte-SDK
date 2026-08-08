"""Context Protocol Header

Description:
    Feature tests for agent usage parsing, pricing, and provider strictness.
Purpose:
    Locks the behavior of the PR #304 review-comment resolutions: the shared
    nested-payload accessor and derived uncached-input property, the shared usage
    class for OpenAI-compatible providers, and the strictly-typed pricing registry.
Architecture:
    - PricingBaseTests: nested_int + uncached_input_tokens on ProviderUsage.
    - CompatibleProviderTests: xai/glm/minimax/deepseek route through one class.
    - PricingRegistryStrictnessTests: resolve/register take only ModelProvider.
    - OperationPricingTableTests: no operation rate is off by a per-1,000 factor.
Relations:
    Exercises vidbyte/agents/pricing/*, vidbyte/lib/registries/pricing.py, and
    vidbyte/lib/registries/operation_pricing.py.
Similar Files:
    - tests/test_agent_registry.py
"""

from __future__ import annotations

import unittest

from vidbyte.agents.pricing import (
    ChatCompletionUsage,
    DeepSeekUsage,
    GLMUsage,
    MiniMaxUsage,
    OpenAIUsage,
    OpenRouterUsage,
    XAIUsage,
)
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.registries.operation_pricing import OPERATION_PRICING, OperationPricingRegistry
from vidbyte.lib.registries.pricing import ModelPricing, ModelPricingRegistry

# Floor for any non-zero operation rate. Vendors publish per-1,000-unit figures, so
# the recurring defect is dividing by 1,000,000 instead of 1,000. The smallest real
# rate in the table is Firecrawl's 0.00083/page, leaving 83x of headroom.
_MIN_PLAUSIBLE_RATE_USD = 1e-5


class PricingBaseTests(unittest.TestCase):
    def test_nested_int_reads_details_and_tolerates_absence(self) -> None:
        usage = OpenAIUsage.from_usage_payload(
            {
                "input_tokens": 10_000,
                "output_tokens": 500,
                "total_tokens": 10_500,
                "input_tokens_details": {"cached_tokens": 2_000},
                "output_tokens_details": {"reasoning_tokens": 120},
            }
        )
        assert usage is not None
        self.assertEqual(usage.cached_input_tokens, 2_000)
        self.assertEqual(usage.reasoning_tokens, 120)

        # Missing/malformed detail blocks resolve to None instead of raising.
        bare = OpenAIUsage.from_usage_payload({"input_tokens": 100, "output_tokens": 10, "total_tokens": 110})
        assert bare is not None
        self.assertIsNone(bare.cached_input_tokens)
        self.assertIsNone(bare.reasoning_tokens)

        malformed = OpenAIUsage.from_usage_payload(
            {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110, "input_tokens_details": 7}
        )
        assert malformed is not None
        self.assertIsNone(malformed.cached_input_tokens)

    def test_uncached_input_tokens_is_input_minus_cached_subset(self) -> None:
        usage = OpenAIUsage(input_tokens=10_000, output_tokens=500, total_tokens=10_500, cached_input_tokens=2_000)
        self.assertEqual(usage.uncached_input_tokens, 8_000)

        # Cached is clamped to input so uncached never goes negative.
        over = OpenAIUsage(input_tokens=1_000, cached_input_tokens=5_000)
        self.assertEqual(over.uncached_input_tokens, 0)

        self.assertIsNone(OpenAIUsage(input_tokens=None).uncached_input_tokens)

    def test_subset_cost_prices_uncached_and_cached_at_distinct_rates(self) -> None:
        pricing = ModelPricing(input_per_million=2.5, output_per_million=15.0, cache_read_per_million=0.25)
        usage = OpenAIUsage(input_tokens=10_000, output_tokens=500, total_tokens=10_500, cached_input_tokens=2_000)
        # (8000 * 2.5 + 2000 * 0.25 + 500 * 15) / 1e6
        self.assertAlmostEqual(usage.cost_usd(pricing), 0.028)

    def test_no_token_fields_parses_to_none(self) -> None:
        self.assertIsNone(OpenAIUsage.from_usage_payload({"input_tokens_details": {"cached_tokens": 5}}))


class CompatibleProviderTests(unittest.TestCase):
    def test_named_aliases_share_one_response_shape_class(self) -> None:
        for alias in (XAIUsage, DeepSeekUsage, GLMUsage, MiniMaxUsage):
            self.assertIs(alias, ChatCompletionUsage)

    def test_usage_class_dispatches_compatible_providers(self) -> None:
        for provider in (ModelProvider.XAI, ModelProvider.GLM, ModelProvider.MINIMAX, ModelProvider.DEEPSEEK, ModelProvider.META, ModelProvider.MISTRAL):
            usage_cls = provider.usage_class()
            self.assertIs(usage_cls, ChatCompletionUsage)
            usage = usage_cls.from_usage_payload({"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120})
            self.assertIsInstance(usage, ChatCompletionUsage)

    def test_cached_input_reads_first_reported_source(self) -> None:
        # DeepSeek reports prompt_cache_hit_tokens rather than the nested detail block.
        usage = ChatCompletionUsage.from_usage_payload(
            {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120, "prompt_cache_hit_tokens": 40}
        )
        assert usage is not None
        self.assertEqual(usage.cached_input_tokens, 40)


class OpenRouterUsageTests(unittest.TestCase):
    def test_provider_reported_cost_wins_over_table_math(self) -> None:
        usage = OpenRouterUsage.from_usage_payload(
            {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120, "cost": 0.0042}
        )
        assert usage is not None
        self.assertEqual(usage.cost_usd(None), 0.0042)

    def test_non_numeric_cost_is_rejected(self) -> None:
        usage = OpenRouterUsage.from_usage_payload(
            {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120, "cost": True}
        )
        assert usage is not None
        self.assertIsNone(usage.reported_cost)


class PricingRegistryStrictnessTests(unittest.TestCase):
    def test_resolve_requires_model_provider_enum(self) -> None:
        registry = ModelPricingRegistry.default()
        self.assertIsNotNone(registry.resolve(ModelProvider.OPENAI, "gpt-5.4"))
        # A raw provider string is no longer coerced; strict typing yields None.
        self.assertIsNone(registry.resolve("openai", "gpt-5.4"))  # type: ignore[arg-type]

    def test_register_rejects_non_enum_provider(self) -> None:
        registry = ModelPricingRegistry.default()
        pricing = ModelPricing(input_per_million=1.0, output_per_million=2.0)
        with self.assertRaises(ConfigurationError):
            registry.register("openai", "custom-model", pricing)  # type: ignore[arg-type]
        registry.register(ModelProvider.OPENAI, "custom-model", pricing)
        self.assertIs(registry.resolve(ModelProvider.OPENAI, "custom-model"), pricing)


class OperationPricingTableTests(unittest.TestCase):
    def test_no_rate_is_implausibly_small(self) -> None:
        # Guards the whole table against a per-1,000 figure being divided twice.
        for key, pricing in OPERATION_PRICING.items():
            for field, rate in (("usd_fixed", pricing.usd_fixed), ("usd_per_unit", pricing.usd_per_unit)):
                if rate:
                    self.assertGreaterEqual(rate, _MIN_PLAUSIBLE_RATE_USD, f"{key} {field}={rate} looks off by a per-1,000 factor.")

    def test_free_operations_price_at_zero_rather_than_none(self) -> None:
        # The floor above skips zero rates, so confirm free providers really are zero.
        registry = OperationPricingRegistry.default()
        for operation, provider in (("search", "semantic_scholar"), ("fetch", "direct_http")):
            pricing = registry.resolve(operation, provider)
            assert pricing is not None
            self.assertEqual(pricing.cost_usd(25), 0.0)

    def test_parallel_rates_convert_from_the_per_thousand_column(self) -> None:
        # Pins the divisor: Parallel's "Cost ($/1000)" value of 1 is $0.001 per unit.
        registry = OperationPricingRegistry.default()
        turbo = registry.resolve("search", "parallel", "turbo")
        assert turbo is not None
        self.assertAlmostEqual(turbo.usd_fixed, 0.001)
        self.assertAlmostEqual(turbo.usd_per_unit, 0.001)
        pro = registry.resolve("search", "parallel", "pro")
        assert pro is not None
        self.assertAlmostEqual(pro.usd_fixed, 0.005)
        extract = registry.resolve("fetch", "parallel", "default")
        assert extract is not None
        self.assertAlmostEqual(extract.usd_per_unit, 0.001)

    def test_parallel_search_bills_a_base_request_plus_results_above_ten(self) -> None:
        # Twenty turbo results cost the $0.001 request plus $0.001 for each of ten extras.
        registry = OperationPricingRegistry.default()
        turbo = registry.resolve("search", "parallel", "turbo")
        assert turbo is not None
        self.assertAlmostEqual(turbo.cost_usd(20), 0.011)
        self.assertAlmostEqual(turbo.cost_usd(10), 0.001)


if __name__ == "__main__":
    unittest.main()
