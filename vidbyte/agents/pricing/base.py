"""Context Protocol Header

Description:
    Abstract contract and provider registry for per-provider token usage classes.
Purpose:
    Gives every provider response shape its own usage class with native fields and
    a provider-specific cost formula, bound to a provider string via one registry.
Architecture:
    - ProviderUsage: ABC exposing the uniform surface (input/output/total/cost_usd)
      and the shared token-coercion and cost-math the subclasses build on.
    - usage_for: Decorator binding a ProviderUsage class to a ModelProvider.
    - parse_usage: Defensive entry point turning a raw usage payload into a
      provider-native ProviderUsage, or None.
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

    @property
    def cached_input_tokens(self) -> int | None:
        # Billed cached-input subset of input tokens; None unless a provider reports it.
        return None

    @staticmethod
    def coerce_int(value: Any) -> int | None:
        # Coerces one payload value to int, rejecting bools and non-numerics.
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        return None

    def effective_rates(self, pricing: ModelPricing) -> tuple[float, float, float]:
        # Returns (input, output, cache-read) rates, using the over-threshold tier when
        # this call's input crosses it; cache-read scales with the active input rate.
        input_rate = pricing.input_per_million
        output_rate = pricing.output_per_million
        if (
            self._over_threshold(pricing)
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

    def _over_threshold(self, pricing: ModelPricing) -> bool:
        # True when input crosses into the over-threshold tier, honoring inclusivity (xAI uses >=).
        if pricing.threshold_tokens is None or self.input_tokens is None:
            return False
        if pricing.threshold_inclusive:
            return self.input_tokens >= pricing.threshold_tokens
        return self.input_tokens > pricing.threshold_tokens

    def subset_billing_cost(self, pricing: ModelPricing | None) -> float | None:
        # Prices providers whose cached input is a discounted subset of input tokens.
        if pricing is None or (self.input_tokens is None and self.output_tokens is None):
            return None
        billable_input = self.input_tokens or 0
        cached = min(self.cached_input_tokens or 0, billable_input)
        input_rate, output_rate, cache_read_rate = self.effective_rates(pricing)
        return ((billable_input - cached) * input_rate + cached * cache_read_rate + (self.output_tokens or 0) * output_rate) / 1_000_000


def usage_for(provider: ModelProvider) -> Callable[["type[ProviderUsage]"], "type[ProviderUsage]"]:
    # Decorator binding one ProviderUsage class to a provider in the registry.
    def wrap(cls: type[ProviderUsage]) -> type[ProviderUsage]:
        _USAGE_CLASSES[provider] = cls
        return cls

    return wrap


def parse_usage(provider: ModelProvider | str | None, payload: Mapping[str, Any] | None) -> ProviderUsage | None:
    # Dispatches a raw usage payload to the provider's usage class; never raises.
    if not isinstance(payload, Mapping):
        return None
    if not isinstance(provider, ModelProvider):
        try:
            provider = ModelProvider(str(provider))
        except (ValueError, TypeError):
            return None
    usage_cls = _USAGE_CLASSES.get(provider)
    if usage_cls is None:
        return None
    try:
        return usage_cls.from_usage_payload(payload)
    except Exception:
        return None


__all__ = [
    "ProviderUsage",
    "parse_usage",
    "usage_for",
]
