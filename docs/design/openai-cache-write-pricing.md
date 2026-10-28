# Design Doc: OpenAI cache writes are priced at the cache-write rate

**Status:** Draft · **Author:** Claude · **Created:** 2026-10-27 · **Last Updated:** 2026-10-27

## 1. Overview
OpenAI's Responses usage reports prompt-cache writes inside `input_tokens`, as
`input_tokens_details.cache_write_tokens`, and bills them at the model's cache-write rate. For example, gpt-6-sol has
input $2, cache write $2.50 and output $10 per million. `OpenAIUsage` read only `cached_tokens`, so it priced writes as
plain input. A gpt-6-sol call with 10k input tokens (4k of them cache writes) and 100 output tokens cost $0.021 in the
SDK, but $0.023 at OpenAI. Codex's usage payload carries the same count as a top-level `cache_write_input_tokens`, and
that count was ignored too. The backend compensates today with `_cache_write_surcharge_nanousd`
(`backend/services/model_gateway/metering.py`). This change moves that exact formula into the SDK.

## 2. Goals & Non-Goals
**Goals:**
- Price `min(writes, input - cached)` tokens at the cache-write rate, scaled by the same long-context factor as input.
  Price the rest of the uncached input at the input rate, as before.
- Read the count from `input_tokens_details.cache_write_tokens`, or else from the top-level `cache_write_input_tokens`
  (Codex).
- Match the backend surcharge formula exactly, so that removing the surcharge leaves gateway bills unchanged.

**Non-Goals:**
- Rates, `PRICING_AS_OF` and the vintage lock: no rate changes, so no lock refresh.
- #17 service-tier rates (a founder decision).
- MiniMax's unread `cache_write_per_million` (#16c): its usage reports no write count to price.

## 3-4. Requirements
1. With `cache_write_per_million` None, or a base input rate of 0 or less, the cost is unchanged (the backend's
   guards).
2. `writes` is clamped to the uncached input. Cached tokens are never also billed as writes.
3. The cost is `subset_billing_cost` + `billable × (cache_write × tier_input / base_input − tier_input) / 1e6`. This
   is the backend's `gap` term.

## 5-6. Design
`vidbyte/agents/pricing/openai.py` (Modified): adds a `cache_write_input_tokens` field, parsed in
`from_usage_payload`. `cost_usd` adds the cache-write premium on top of `subset_billing_cost`.

## 7-8. Data Model / API
`OpenAIUsage.cache_write_input_tokens: int | None = None`. The field is appended last, so positional construction is
unchanged.

## 9. File Change Manifest
| Action | File | Reason |
|---|---|---|
| MODIFY | `vidbyte/agents/pricing/openai.py` | Parse and price cache writes |
| MODIFY | `tests/test_agent_pricing.py` | Regression tests |
| CREATE | `docs/design/openai-cache-write-pricing.md` | This doc |

## 10. Testing Plan
- The gpt-6-sol worked example costs 0.023 (Decimal truth). [Silent Failure]
- The Codex top-level key is priced the same way. [Hidden Assumption]
- Writes greater than the uncached input are clamped, so cached tokens are not billed twice. [Edge Case]
- No cache-write rate, or zero writes, leaves the cost unchanged. [Edge Case]
- Over the long-context threshold, the write rate scales with the input tier. [Hidden Failure]
- Parity with the backend: for the same usage, the SDK's added cost equals the backend's surcharge formula. The
  formula is re-derived independently in the test.
- `repro_16_17_dead_rates.py`: the #16a and #16b lines go from UNDER and unpriced to OK and priced. The script still
  exits 1 because of #17, which is out of scope.

## 12. Rollout (critical)
**This SDK change must ship together with removing the backend surcharge, in the same SDK-pin bump. Otherwise gateway
customers are billed twice for OpenAI cache writes.** Gateway customers see the change only after an SDK release and a
backend pin bump.

## 13. Open Questions
- [ ] The parity rounding: the backend rounds its surcharge up per call in nano-USD, while the SDK sums floats. The
  difference after the swap is at most 1 nano-USD per call.
