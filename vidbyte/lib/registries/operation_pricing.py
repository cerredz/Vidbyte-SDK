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


OPERATION_PRICING_AS_OF: str = "2026-08-08"

# Rates verified against official provider docs on OPERATION_PRICING_AS_OF and
# converted to USD (the token tracker's unit) from each provider's native basis.
# Most vendors publish a per-1,000-unit rate, so the entry below is that figure
# divided by 1,000. Dividing twice is the one mistake this table has actually
# made in review (see the Parallel note); OperationPricingTableTests asserts a
# magnitude floor that catches it.
# Preferred basis is the vendor's pay-as-you-go API rate. Where a vendor sells
# no PAYG rate, a reference plan is named below, since the customer's plan is
# not knowable at call time and those accounts should override this registry
# through OperationPricingRegistry.register:
#   - Tavily bills in credits at a published PAYG rate of $0.008/credit with no
#     monthly commitment. Monthly plans are cheaper ($0.005-$0.0075/credit), so
#     this is the plan-free API rate and it over-prices a subscribed account.
#   - Firecrawl publishes no pay-per-use rate at all ("We currently do not offer
#     a pay-per-use plan"), only monthly plans. USD uses the Standard plan
#     ($83 / 100,000 credits = $0.00083/credit). Plans span 5.3x (Hobby $0.0032,
#     Standard $0.00083, Growth $0.0007, Scale $0.0006), so any single figure
#     here encodes a plan assumption that off-Standard accounts must override.
#   - Exa assumes a single content type (text+highlights); extra content types
#     (summaries) bill separately and are out of scope.
#   - Exa "<type>+highlights" modes fold the contents meter into usd_per_unit
#     (0.001 search + 0.001 highlights). This is an approximation: highlights bill
#     from the first result while search bills only above the ten-result
#     allowance, so the entry under-prices calls at or below ten results and
#     over-prices very large ones. It is accurate near twenty results, the
#     intended operating point. ExaClient(include_highlights=True) is what selects
#     these modes; the default results-only client never resolves them.
#   - Parallel's pricing table column is headed "Cost ($/1000)", so every entry
#     below is that column's value divided by 1,000 -- turbo 1 -> $0.001/request,
#     basic/base/advanced/pro 5 -> $0.005/request, additional results 1 ->
#     $0.001/result above the ten included, Extract 1 -> $0.001/URL. Do not
#     divide again: reading the column value as dollars-per-unit and then
#     dividing by 1,000 put these six entries 1000x under the real rate on main
#     and reverted a correct fix (PR #325) once. The Task/Chat/Response/Monitor
#     entries further down convert the same column correctly and cross-check it.
#   - Browserbase uses Developer-plan overage; the Startup plan halves Fetch and
#     lowers browser hours, so those accounts should override this registry.
#   - OpenAlex prices the marginal search call; the account-level $1/day free
#     allowance is not trackable per call.
# Products deliberately absent, because one call bills two meters or the vendor
# publishes a range rather than a rate; they resolve to None so cost_complete
# stays visibly false instead of being guessed:
#   - Tavily Crawl (map credits + extract credits) and Research (4-110 / 15-250).
#   - Parallel FindAll (fixed generator cost + per-match cost).
#   - Exa Contents text/summary content types, and Agent "auto" metered mode.
#     Highlights are represented through the "+highlights" search modes above.
#   - Browserbase browser-hours and proxy-GB, whose fractional units would round
#     up to a whole batch under OperationPricing.cost_usd.
#   - Tavily "fast" / "ultra-fast" depths, whose credit cost is not published.
# Free operations resolve to an all-zero tariff (cost 0.0), never None, so they do
# not poison the rollup's cost_complete flag. Sources:
#   brave  https://brave.com/search/api/
#   browserbase https://www.browserbase.com/pricing
#   exa    https://exa.ai/pricing
#   tavily https://docs.tavily.com/documentation/api-credits
#   linkup https://docs.linkup.so/pages/documentation/platform/pricing
#   parallel https://docs.parallel.ai/getting-started/pricing
#   openalex https://blog.openalex.org/openalex-api-new-features-and-usage-based-pricing/
#   semantic_scholar https://github.com/allenai/s2-folks/blob/main/API_RELEASE_NOTES.md
#   firecrawl https://www.firecrawl.dev/pricing
OPERATION_PRICING: dict[tuple[str, str, str], OperationPricing] = {
    # ── search ──────────────────────────────────────────────────────────────
    ("search", "brave", "default"): OperationPricing(usd_fixed=0.005),
    ("search", "browserbase", "default"): OperationPricing(usd_fixed=0.007),
    ("search", "exa", "default"): OperationPricing(usd_fixed=0.007, usd_per_unit=0.001, included_units=10),
    ("search", "exa", "standard"): OperationPricing(usd_fixed=0.007, usd_per_unit=0.001, included_units=10),
    ("search", "exa", "auto"): OperationPricing(usd_fixed=0.007, usd_per_unit=0.001, included_units=10),
    ("search", "exa", "fast"): OperationPricing(usd_fixed=0.007, usd_per_unit=0.001, included_units=10),
    ("search", "exa", "agentic"): OperationPricing(usd_fixed=0.012, usd_per_unit=0.001, included_units=10),
    ("search", "exa", "deep-lite"): OperationPricing(usd_fixed=0.012, usd_per_unit=0.001, included_units=10),
    ("search", "exa", "deep"): OperationPricing(usd_fixed=0.012, usd_per_unit=0.001, included_units=10),
    ("search", "exa", "deep-reasoning"): OperationPricing(usd_fixed=0.015, usd_per_unit=0.001, included_units=10),
    ("search", "exa", "default+highlights"): OperationPricing(usd_fixed=0.007, usd_per_unit=0.002, included_units=10),
    ("search", "exa", "standard+highlights"): OperationPricing(usd_fixed=0.007, usd_per_unit=0.002, included_units=10),
    ("search", "exa", "auto+highlights"): OperationPricing(usd_fixed=0.007, usd_per_unit=0.002, included_units=10),
    ("search", "exa", "fast+highlights"): OperationPricing(usd_fixed=0.007, usd_per_unit=0.002, included_units=10),
    ("search", "exa", "agentic+highlights"): OperationPricing(usd_fixed=0.012, usd_per_unit=0.002, included_units=10),
    ("search", "exa", "deep-lite+highlights"): OperationPricing(usd_fixed=0.012, usd_per_unit=0.002, included_units=10),
    ("search", "exa", "deep+highlights"): OperationPricing(usd_fixed=0.012, usd_per_unit=0.002, included_units=10),
    ("search", "exa", "deep-reasoning+highlights"): OperationPricing(usd_fixed=0.015, usd_per_unit=0.002, included_units=10),
    ("search", "tavily", "default"): OperationPricing(usd_fixed=0.008),
    ("search", "tavily", "basic"): OperationPricing(usd_fixed=0.008),
    ("search", "tavily", "advanced"): OperationPricing(usd_fixed=0.016),
    ("search", "linkup", "default"): OperationPricing(usd_fixed=0.005),
    ("search", "linkup", "standard"): OperationPricing(usd_fixed=0.005),
    ("search", "linkup", "deep"): OperationPricing(usd_fixed=0.05),
    ("search", "parallel", "default"): OperationPricing(usd_fixed=0.001, usd_per_unit=0.001, included_units=10),
    ("search", "parallel", "turbo"): OperationPricing(usd_fixed=0.001, usd_per_unit=0.001, included_units=10),
    ("search", "parallel", "pro"): OperationPricing(usd_fixed=0.005, usd_per_unit=0.001, included_units=10),
    ("search", "parallel", "base"): OperationPricing(usd_fixed=0.005, usd_per_unit=0.001, included_units=10),
    ("search", "parallel", "advanced"): OperationPricing(usd_fixed=0.005, usd_per_unit=0.001, included_units=10),
    ("search", "openalex", "default"): OperationPricing(usd_fixed=0.001),
    ("search", "semantic_scholar", "default"): OperationPricing(),
    # ── fetch ───────────────────────────────────────────────────────────────
    ("fetch", "firecrawl", "default"): OperationPricing(usd_per_unit=0.00083),
    ("fetch", "firecrawl", "scrape"): OperationPricing(usd_per_unit=0.00083),
    ("fetch", "browserbase", "default"): OperationPricing(usd_per_unit=0.001),
    ("fetch", "browserbase", "proxy"): OperationPricing(usd_per_unit=0.004),
    ("fetch", "parallel", "default"): OperationPricing(usd_per_unit=0.001),
    ("fetch", "tavily", "default"): OperationPricing(usd_per_unit=0.008, unit_batch=5),
    ("fetch", "tavily", "basic"): OperationPricing(usd_per_unit=0.008, unit_batch=5),
    ("fetch", "tavily", "advanced"): OperationPricing(usd_per_unit=0.016, unit_batch=5),
    ("fetch", "linkup", "default"): OperationPricing(usd_per_unit=0.001),
    ("fetch", "linkup", "nojs"): OperationPricing(usd_per_unit=0.001),
    ("fetch", "linkup", "js"): OperationPricing(usd_per_unit=0.005),
    ("fetch", "direct_http", "default"): OperationPricing(),
    # ── other provider APIs: reference rates with no tool emitter yet ────────
    # Callers reaching these endpoints with their own client can record them via
    # UsageTracker.record_operation and get a priced record from this table.
    ("extract", "browserbase", "default"): OperationPricing(usd_per_unit=0.004),
    ("extract", "browserbase", "proxy"): OperationPricing(usd_per_unit=0.007),
    ("fetch", "exa", "default"): OperationPricing(usd_per_unit=0.001),
    ("answer", "exa", "default"): OperationPricing(usd_fixed=0.005),
    ("monitor", "exa", "default"): OperationPricing(usd_fixed=0.015),
    ("agent", "exa", "minimal"): OperationPricing(usd_fixed=0.012),
    ("agent", "exa", "low"): OperationPricing(usd_fixed=0.025),
    ("agent", "exa", "medium"): OperationPricing(usd_fixed=0.10),
    ("agent", "exa", "high"): OperationPricing(usd_fixed=0.50),
    ("agent", "exa", "xhigh"): OperationPricing(usd_fixed=1.00),
    ("map", "tavily", "default"): OperationPricing(usd_per_unit=0.008, unit_batch=10),
    ("map", "tavily", "instructions"): OperationPricing(usd_per_unit=0.016, unit_batch=10),
    ("chat", "parallel", "speed"): OperationPricing(usd_fixed=0.005),
    ("chat", "parallel", "lite"): OperationPricing(usd_fixed=0.005),
    ("chat", "parallel", "base"): OperationPricing(usd_fixed=0.010),
    ("chat", "parallel", "core"): OperationPricing(usd_fixed=0.025),
    ("response", "parallel", "low"): OperationPricing(usd_fixed=0.010),
    ("response", "parallel", "medium"): OperationPricing(usd_fixed=0.050),
    ("response", "parallel", "high"): OperationPricing(usd_fixed=0.250),
    ("task", "parallel", "lite"): OperationPricing(usd_fixed=0.005),
    ("task", "parallel", "base"): OperationPricing(usd_fixed=0.010),
    ("task", "parallel", "core"): OperationPricing(usd_fixed=0.025),
    ("task", "parallel", "core2x"): OperationPricing(usd_fixed=0.050),
    ("task", "parallel", "pro"): OperationPricing(usd_fixed=0.100),
    ("task", "parallel", "ultra"): OperationPricing(usd_fixed=0.300),
    ("task", "parallel", "ultra2x"): OperationPricing(usd_fixed=0.600),
    ("task", "parallel", "ultra4x"): OperationPricing(usd_fixed=1.200),
    ("task", "parallel", "ultra8x"): OperationPricing(usd_fixed=2.400),
    ("monitor", "parallel", "lite"): OperationPricing(usd_per_unit=0.003),
    ("monitor", "parallel", "base"): OperationPricing(usd_per_unit=0.010),
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
