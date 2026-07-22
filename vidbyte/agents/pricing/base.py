"""Context Protocol Header

Description:
    Abstract contract and provider registry for per-provider token usage classes.
Purpose:
    Gives every provider response shape its own usage class with native fields and
    a provider-specific cost formula, bound to a provider string via one registry.
Architecture:
    - ProviderUsage: ABC exposing the uniform surface (input/output/total/cost_usd).
    - usage_for: Decorator binding a ProviderUsage class to a ModelProvider.
    - parse_usage: Defensive entry point turning a raw usage payload into a
      provider-native ProviderUsage, or None.
Key Functions:
    - effective_rates: Swaps in over-threshold tier rates and scales cache rates.
    - subset_billing_cost: Cost math for providers whose cached tokens are a
      discounted subset of reported input tokens.
Relations:
    Subclassed by the provider modules in this package; consumed by UsageTracker
    and by AgentRuntime through parse_usage.
Similar Files:
    - vidbyte/lib/registries/pricing.py
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from typing import Any

from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.registries.pricing import ModelPricing

_USAGE_CLASSES: dict[ModelProvider, type["ProviderUsage"]] = {}


class ProviderUsage(ABC):
    """Provider-native token usage for one model call, with its own cost formula."""

    raw: Mapping[str, Any]

    @classmethod
    @abstractmethod
    def from_usage_payload(cls, payload: Mapping[str, Any]) -> "ProviderUsage | None":
        # Parses one provider usage sub-dict; returns None when shape is unrecognized.
        raise NotImplementedError

    @property
    @abstractmethod
    def input_tokens(self) -> int | None:
        # Returns billed input tokens for this call, or None when unreported.
        raise NotImplementedError

    @property
    @abstractmethod
    def output_tokens(self) -> int | None:
        # Returns billed output tokens for this call, or None when unreported.
        raise NotImplementedError

    @property
    @abstractmethod
    def total_tokens(self) -> int | None:
        # Returns total billed tokens for this call, or None when unreported.
        raise NotImplementedError

    @abstractmethod
    def cost_usd(self, pricing: ModelPricing | None) -> float | None:
        # Returns this call's USD cost from provider-native fields; None when unknown.
        raise NotImplementedError


def usage_for(provider: ModelProvider) -> Callable[["type[ProviderUsage]"], "type[ProviderUsage]"]:
    # Decorator binding one ProviderUsage class to a provider in the registry.
    def wrap(cls: type[ProviderUsage]) -> type[ProviderUsage]:
        _USAGE_CLASSES[provider] = cls
        return cls

    return wrap


def parse_usage(provider: ModelProvider | str | None, payload: Mapping[str, Any] | None) -> ProviderUsage | None:
    # Dispatches a raw usage payload to the provider's usage class; never raises.
    provider_enum = _coerce_provider(provider)
    if provider_enum is None or not isinstance(payload, Mapping):
        return None
    usage_cls = _USAGE_CLASSES.get(provider_enum)
    if usage_cls is None:
        return None
    try:
        return usage_cls.from_usage_payload(payload)
    except Exception:
        return None


def effective_rates(pricing: ModelPricing, input_tokens: int | None) -> tuple[float, float, float]:
    # Returns (input, output, cache-read) rates, using the over-threshold tier when
    # the call's input exceeds it; cache-read scales with the active input rate.
    input_rate = pricing.input_per_million
    output_rate = pricing.output_per_million
    if (
        pricing.threshold_tokens is not None
        and input_tokens is not None
        and input_tokens > pricing.threshold_tokens
        and pricing.input_over_threshold_per_million is not None
        and pricing.output_over_threshold_per_million is not None
    ):
        input_rate = pricing.input_over_threshold_per_million
        output_rate = pricing.output_over_threshold_per_million
    cache_read_rate = pricing.cache_read_per_million
    if cache_read_rate is None:
        cache_read_rate = input_rate
    else:
        cache_read_rate = cache_read_rate * (input_rate / pricing.input_per_million)
    return input_rate, output_rate, cache_read_rate


def subset_billing_cost(input_tokens: int | None, output_tokens: int | None, cached_input_tokens: int | None, pricing: ModelPricing | None) -> float | None:
    # Prices providers whose cached input is a discounted subset of input tokens.
    if pricing is None or (input_tokens is None and output_tokens is None):
        return None
    billable_input = input_tokens or 0
    cached = min(cached_input_tokens or 0, billable_input)
    input_rate, output_rate, cache_read_rate = effective_rates(pricing, input_tokens)
    return ((billable_input - cached) * input_rate + cached * cache_read_rate + (output_tokens or 0) * output_rate) / 1_000_000


def int_or_none(value: Any) -> int | None:
    # Coerces one payload value to int, rejecting bools and non-numerics.
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _coerce_provider(provider: ModelProvider | str | None) -> ModelProvider | None:
    # Converts provider strings to ModelProvider, returning None when unknown.
    if isinstance(provider, ModelProvider):
        return provider
    if provider is None:
        return None
    try:
        return ModelProvider(str(provider))
    except ValueError:
        return None


__all__ = [
    "ProviderUsage",
    "effective_rates",
    "int_or_none",
    "parse_usage",
    "subset_billing_cost",
    "usage_for",
]
