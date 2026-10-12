"""FILE: tests/features/sdk_model_catalog/test_catalog_pricing_contract.py

PURPOSE: Pin the October 2026 catalog refresh: every added model validates, is detected as text, and prices at its first-party rate.
ROLE IN CODEBASE: Exercises vidbyte/lib/constants/runners.py, vidbyte/lib/enums/model_modality.py, vidbyte/lib/registries/{models,pricing}.py and vidbyte/agents/pricing/anthropic.py.
ARCHITECTURE NOTE: Expected rates are copied from the provider pages cited in pricing.py; parsing, lookup and cost math stay production code.
FUNCTION INVENTORY: catalog tests (validation, wrong provider, parity, modality); rate tests (exact rates, exact keys, dated ids, corrections, metadata); threshold tests (xAI, OpenAI, Anthropic Haiku 5.5); tracker integration tests.
COMMON MODIFICATION PATTERNS: When a provider changes a price, change EXPECTED_RATES and pricing.py together, citing the provider page.
WHAT NOT TO DO IN THIS FILE: 1. Do not call providers. 2. Do not derive expected rates from PROVIDER_PRICING; that would make every rate test vacuous.
KNOWN EDGE CASES: Longest-prefix lookup silently prices claude-sonnet-5-5 as claude-sonnet-5 when its own row is missing; Anthropic input_tokens excludes cache buckets.
RELATED DOCS: tests/features/sdk_model_catalog/FEATURE.md and docs/design/model-catalog-pricing-refresh.md.
TESTS: python -m pytest -q tests/features/sdk_model_catalog
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from vidbyte.agents.pricing import AnthropicUsage, UsageTracker
from vidbyte.lib.agents.modality_detector import ModalityDetector
from vidbyte.lib.constants.runners import MODEL_PROVIDER_RUNNER_TYPE_MAP, MODEL_RUNNER_TYPE_MAP, RUNNER_TYPE_TEXT
from vidbyte.lib.enums import ModelModality, ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.registries.models import ProviderModelRegistry
from vidbyte.lib.registries.pricing import DEEPSEEK_TIME_OF_DAY_RATES, OPENAI_GPT56_TIER_RATES, OPENAI_GPT6_TIER_RATES, PRICING_AS_OF, PROVIDER_PRICING, ModelPricingRegistry

OPENAI, ANTHROPIC, GEMINI, XAI = ModelProvider.OPENAI, ModelProvider.ANTHROPIC, ModelProvider.GEMINI, ModelProvider.XAI
DEEPSEEK, GLM, KIMI, META, MISTRAL = ModelProvider.DEEPSEEK, ModelProvider.GLM, ModelProvider.KIMI, ModelProvider.META, ModelProvider.MISTRAL

# (input, output, cache_read, cache_write, threshold, input_over,
# output_over, inclusive): each provider's regular rate from its own
# page, never a promotional or sale price.
EXPECTED_RATES: dict[tuple[ModelProvider, str], tuple[float, float, float | None, float | None, int | None, float | None, float | None, bool]] = {
    (OPENAI, "gpt-6-astra"): (10.0, 50.0, 1.0, 12.5, 272_000, 20.0, 75.0, False),
    (OPENAI, "gpt-6.1-sol"): (2.0, 10.0, 0.1, 2.5, 272_000, 4.0, 15.0, False),
    (OPENAI, "gpt-6-sol"): (2.0, 10.0, 0.2, 2.5, 272_000, 4.0, 15.0, False),
    (OPENAI, "gpt-6-luna"): (0.1, 0.5, 0.01, 0.125, 272_000, 0.2, 0.75, False),
    (OPENAI, "gpt-5.6-sol"): (5.0, 30.0, 0.5, 6.25, 272_000, 10.0, 45.0, False),
    (ANTHROPIC, "claude-fable-5-1"): (10.0, 50.0, 0.25, 12.5, None, None, None, False),
    (ANTHROPIC, "claude-mythos-5-1"): (10.0, 50.0, 0.25, 12.5, None, None, None, False),
    (ANTHROPIC, "claude-opus-5-5"): (4.0, 20.0, 0.2, 5.0, None, None, None, False),
    (ANTHROPIC, "claude-sonnet-5-5"): (2.0, 10.0, 0.1, 2.5, None, None, None, False),
    (ANTHROPIC, "claude-haiku-5-5"): (0.1, 0.5, 0.01, 0.125, 100_000, 0.5, 2.5, False),
    (ANTHROPIC, "claude-opus-5"): (5.0, 25.0, 0.5, 6.25, None, None, None, False),
    (ANTHROPIC, "claude-fable-5"): (10.0, 50.0, 1.0, 12.5, None, None, None, False),
    (ANTHROPIC, "claude-mythos-5"): (10.0, 50.0, 1.0, 12.5, None, None, None, False),
    (GEMINI, "gemini-3.8-flash"): (1.5, 7.5, 0.15, None, None, None, None, False),
    (GEMINI, "gemini-3.6-flash"): (1.5, 7.5, 0.15, None, None, None, None, False),
    (GEMINI, "gemini-3.5-flash"): (1.5, 7.5, 0.15, None, None, None, None, False),
    (GEMINI, "gemini-3.5-flash-lite"): (0.3, 2.5, 0.03, None, None, None, None, False),
    (GEMINI, "gemini-3.1-flash-lite"): (0.25, 1.5, 0.025, None, None, None, None, False),
    (XAI, "grok-4.7"): (2.0, 6.0, 0.5, None, 200_000, 4.0, 12.0, True),
    (XAI, "grok-4.6"): (2.0, 6.0, 0.5, None, 200_000, 4.0, 12.0, True),
    (DEEPSEEK, "deepseek-flash"): (0.3, 1.2, 0.006, None, None, None, None, False),
    (DEEPSEEK, "deepseek-v4-flash"): (0.3, 1.2, 0.006, None, None, None, None, False),
    (DEEPSEEK, "deepseek-v4-pro"): (1.32, 3.96, 0.044, None, None, None, None, False),
    (GLM, "glm-5.3"): (1.4, 4.4, 0.26, None, None, None, None, False),
    (GLM, "glm-5.3-flash"): (0.15, 0.5, 0.03, None, None, None, None, False),
    (GLM, "glm-5.3-flashx"): (0.37, 1.25, 0.075, None, None, None, None, False),
    (KIMI, "kimi-k3"): (3.0, 15.0, 0.3, 3.0, None, None, None, False),
    (KIMI, "kimi-k2.6"): (0.95, 4.0, 0.16, None, None, None, None, False),
    (META, "muse-spark-1.3"): (1.25, 4.25, 0.15, None, None, None, None, False),
    (META, "muse-spark-1.2"): (1.25, 4.25, 0.15, None, None, None, None, False),
    (META, "muse-spark-1.3-contributor"): (0.1, 0.2, 0.002, None, None, None, None, False),
    (META, "muse-spark-1.2-contributor"): (0.1, 0.2, 0.002, None, None, None, None, False),
    (MISTRAL, "mistral-medium-3-5"): (1.5, 7.5, None, None, None, None, None, False),
    (MISTRAL, "mistral-medium-latest"): (1.5, 7.5, None, None, None, None, None, False),
    (MISTRAL, "mistral-small-2603"): (0.15, 0.6, None, None, None, None, None, False),
    (MISTRAL, "mistral-small-latest"): (0.15, 0.6, None, None, None, None, None, False),
    (MISTRAL, "mistral-large-2512"): (0.5, 1.5, None, None, None, None, None, False),
    (MISTRAL, "mistral-large-latest"): (0.5, 1.5, None, None, None, None, None, False),
    (MISTRAL, "mistral-large-4"): (1.36, 4.18, 0.14, None, None, None, None, False),
    (MISTRAL, "mistral-large-4-0"): (1.36, 4.18, 0.14, None, None, None, None, False),
}

# Models this refresh adds to the runner catalog, by provider.
ADDED_MODELS: dict[ModelProvider, tuple[str, ...]] = {
    OPENAI: ("gpt-6-astra", "gpt-6.1-sol", "gpt-6-sol", "gpt-6-luna"),
    ANTHROPIC: ("claude-fable-5-1", "claude-mythos-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5"),
    GEMINI: ("gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"),
    XAI: ("grok-4.7", "grok-4.6"),
    DEEPSEEK: ("deepseek-flash",),
    GLM: ("glm-5.3", "glm-5.3-flash", "glm-5.3-flashx"),
    META: ("muse-spark-1.3", "muse-spark-1.2", "muse-spark-1.3-contributor", "muse-spark-1.2-contributor"),
    MISTRAL: ("mistral-medium-3-5", "mistral-small-2603", "mistral-large-4", "mistral-large-4-0"),
}
ADDED_PAIRS = [(provider, model) for provider, models in ADDED_MODELS.items() for model in models]

# A new model whose id extends an older priced key, with that older key.
PREFIX_SIBLINGS = [
    (ANTHROPIC, "claude-sonnet-5-5", "claude-sonnet-5"),
    (ANTHROPIC, "claude-opus-5-5", "claude-opus-5"),
    (ANTHROPIC, "claude-fable-5-1", "claude-fable-5"),
    (ANTHROPIC, "claude-mythos-5-1", "claude-mythos-5"),
    (GLM, "glm-5.3", "glm-5"),
    (GLM, "glm-5.3-flash", "glm-5.3"),
    (META, "muse-spark-1.3-contributor", "muse-spark-1.3"),
    (MISTRAL, "mistral-large-4-0", "mistral-large-4"),
]


def _resolve(provider: ModelProvider, model: str):
    # Looks a model up through the same registry UsageTracker uses by
    # default.
    return ModelPricingRegistry.default().resolve(provider, model)


@pytest.mark.parametrize(("provider", "model"), ADDED_PAIRS)
def test_every_added_model_validates_under_its_own_provider(provider: ModelProvider, model: str) -> None:
    # [Hidden Assumption] Strict validation accepts each added model
    # under the provider that serves it.
    assert ProviderModelRegistry.STRICT_MODEL_VALIDATION is True
    ProviderModelRegistry.validate_provider_model_pair(provider, model)
    assert ProviderModelRegistry.is_supported_model(provider, model)


@pytest.mark.parametrize(("provider", "model", "wrong"), [(ANTHROPIC, "claude-opus-5-5", OPENAI), (OPENAI, "gpt-6.1-sol", ANTHROPIC), (DEEPSEEK, "deepseek-flash", GLM)])
def test_an_added_model_declared_under_the_wrong_provider_is_rejected(provider: ModelProvider, model: str, wrong: ModelProvider) -> None:
    # [Hidden Assumption] Ownership is checked, so a model cannot be
    # sent to a vendor that does not serve it.
    with pytest.raises(ConfigurationError, match="is registered under provider"):
        ProviderModelRegistry.validate_provider_model_pair(wrong, model)


def test_openai_publishes_no_bare_gpt_6_alias_so_none_is_accepted() -> None:
    # [Edge Case] gpt-6 is not a published OpenAI model id, unlike the
    # gpt-5.6 alias.
    with pytest.raises(ConfigurationError, match="Unrecognized model"):
        ProviderModelRegistry.validate_model("gpt-6")


@pytest.mark.parametrize(("provider", "model"), ADDED_PAIRS)
def test_qualified_and_bare_runner_maps_list_each_added_model_as_text(provider: ModelProvider, model: str) -> None:
    # [Hidden Failure] A model in only one map passes validation but
    # fails runner inference.
    assert MODEL_PROVIDER_RUNNER_TYPE_MAP[f"{provider.value}/{model}"] == RUNNER_TYPE_TEXT
    assert MODEL_RUNNER_TYPE_MAP[model] == RUNNER_TYPE_TEXT


@pytest.mark.parametrize(("provider", "model"), ADDED_PAIRS)
def test_every_added_model_is_detected_as_text(provider: ModelProvider, model: str) -> None:
    # [Edge Case] Each added model routes to the text runner.
    assert ModalityDetector.detect_modality(model) is ModelModality.TEXT


@pytest.mark.parametrize(("provider", "model"), sorted(EXPECTED_RATES, key=lambda item: (item[0].value, item[1])))
def test_every_priced_refresh_model_passes_strict_validation(provider: ModelProvider, model: str) -> None:
    # [Hidden Failure] A price row for a model strict validation rejects
    # can never be billed, so every row this refresh pins is reachable.
    ProviderModelRegistry.validate_provider_model_pair(provider, model)


def test_every_added_catalog_model_has_an_expected_rate() -> None:
    # [Hidden Assumption] No model is catalogued by this refresh without
    # a pinned first-party price.
    assert set(ADDED_PAIRS) <= set(EXPECTED_RATES)


@pytest.mark.parametrize(("provider", "model"), sorted(EXPECTED_RATES, key=lambda item: (item[0].value, item[1])))
def test_each_refreshed_model_prices_at_its_first_party_rate(provider: ModelProvider, model: str) -> None:
    # [Silent Failure] A wrong rate still returns a number; every field
    # is compared to the provider page.
    pricing = _resolve(provider, model)
    expected = EXPECTED_RATES[(provider, model)]
    actual = (pricing.input_per_million, pricing.output_per_million, pricing.cache_read_per_million, pricing.cache_write_per_million, pricing.threshold_tokens, pricing.input_over_threshold_per_million, pricing.output_over_threshold_per_million, pricing.threshold_inclusive)
    assert actual == expected


@pytest.mark.parametrize(("provider", "model"), sorted(EXPECTED_RATES, key=lambda item: (item[0].value, item[1])))
def test_each_refreshed_model_resolves_through_its_own_exact_key(provider: ModelProvider, model: str) -> None:
    # [Silent Failure] Longest-prefix fallback would hide a missing row
    # behind an older sibling's rate.
    assert _resolve(provider, model) is PROVIDER_PRICING[provider][model]


@pytest.mark.parametrize(("provider", "model", "older"), PREFIX_SIBLINGS)
def test_a_new_model_never_prices_as_the_older_key_its_id_extends(provider: ModelProvider, model: str, older: str) -> None:
    # [Silent Failure] claude-sonnet-5-5 starts with claude-sonnet-5,
    # and the two differ in cache rate.
    assert _resolve(provider, model) is not PROVIDER_PRICING[provider][older]


@pytest.mark.parametrize(("provider", "versioned", "base"), [(ANTHROPIC, "claude-opus-5-5-20260922", "claude-opus-5-5"), (XAI, "grok-4.7-0915", "grok-4.7"), (GLM, "glm-5.3-flash-250930", "glm-5.3-flash")])
def test_a_versioned_response_id_prices_at_its_base_model(provider: ModelProvider, versioned: str, base: str) -> None:
    # [Edge Case] Responses can name a dated snapshot; the longest
    # matching key must be the model itself.
    assert _resolve(provider, versioned) is PROVIDER_PRICING[provider][base]


def test_gpt_5_6_sol_row_and_tiers_carry_the_regular_not_promotional_rate() -> None:
    # [Silent Failure] OpenAI's $4 / $20 promotion lapses; the row and
    # its tier metadata both keep the regular $5 / $30 rate.
    tiers = OPENAI_GPT56_TIER_RATES["gpt-5.6-sol"]
    assert (tiers["standard"]["input_per_million"], tiers["standard"]["output_per_million"]) == (5.0, 30.0)
    assert (tiers["batch"]["input_per_million"], tiers["flex"]["output_per_million"]) == (2.5, 15.0)
    assert (tiers["fast"]["input_per_million"], tiers["fast"]["output_per_million"]) == (10.0, 60.0)
    assert _resolve(OPENAI, "gpt-5.6-sol").tier_rates is tiers


def test_gpt_6_tier_metadata_has_every_published_tier() -> None:
    # [Silent Failure] Ultrafast exists only for Astra and 6.1 Sol;
    # every model has the other four tiers.
    for model, tiers in OPENAI_GPT6_TIER_RATES.items():
        assert {"standard", "batch", "flex", "fast"} <= set(tiers), model
        assert ("ultrafast" in tiers) is (model in {"gpt-6-astra", "gpt-6.1-sol"}), model
        assert tiers["standard"]["input_per_million"] == _resolve(OPENAI, model).input_per_million
    assert OPENAI_GPT6_TIER_RATES["gpt-6-astra"]["ultrafast"]["output_per_million"] == 300.0
    assert OPENAI_GPT6_TIER_RATES["gpt-6.1-sol"]["batch"]["cached_input_per_million"] == 0.05


def test_deepseek_rows_carry_the_peak_rate_and_off_peak_metadata() -> None:
    # [Hidden Assumption] The table bills the peak rate; off-peak is
    # exactly half, kept as metadata.
    for model in ("deepseek-flash", "deepseek-v4-pro"):
        rates = DEEPSEEK_TIME_OF_DAY_RATES[model]
        assert _resolve(DEEPSEEK, model).input_per_million == rates["peak"]["input_per_million"]
        for field in ("input_per_million", "cached_input_per_million", "output_per_million"):
            assert rates["off_peak"][field] == pytest.approx(rates["peak"][field] / 2)
    assert _resolve(DEEPSEEK, "deepseek-v4-flash").tier_rates is DEEPSEEK_TIME_OF_DAY_RATES["deepseek-flash"]


@pytest.mark.parametrize(("provider", "routed", "target"), [(GEMINI, "gemini-3.5-flash", "gemini-3.6-flash"), (DEEPSEEK, "deepseek-v4-flash", "deepseek-flash")])
def test_a_deprecated_name_bills_as_the_model_the_vendor_routes_it_to(provider: ModelProvider, routed: str, target: str) -> None:
    # [Hidden Assumption] A routed legacy name is billed at the serving
    # model's rate, not its old list price.
    old, new = _resolve(provider, routed), _resolve(provider, target)
    assert (old.input_per_million, old.output_per_million, old.cache_read_per_million) == (new.input_per_million, new.output_per_million, new.cache_read_per_million)


@pytest.mark.parametrize(("prompt_tokens", "expected_input_rate"), [(199_999, 2.0), (200_000, 4.0), (200_001, 4.0)])
def test_grok_4_7_high_tier_starts_at_exactly_200k_prompt_tokens(prompt_tokens: int, expected_input_rate: float) -> None:
    # [Edge Case] xAI bills the higher rate once a prompt "reaches"
    # 200k, so the boundary is inclusive.
    usage = XAI.usage_class().from_usage_payload({"prompt_tokens": prompt_tokens, "completion_tokens": 0})
    assert usage.cost_usd(_resolve(XAI, "grok-4.7")) == pytest.approx(prompt_tokens * expected_input_rate / 1_000_000)


@pytest.mark.parametrize(("input_tokens", "expected_input_rate"), [(272_000, 10.0), (272_001, 20.0)])
def test_gpt_6_astra_long_tier_starts_above_272k_input_tokens(input_tokens: int, expected_input_rate: float) -> None:
    # [Edge Case] OpenAI's long-context tier applies to prompts with
    # more than 272K input tokens.
    usage = OPENAI.usage_class().from_usage_payload({"input_tokens": input_tokens, "output_tokens": 0})
    assert usage.cost_usd(_resolve(OPENAI, "gpt-6-astra")) == pytest.approx(input_tokens * expected_input_rate / 1_000_000)


def test_haiku_5_5_cache_heavy_prompt_over_100k_bills_the_high_tier() -> None:
    # [Silent Failure] 10K uncached plus 140K cache reads is a 150K
    # prompt, so every bucket bills at 5x.
    usage = AnthropicUsage(input_tokens=10_000, output_tokens=2_000, cache_read_input_tokens=140_000, cache_creation_input_tokens=0)
    expected = (10_000 * 0.5 + 140_000 * 0.05 + 2_000 * 2.5) / 1_000_000
    assert usage.cost_usd(_resolve(ANTHROPIC, "claude-haiku-5-5")) == pytest.approx(expected)


def test_haiku_5_5_prompt_of_exactly_100k_bills_the_base_tier() -> None:
    # [Edge Case] Anthropic raises the price only for prompts "over
    # 100,000 tokens".
    usage = AnthropicUsage(input_tokens=50_000, output_tokens=1_000, cache_read_input_tokens=30_000, cache_creation_input_tokens=20_000)
    expected = (50_000 * 0.1 + 30_000 * 0.01 + 20_000 * 0.125 + 1_000 * 0.5) / 1_000_000
    assert usage.cost_usd(_resolve(ANTHROPIC, "claude-haiku-5-5")) == pytest.approx(expected)


def test_haiku_5_5_over_threshold_cache_rates_match_the_published_ones() -> None:
    # [Silent Failure] Over 100K Anthropic lists cache reads at $0.05
    # and 5-minute writes at $0.625.
    reads = AnthropicUsage(input_tokens=0, output_tokens=0, cache_read_input_tokens=1_000_000, cache_creation_input_tokens=0)
    writes = AnthropicUsage(input_tokens=0, output_tokens=0, cache_read_input_tokens=0, cache_creation_input_tokens=1_000_000)
    pricing = _resolve(ANTHROPIC, "claude-haiku-5-5")
    assert reads.cost_usd(pricing) == pytest.approx(0.05)
    assert writes.cost_usd(pricing) == pytest.approx(0.625)


@pytest.mark.parametrize("cache_read", [0, 900_000])
def test_an_anthropic_model_without_a_tier_prices_the_same_at_any_prompt_size(cache_read: int) -> None:
    # [Hidden Failure] The threshold change must not alter models that
    # publish no prompt-length tier.
    usage = AnthropicUsage(input_tokens=100_000, output_tokens=0, cache_read_input_tokens=cache_read, cache_creation_input_tokens=0)
    assert usage.cost_usd(_resolve(ANTHROPIC, "claude-opus-5-5")) == pytest.approx((100_000 * 4.0 + cache_read * 0.2) / 1_000_000)


def test_anthropic_usage_without_token_fields_uses_base_rates() -> None:
    # [Edge Case] A record with only output tokens has no prompt length
    # and so no tier.
    usage = AnthropicUsage(output_tokens=1_000)
    assert usage.cost_usd(_resolve(ANTHROPIC, "claude-haiku-5-5")) == pytest.approx(1_000 * 0.5 / 1_000_000)


def test_every_rate_in_the_pricebook_is_finite_and_non_negative() -> None:
    # [Hidden Failure] A typo such as a negative or NaN rate would
    # corrupt every rollup that touches it.
    for provider, models in PROVIDER_PRICING.items():
        for model, pricing in models.items():
            for value in (pricing.input_per_million, pricing.output_per_million, pricing.cache_read_per_million, pricing.cache_write_per_million, pricing.input_over_threshold_per_million, pricing.output_over_threshold_per_million):
                assert value is None or (math.isfinite(value) and value >= 0), (provider, model, value)


def test_every_provider_default_text_model_is_priced() -> None:
    # [Hidden Assumption] Mistral's default used to resolve to no price;
    # OpenRouter bills per response by design.
    for provider, model in ProviderModelRegistry.DEFAULT_PROVIDER_MODELS.items():
        if ModalityDetector.detect_modality(model) is not ModelModality.TEXT or provider is ModelProvider.OPENROUTER:
            continue
        assert _resolve(provider, model) is not None, (provider, model)


def test_the_pricebook_vintage_names_this_refresh() -> None:
    # [Hidden Failure] Changed rates under an old vintage would let a
    # backend run resume on new prices.
    assert PRICING_AS_OF == "2026-10-11"


def test_tracker_records_haiku_5_5_cache_heavy_call_at_the_high_tier() -> None:
    # [Silent Failure] End to end through UsageTracker: parser, registry
    # and tier must agree.
    response = SimpleNamespace(provider=ANTHROPIC, model="claude-haiku-5-5", usage={"input_tokens": 1_000, "output_tokens": 0, "cache_read_input_tokens": 120_000, "cache_creation_input_tokens": 0})
    record = UsageTracker().record_call(response)
    assert record is not None
    assert record.cost_usd == pytest.approx((1_000 * 0.5 + 120_000 * 0.05) / 1_000_000)


def test_tracker_records_gpt_6_1_sol_cached_input_at_its_own_cache_rate() -> None:
    # [Silent Failure] GPT-6.1 Sol caches at $0.10, half of GPT-6 Sol's
    # $0.20, below the 272K long tier.
    response = SimpleNamespace(provider=OPENAI, model="gpt-6.1-sol", usage={"input_tokens": 200_000, "output_tokens": 0, "input_tokens_details": {"cached_tokens": 200_000}})
    record = UsageTracker().record_call(response)
    assert record is not None
    assert record.cost_usd == pytest.approx(200_000 * 0.1 / 1_000_000)


def test_tracker_doubles_gpt_6_1_sol_cache_rate_past_the_long_tier() -> None:
    # [Edge Case] Above 272K input the cache rate follows the 2x
    # long-context input rate.
    response = SimpleNamespace(provider=OPENAI, model="gpt-6.1-sol", usage={"input_tokens": 1_000_000, "output_tokens": 0, "input_tokens_details": {"cached_tokens": 1_000_000}})
    record = UsageTracker().record_call(response)
    assert record is not None
    assert record.cost_usd == pytest.approx(0.2)
