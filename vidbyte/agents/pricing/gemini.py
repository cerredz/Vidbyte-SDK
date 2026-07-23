"""Context Protocol Header

Description:
    Google Gemini generateContent usage shape and cost formula.
Purpose:
    Parses usageMetadata camelCase fields, billing thoughts tokens as output and
    cached content as a discounted subset of prompt tokens.
Architecture:
    - GeminiUsage: ProviderUsage bound to ModelProvider.GEMINI.
Relations:
    Registered in vidbyte/agents/pricing/base.py; fixes the historical gap where
    Gemini runs reported no token usage; rates from PROVIDER_PRICING.
Similar Files:
    - vidbyte/agents/pricing/openai.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.agents.pricing.base import ProviderUsage, usage_for
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.registries.pricing import ModelPricing


@usage_for(ModelProvider.GEMINI)
@dataclass(frozen=True, slots=True)
class GeminiUsage(ProviderUsage):
    """Gemini usageMetadata: thoughts bill as output; cached content is an input subset."""

    prompt_tokens: int | None = None
    candidates_tokens: int | None = None
    thoughts_tokens: int | None = None
    cached_content_tokens: int | None = None
    reported_total_tokens: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_usage_payload(cls, payload: Mapping[str, Any]) -> "GeminiUsage | None":
        # Parses a Gemini usageMetadata dict; None when no token fields exist.
        usage = cls(
            prompt_tokens=cls.coerce_int(payload.get("promptTokenCount")),
            candidates_tokens=cls.coerce_int(payload.get("candidatesTokenCount")),
            thoughts_tokens=cls.coerce_int(payload.get("thoughtsTokenCount")),
            cached_content_tokens=cls.coerce_int(payload.get("cachedContentTokenCount")),
            reported_total_tokens=cls.coerce_int(payload.get("totalTokenCount")),
            raw=payload,
        )
        if usage.total_tokens is None:
            return None
        return usage

    @property
    def input_tokens(self) -> int | None:
        # Returns prompt tokens, Gemini's billed input measure.
        return self.prompt_tokens

    @property
    def output_tokens(self) -> int | None:
        # Returns candidates plus thoughts tokens, Gemini's billed output measure.
        if self.candidates_tokens is None and self.thoughts_tokens is None:
            return None
        return (self.candidates_tokens or 0) + (self.thoughts_tokens or 0)

    @property
    def cached_input_tokens(self) -> int | None:
        # Maps Gemini's cached-content bucket onto the shared cached-input subset.
        return self.cached_content_tokens

    @property
    def total_tokens(self) -> int | None:
        # Prefers the reported total, else sums prompt and output components.
        if self.reported_total_tokens is not None:
            return self.reported_total_tokens
        if self.prompt_tokens is None and self.output_tokens is None:
            return None
        return (self.prompt_tokens or 0) + (self.output_tokens or 0)

    def cost_usd(self, pricing: ModelPricing | None) -> float | None:
        # Prices uncached prompt at input rate and cached content at cache-read rate.
        return self.subset_billing_cost(pricing)


__all__ = ["GeminiUsage"]
