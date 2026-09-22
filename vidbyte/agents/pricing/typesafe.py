"""Context Protocol Header

FILE: vidbyte/agents/pricing/typesafe.py
PURPOSE: Parses TypeSafe Jev decision usage and prices it: input tokens at the table rate, output tokens free.
ROLE IN CODEBASE: Bound to ModelProvider.TYPESAFE through ModelProvider.usage_class, so UsageTracker.record_call prices every Jev call a model-backed tool reports.
ARCHITECTURE NOTE: Jev reports only input_tokens and output_tokens and has no cached-token tier; total_tokens is derived, and cost goes through the shared subset_billing_cost formula so C005 keeps cost math inside this package.
COMMON MODIFICATION PATTERNS: Change rates in vidbyte/lib/registries/pricing.py, not here; extend parsing only when TypeSafe adds usage fields.
KNOWN EDGE CASES: A payload with neither token field parses to None; output tokens are priced at the table's output rate, which is 0.0 for every Jev model; any cache-looking field TypeSafe might add is ignored until TypeSafe documents a cache rate.
RELATED DOCS: docs/design/jev-agent-scaffold.md, https://docs.typesafe.ai/models.md, and https://docs.typesafe.ai/api.md#response-body.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.

Description:
    JevUsage — the ProviderUsage subclass for TypeSafe's System One endpoint.
Relations:
    Registered in vidbyte/lib/enums/model_provider.py; priced by
    vidbyte/lib/registries/pricing.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.agents.pricing.base import ProviderUsage
from vidbyte.lib.registries.pricing import ModelPricing


@dataclass(frozen=True, slots=True)
class JevUsage(ProviderUsage):
    """TypeSafe Jev usage: input tokens are billed, output tokens are reported but free."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_usage_payload(cls, payload: Mapping[str, Any]) -> "JevUsage | None":
        # Parses a System One usage dict; None when neither token field is reported.
        input_tokens = cls.coerce_int(payload.get("input_tokens"))
        output_tokens = cls.coerce_int(payload.get("output_tokens"))
        if input_tokens is None and output_tokens is None:
            return None
        total = input_tokens + output_tokens if input_tokens is not None and output_tokens is not None else None
        return cls(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=total, raw=payload)

    @property
    def cached_input_tokens(self) -> int | None:
        # Always None: TypeSafe neither reports cached input tokens nor prices them differently.
        # @intent jev-has-no-cache-tier
        # Checked against https://docs.typesafe.ai/models.md and api.md on 2026-09-21: usage is
        # only input_tokens/output_tokens and every input token bills at one rate, so returning
        # None keeps the subset formula billing all input at the full rate and cache_hit_rate None.
        return None

    def cost_usd(self, pricing: ModelPricing | None) -> float | None:
        # Prices input at the input rate and output at the (free) output rate.
        # @intent jev-output-is-free
        # Output tokens are reported but TypeSafe does not bill them; the table's 0.0 output
        # rate, not special-casing here, encodes that so a future price change is data-only.
        return self.subset_billing_cost(pricing)


__all__ = ["JevUsage"]
