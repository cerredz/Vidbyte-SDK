"""Context Protocol Header

Description:
    OpenRouter chat-completions usage shape with provider-reported cost.
Purpose:
    Prefers OpenRouter's per-generation usage.cost (returned when requests set
    usage.include) because marketplace rates vary per routed model; falls back
    to table math when the provider did not report cost.
Architecture:
    - OpenRouterUsage: ChatCompletionUsage subclass bound to ModelProvider.OPENROUTER.
Relations:
    Registered in vidbyte/agents/pricing/base.py; pairs with the usage.include
    request field added in vidbyte/providers/openrouter.py.
Similar Files:
    - vidbyte/agents/pricing/compatible.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from vidbyte.agents.pricing.base import usage_for
from vidbyte.agents.pricing.compatible import ChatCompletionUsage
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.registries.pricing import ModelPricing


@usage_for(ModelProvider.OPENROUTER)
@dataclass(frozen=True, slots=True)
class OpenRouterUsage(ChatCompletionUsage):
    """OpenRouter usage: provider-reported cost wins over table pricing."""

    reported_cost: float | None = None

    @classmethod
    def from_usage_payload(cls, payload: Mapping[str, Any]) -> "OpenRouterUsage | None":
        # Parses chat-completions usage plus OpenRouter's optional usage.cost.
        # Explicit super() is required: zero-arg super() breaks under slots=True.
        usage = super(OpenRouterUsage, cls).from_usage_payload(payload)
        if usage is None:
            return None
        return replace(usage, reported_cost=cls._cost_or_none(payload))

    @staticmethod
    def _cost_or_none(payload: Mapping[str, Any]) -> float | None:
        # Coerces OpenRouter's usage.cost to float, rejecting bools and non-numerics.
        value = payload.get("cost")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)

    def cost_usd(self, pricing: ModelPricing | None) -> float | None:
        # Returns the provider-reported cost when present, else table math.
        if self.reported_cost is not None:
            return self.reported_cost
        return super(OpenRouterUsage, self).cost_usd(pricing)


__all__ = ["OpenRouterUsage"]
