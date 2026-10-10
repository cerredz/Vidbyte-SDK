"""Context Protocol Header

Description:
    OpenRouter chat-completions and System One decision usage shapes with provider-reported cost.
Purpose:
    Prefers OpenRouter's per-generation usage.cost (returned when requests set
    usage.include) because marketplace rates vary per routed model; falls back
    to table math when the provider did not report cost.
Architecture:
    - OpenRouterUsage: ChatCompletionUsage subclass bound to ModelProvider.OPENROUTER.
Relations:
    Registered in vidbyte/agents/pricing/base.py; pairs with the usage.include
    request field added in vidbyte/providers/openrouter.py. Decision calls through
    vidbyte/providers/systemone.py report this same usage object.
Known Edge Cases:
    OpenRouter's /systemone decision route reports usage as input_tokens /
    output_tokens (the System One keys) plus cost, not prompt_tokens /
    completion_tokens; the total is derived from the two when it is absent.
Similar Files:
    - vidbyte/agents/pricing/compatible.py
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from vidbyte.agents.pricing.compatible import ChatCompletionUsage
from vidbyte.lib.registries.pricing import ModelPricing


@dataclass(frozen=True, slots=True)
class OpenRouterUsage(ChatCompletionUsage):
    """OpenRouter usage: provider-reported cost wins over table pricing."""

    reported_cost: float | None = None

    @classmethod
    def from_usage_payload(cls, payload: Mapping[str, Any]) -> "OpenRouterUsage | None":
        # Parses chat-completions usage, or the System One decision usage keys, plus OpenRouter's optional usage.cost.
        # Explicit super() is required: zero-arg super() breaks under slots=True.
        # @intent openrouter-decision-usage-stays-priced
        # OpenRouter's decision route reports input_tokens/output_tokens instead of the chat keys; reading
        # them keeps those calls recorded with token counts and usage.cost instead of counted as unaccounted.
        usage = super(OpenRouterUsage, cls).from_usage_payload(payload)
        if usage is None or (usage.input_tokens is None and usage.output_tokens is None):
            usage = cls._decision_usage(payload) or usage
        if usage is None:
            return None
        return replace(usage, reported_cost=cls._cost_or_none(payload))

    @classmethod
    def _decision_usage(cls, payload: Mapping[str, Any]) -> "OpenRouterUsage | None":
        # Reads the System One usage keys; None when neither token count is reported.
        input_tokens = cls.coerce_int(payload.get("input_tokens"))
        output_tokens = cls.coerce_int(payload.get("output_tokens"))
        if input_tokens is None and output_tokens is None:
            return None
        total_tokens = cls.coerce_int(payload.get("total_tokens"))
        if total_tokens is None and input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens
        return cls(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=total_tokens, raw=payload)

    @staticmethod
    def _cost_or_none(payload: Mapping[str, Any]) -> float | None:
        # A malformed marketplace price must not turn an unpriced model call into a complete negative or infinite bill.
        value = payload.get("cost")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            return None
        return float(value)

    def cost_usd(self, pricing: ModelPricing | None) -> float | None:
        # Returns the provider-reported cost when present, else table math.
        if self.reported_cost is not None:
            return self.reported_cost
        return super(OpenRouterUsage, self).cost_usd(pricing)


__all__ = ["OpenRouterUsage"]
