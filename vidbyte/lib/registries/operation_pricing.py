"""Context Protocol Header

Description:
    Source-of-truth pricing table and lookup registry for search/fetch operations.
Purpose:
    Centralizes per-operation USD rates so agent usage tracking can price tool
    operations (web search, page fetch) without scattering rate constants across
    the pre-built provider tools.
Architecture:
    - OperationPricing: Immutable per-operation tariff (fixed + per-unit, with an
      included-unit allowance and per-batch billing).
    - OPERATION_PRICING: Built-in rate table keyed by (operation, provider, mode).
    - OperationPricingRegistry: Resolves an (operation, provider, mode) triple to a
      tariff with a mode -> "default" fallback and caller overrides.
Key Functions:
    - default: Builds a registry over the built-in OPERATION_PRICING table.
    - resolve: Returns the OperationPricing for a triple, or None.
    - register: Adds or overrides rates for one (operation, provider, mode) entry.
Relations:
    Consumed by UsageTracker.record_operation and by the priced operation tools in
    vidbyte/tools/builtins/operations.
Similar Files:
    - vidbyte/lib/registries/pricing.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import ceil

from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class OperationPricing:
    """Per-operation USD tariff: a fixed base plus a per-unit rate over an allowance."""

    usd_fixed: float = 0.0
    usd_per_unit: float = 0.0
    included_units: int = 0
    unit_batch: int = 1

    def cost_usd(self, units: int) -> float:
        # Prices one operation: fixed base plus the per-unit rate applied to the
        # billable units above the included allowance, rounded up to whole batches.
        billable = max(0, units - self.included_units)
        batches = ceil(billable / self.unit_batch) if self.unit_batch > 0 else billable
        return self.usd_fixed + self.usd_per_unit * batches


OPERATION_PRICING_AS_OF: str = "2026-07-24"

# Rates verified against official provider docs on OPERATION_PRICING_AS_OF and
# converted to USD (the token tracker's unit) from each provider's native basis.
# Reference-plan assumptions baked into the effective rate, since the customer's
# plan is not knowable at call time:
#   - Tavily / Firecrawl bill in credits; USD uses PAYG ($0.008/credit) and the
#     Standard plan ($0.00083/credit) respectively.
#   - Exa assumes a single content type (text+highlights); extra content types
#     (summaries) bill separately and are out of scope.
#   - Parallel Search assumes ~10 included results before the per-result rate.
#   - OpenAlex prices the marginal search call; the account-level $1/day free
#     allowance is not trackable per call.
# Free operations resolve to an all-zero tariff (cost 0.0), never None, so they do
# not poison the rollup's cost_complete flag. Sources:
#   brave  https://brave.com/learn/best-search-api-2026/
#   exa    https://exa.ai/docs/reference/search
#   tavily https://docs.tavily.com/documentation/api-credits
#   linkup https://docs.linkup.so/pages/documentation/platform/pricing
#   parallel https://docs.parallel.ai/getting-started/pricing
#   openalex https://blog.openalex.org/openalex-api-new-features-and-usage-based-pricing/
#   semantic_scholar https://github.com/allenai/s2-folks/blob/main/API_RELEASE_NOTES.md
#   firecrawl https://www.eesel.ai/blog/firecrawl-pricing
OPERATION_PRICING: dict[tuple[str, str, str], OperationPricing] = {
    # ── search ──────────────────────────────────────────────────────────────
    ("search", "brave", "default"): OperationPricing(usd_fixed=0.005),
    ("search", "exa", "default"): OperationPricing(usd_fixed=0.007, usd_per_unit=0.001, included_units=10),
    ("search", "exa", "standard"): OperationPricing(usd_fixed=0.007, usd_per_unit=0.001, included_units=10),
    ("search", "exa", "agentic"): OperationPricing(usd_fixed=0.012, usd_per_unit=0.001, included_units=10),
    ("search", "tavily", "default"): OperationPricing(usd_fixed=0.008),
    ("search", "tavily", "basic"): OperationPricing(usd_fixed=0.008),
    ("search", "tavily", "advanced"): OperationPricing(usd_fixed=0.016),
    ("search", "linkup", "default"): OperationPricing(usd_fixed=0.005),
    ("search", "linkup", "standard"): OperationPricing(usd_fixed=0.005),
    ("search", "linkup", "deep"): OperationPricing(usd_fixed=0.05),
    ("search", "parallel", "default"): OperationPricing(usd_fixed=0.000001, usd_per_unit=0.000001, included_units=10),
    ("search", "parallel", "turbo"): OperationPricing(usd_fixed=0.000001, usd_per_unit=0.000001, included_units=10),
    ("search", "parallel", "pro"): OperationPricing(usd_fixed=0.000005, usd_per_unit=0.000001, included_units=10),
    ("search", "openalex", "default"): OperationPricing(usd_fixed=0.001),
    ("search", "semantic_scholar", "default"): OperationPricing(),
    # ── fetch ───────────────────────────────────────────────────────────────
    ("fetch", "firecrawl", "default"): OperationPricing(usd_per_unit=0.00083),
    ("fetch", "firecrawl", "scrape"): OperationPricing(usd_per_unit=0.00083),
    ("fetch", "parallel", "default"): OperationPricing(usd_per_unit=0.001),
    ("fetch", "tavily", "default"): OperationPricing(usd_per_unit=0.008, unit_batch=5),
    ("fetch", "tavily", "basic"): OperationPricing(usd_per_unit=0.008, unit_batch=5),
    ("fetch", "tavily", "advanced"): OperationPricing(usd_per_unit=0.016, unit_batch=5),
    ("fetch", "linkup", "default"): OperationPricing(usd_per_unit=0.001),
    ("fetch", "linkup", "nojs"): OperationPricing(usd_per_unit=0.001),
    ("fetch", "linkup", "js"): OperationPricing(usd_per_unit=0.005),
    ("fetch", "direct_http", "default"): OperationPricing(),
}


class OperationPricingRegistry:
    """Resolves (operation, provider, mode) triples to OperationPricing with overrides."""

    def __init__(self, table: Mapping[tuple[str, str, str], OperationPricing] | None = None) -> None:
        # Copy the source table so register() never mutates shared module state.
        source = table if table is not None else OPERATION_PRICING
        self._table: dict[tuple[str, str, str], OperationPricing] = dict(source)

    @classmethod
    def default(cls) -> "OperationPricingRegistry":
        # Returns an independent registry over the built-in OPERATION_PRICING table.
        return cls(OPERATION_PRICING)

    def resolve(self, operation: str, provider: str, mode: str = "default") -> OperationPricing | None:
        # Returns the tariff for the exact triple, falling back to the provider's
        # "default" mode, else None when the operation/provider is unpriced.
        if not self._valid_key(operation, provider, mode):
            return None
        exact = self._table.get((operation, provider, mode))
        if exact is not None:
            return exact
        return self._table.get((operation, provider, "default"))

    def register(self, operation: str, provider: str, mode: str, pricing: OperationPricing) -> None:
        # Adds or overrides one (operation, provider, mode) entry after validating inputs.
        if not self._valid_key(operation, provider, mode):
            raise ConfigurationError("operation, provider, and mode must be non-empty strings.")
        if not isinstance(pricing, OperationPricing):
            raise ConfigurationError("pricing must be an OperationPricing instance.")
        self._table[(operation, provider, mode)] = pricing

    @staticmethod
    def _valid_key(operation: str, provider: str, mode: str) -> bool:
        # True when every key component is a non-empty string.
        return all(isinstance(part, str) and bool(part.strip()) for part in (operation, provider, mode))


__all__ = [
    "OPERATION_PRICING",
    "OPERATION_PRICING_AS_OF",
    "OperationPricing",
    "OperationPricingRegistry",
]
