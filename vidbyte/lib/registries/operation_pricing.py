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
    included_units: float = 0.0
    unit_batch: int = 1

    def cost_usd(self, units: int | float) -> float:
        # Prices one operation: fixed base plus the per-unit rate applied to the
        # billable units above the included allowance, rounded up to whole batches.
        billable = max(0, units - self.included_units)
        batches = ceil(billable / self.unit_batch) if self.unit_batch > 0 else billable
        return self.usd_fixed + self.usd_per_unit * batches


OPERATION_PRICING_AS_OF: str = "2026-07-29"

# Rates are reviewed against official provider docs on OPERATION_PRICING_AS_OF and
# converted to USD from each provider's native request, result, page, credit, run,
# or time meter. Plan allowances are not inferred at call time; applications can
# supply an OperationPricingRegistry override for their account plan.
# Dynamic providers emit their native quantity (for example Tavily credits or
# Browserbase browser hours) and the SDK applies the corresponding tariff here.
# Free operations resolve to an all-zero tariff; unsupported operations resolve to
# None so cost_complete remains visibly false instead of guessing.
# Sources:
#   browserbase https://www.browserbase.com/pricing
#   exa        https://exa.ai/pricing?tab=api
#   tavily     https://docs.tavily.com/documentation/api-credits
#   parallel   https://docs.parallel.ai/getting-started/pricing
#   brave      https://brave.com/search/api/
#   firecrawl  https://www.firecrawl.dev/pricing
#   linkup     https://docs.linkup.so/pages/documentation/platform/pricing
#   openalex   https://blog.openalex.org/openalex-api-new-features-and-usage-based-pricing/
#   semantic_scholar https://github.com/allenai/s2-folks/blob/main/API_RELEASE_NOTES.md
OPERATION_PRICING: dict[tuple[str, str, str], OperationPricing] = {
    # ── search ──────────────────────────────────────────────────────────────
    ("search", "brave", "default"): OperationPricing(usd_fixed=0.005),
    ("search", "browserbase", "default"): OperationPricing(usd_fixed=0.007),
    ("search", "exa", "default"): OperationPricing(usd_fixed=0.007),
    ("search", "exa", "standard"): OperationPricing(usd_fixed=0.007),
    ("search", "exa", "instant"): OperationPricing(usd_fixed=0.007),
    ("search", "exa", "fast"): OperationPricing(usd_fixed=0.007),
    ("search", "exa", "auto"): OperationPricing(usd_fixed=0.007),
    ("search", "exa", "deep-lite"): OperationPricing(usd_fixed=0.012),
    ("search", "exa", "deep"): OperationPricing(usd_fixed=0.012),
    ("search", "exa", "deep-reasoning"): OperationPricing(usd_fixed=0.015),
    ("search_extra_result", "exa", "default"): OperationPricing(usd_per_unit=0.001),
    ("search_extra_result", "exa", "deep"): OperationPricing(usd_per_unit=0.001),
    ("content_summary", "exa", "default"): OperationPricing(usd_per_unit=0.001),
    ("answer", "exa", "default"): OperationPricing(usd_fixed=0.005),
    ("search", "tavily", "default"): OperationPricing(usd_per_unit=0.008),
    ("search", "tavily", "basic"): OperationPricing(usd_per_unit=0.008),
    ("search", "tavily", "fast"): OperationPricing(usd_per_unit=0.008),
    ("search", "tavily", "ultra-fast"): OperationPricing(usd_per_unit=0.008),
    ("search", "tavily", "advanced"): OperationPricing(usd_per_unit=0.008),
    ("search", "linkup", "default"): OperationPricing(usd_fixed=0.005),
    ("search", "linkup", "standard"): OperationPricing(usd_fixed=0.005),
    ("search", "linkup", "deep"): OperationPricing(usd_fixed=0.05),
    ("search", "parallel", "default"): OperationPricing(usd_fixed=0.005),
    ("search", "parallel", "turbo"): OperationPricing(usd_fixed=0.005),
    ("search", "parallel", "basic"): OperationPricing(usd_fixed=0.005),
    ("search", "parallel", "advanced"): OperationPricing(usd_fixed=0.005),
    ("search_extra_result", "parallel", "default"): OperationPricing(usd_per_unit=0.001),
    ("search_extra_result", "parallel", "turbo"): OperationPricing(usd_per_unit=0.001),
    ("search", "openalex", "default"): OperationPricing(usd_fixed=0.001),
    ("search", "semantic_scholar", "default"): OperationPricing(),
    # ── fetch ───────────────────────────────────────────────────────────────
    ("fetch", "firecrawl", "default"): OperationPricing(usd_per_unit=0.00083),
    ("fetch", "firecrawl", "scrape"): OperationPricing(usd_per_unit=0.00083),
    ("fetch", "browserbase", "default"): OperationPricing(usd_per_unit=0.001),
    ("fetch", "browserbase", "proxy"): OperationPricing(usd_per_unit=0.004),
    ("extract", "browserbase", "default"): OperationPricing(usd_per_unit=0.004),
    ("extract", "browserbase", "proxy"): OperationPricing(usd_per_unit=0.007),
    ("fetch", "parallel", "default"): OperationPricing(usd_per_unit=0.001),
    ("fetch", "tavily", "default"): OperationPricing(usd_per_unit=0.008, unit_batch=5),
    ("fetch", "tavily", "basic"): OperationPricing(usd_per_unit=0.008, unit_batch=5),
    ("fetch", "tavily", "advanced"): OperationPricing(usd_per_unit=0.016, unit_batch=5),
    ("map", "tavily", "default"): OperationPricing(usd_per_unit=0.008, unit_batch=10),
    ("map", "tavily", "instructions"): OperationPricing(usd_per_unit=0.016, unit_batch=10),
    ("research", "tavily", "default"): OperationPricing(usd_per_unit=0.008),
    ("fetch", "exa", "default"): OperationPricing(usd_per_unit=0.001),
    ("chat", "parallel", "speed"): OperationPricing(usd_fixed=0.005),
    ("chat", "parallel", "lite"): OperationPricing(usd_fixed=0.005),
    ("chat", "parallel", "base"): OperationPricing(usd_fixed=0.010),
    ("chat", "parallel", "core"): OperationPricing(usd_fixed=0.025),
    ("task", "parallel", "lite"): OperationPricing(usd_fixed=0.005),
    ("task", "parallel", "base"): OperationPricing(usd_fixed=0.010),
    ("task", "parallel", "core"): OperationPricing(usd_fixed=0.025),
    ("task", "parallel", "pro"): OperationPricing(usd_fixed=0.100),
    ("task", "parallel", "ultra"): OperationPricing(usd_fixed=0.300),
    ("find_all_request", "parallel", "preview"): OperationPricing(usd_fixed=0.10),
    ("find_all_request", "parallel", "base"): OperationPricing(usd_fixed=0.25),
    ("find_all_request", "parallel", "core"): OperationPricing(usd_fixed=2.0),
    ("find_all_request", "parallel", "pro"): OperationPricing(usd_fixed=10.0),
    ("find_all_match", "parallel", "base"): OperationPricing(usd_per_unit=0.03),
    ("find_all_match", "parallel", "core"): OperationPricing(usd_per_unit=0.15),
    ("find_all_match", "parallel", "pro"): OperationPricing(usd_per_unit=1.0),
    ("monitor", "parallel", "lite"): OperationPricing(usd_per_unit=0.003),
    ("monitor", "parallel", "base"): OperationPricing(usd_per_unit=0.010),
    ("monitor", "exa", "default"): OperationPricing(usd_fixed=0.015),
    ("session_hour", "browserbase", "default"): OperationPricing(usd_per_unit=0.12),
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
