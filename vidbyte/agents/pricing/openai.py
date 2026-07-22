"""Context Protocol Header

Description:
    OpenAI Responses API usage shape and cost formula.
Purpose:
    Parses OpenAI's input/output/total usage with cached-input and reasoning
    detail, pricing cached input as a discounted subset of input tokens.
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

from vidbyte.agents.pricing.base import ProviderUsage, int_or_none, subset_billing_cost, usage_for
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.registries.pricing import ModelPricing


@usage_for(ModelProvider.OPENAI)
@dataclass(frozen=True, slots=True)
class OpenAIUsage(ProviderUsage):
    """OpenAI Responses usage: cached input is a billed subset of input_tokens."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_usage_payload(cls, payload: Mapping[str, Any]) -> "OpenAIUsage | None":
        # Parses an OpenAI Responses usage dict; None when no token fields exist.
        usage = cls(
            input_tokens=int_or_none(payload.get("input_tokens")),
            output_tokens=int_or_none(payload.get("output_tokens")),
            total_tokens=int_or_none(payload.get("total_tokens")),
            cached_input_tokens=_details_int(payload, "input_tokens_details", "cached_tokens"),
            reasoning_tokens=_details_int(payload, "output_tokens_details", "reasoning_tokens"),
            raw=payload,
        )
        if usage.input_tokens is None and usage.output_tokens is None and usage.total_tokens is None:
            return None
        return usage

    def cost_usd(self, pricing: ModelPricing | None) -> float | None:
        # Prices uncached input at input rate and cached input at cache-read rate.
        return subset_billing_cost(self.input_tokens, self.output_tokens, self.cached_input_tokens, pricing)


def _details_int(payload: Mapping[str, Any], section: str, key: str) -> int | None:
    # Reads one int from a nested usage details mapping, tolerating absence.
    details = payload.get(section)
    if not isinstance(details, Mapping):
        return None
    return int_or_none(details.get(key))


__all__ = ["OpenAIUsage"]
