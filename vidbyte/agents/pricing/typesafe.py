"""Context Protocol Header

FILE: vidbyte/agents/pricing/typesafe.py
PURPOSE: Parses TypeSafe Jev decision usage and prices it: input tokens at the table rate, output tokens free. from_decision and total are the one strict way Jev features read and add decision usage.
ROLE IN CODEBASE: Bound to ModelProvider.TYPESAFE through ModelProvider.usage_class, so UsageTracker.record_call prices every Jev call a model-backed tool reports.
ARCHITECTURE NOTE: Jev reports only input_tokens and output_tokens and has no cached-token tier; total_tokens is derived, and cost goes through the shared subset_billing_cost formula so C005 keeps cost math inside this package.
COMMON MODIFICATION PATTERNS: Change rates in vidbyte/lib/registries/pricing.py, not here; extend parsing only when TypeSafe adds usage fields.
KNOWN EDGE CASES: A payload with neither token field parses to None, while from_decision raises ProviderResponseError unless both counts are present and total of no records is zero tokens; output tokens are priced at the table's output rate, which is 0.0 for every Jev model; any cache-looking field TypeSafe might add is ignored until TypeSafe documents a cache rate.
RELATED DOCS: docs/design/jev-agent-scaffold.md, https://docs.typesafe.ai/models.md, and https://docs.typesafe.ai/api.md#response-body.
TESTS: tests/test_jev_agent.py, tests/test_jev_skill_preload.py, and scripts/test-jev-agent-scaffold.py.

Description:
    JevUsage — the ProviderUsage subclass for TypeSafe's System One endpoint.
Relations:
    Registered in vidbyte/lib/enums/model_provider.py; priced by
    vidbyte/lib/registries/pricing.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vidbyte.agents.pricing.base import ProviderUsage
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.errors import ConfigurationError, ProviderResponseError
from vidbyte.lib.registries.pricing import ModelPricing

if TYPE_CHECKING:
    from vidbyte.lib.runners.types import DecisionModelResponse


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

    @classmethod
    def from_decision(cls, decision: DecisionModelResponse) -> JevUsage:
        # Reads one Jev decision's usage strictly: a decision without both token counts is an error, never an empty record.
        # @intent jev-features-share-one-usage-parser
        # Jev features take their usage from here instead of hand-rolling `from_usage_payload(... or {})`, so a
        # decision whose cost cannot be known fails the same way everywhere.
        usage = None if decision.usage is None else cls.from_usage_payload(decision.usage)
        if usage is None or usage.input_tokens is None or usage.output_tokens is None:
            raise ProviderResponseError(f"TypeSafe answered with model {decision.model!r} but did not report both input and output token counts, so the decision's usage cannot be recorded.", provider=ModelProvider.TYPESAFE.value)
        return usage

    @classmethod
    def total(cls, usages: Iterable[JevUsage]) -> JevUsage:
        # Adds several Jev decisions' token counts into one record; no decisions add up to zero tokens.
        input_tokens = 0
        output_tokens = 0
        for usage in usages:
            if usage.input_tokens is None or usage.output_tokens is None:
                raise ConfigurationError("JevUsage.total needs input and output token counts on every record; read each decision with JevUsage.from_decision.", details={"usage": repr(usage)})
            input_tokens += usage.input_tokens
            output_tokens += usage.output_tokens
        return cls(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=input_tokens + output_tokens, raw={"input_tokens": input_tokens, "output_tokens": output_tokens})

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
