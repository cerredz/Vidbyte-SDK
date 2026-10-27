# Design Doc: Anthropic Usage Price Modifiers (Fast Mode and US Data Residency)

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-27
**Last Updated:** 2026-10-27

---

## 1. Overview

`AnthropicUsage.cost_usd` prices every Anthropic Messages call at standard
rates, even when the response's `usage` says the call ran in fast mode
(`usage.speed == "fast"`) or on US-only infrastructure
(`usage.inference_geo == "us"`). Anthropic bills both at a premium: fast
mode is 2x on Opus 5.5 ($8/$40 instead of $4/$20) and on Opus 5 and Opus 4.8
($10/$50 instead of $5/$25), and US-only inference is 1.1x on every token
bucket of Claude 4.6 and later models. This change prices both modifiers from
the response's own `usage`. The fast rates live in the pricebook as data on
the three Opus rows that offer fast mode, and the data-residency multiplier is
a named constant. A speed or geography the SDK cannot price leaves the call
visibly unpriced instead of silently billing standard rates.

---

## 2. Goals & Non-Goals

### Goals
- Price `usage.speed == "fast"` on Claude Opus 5.5, Opus 5 and Opus 4.8 at
  Anthropic's published fast rates, with prompt-caching multipliers applied on
  top, across the whole context window.
- Price `usage.inference_geo == "us"` at 1.1x on input, output, 5-minute and
  1-hour cache writes, and cache reads. The multiplier stacks with fast mode,
  caching, and the Claude Haiku 5.5 over-100K tier.
- Price `"global"`, `"not_available"`, and an absent or null `inference_geo`
  at 1x, bit-for-bit identical to today's result.
- Fail safe: an unknown `speed`, an unknown `inference_geo`, or a fast call on
  a model with no fast rate makes `cost_usd` return `None`. The tracker then
  records the call as unpriced (`cost_usd=None`, `cost_complete=False`) and
  never bills it at standard rates.
- Regression tests that price the two live payloads from 2026-10-27 and
  assert Anthropic's documented price.

### Non-Goals
- OpenAI tier pricing. `ModelPricing.tier_rates` on OpenAI rows stays
  metadata, read by nothing, and another worker owns that change. OpenAI
  pricing behavior does not change.
- Batch API pricing (50% off), Priority Tier, and server-tool fees (web
  search, code execution). The SDK's Anthropic adapter calls only
  `POST /v1/messages`, and none of these are part of this bug.
- Bedrock, Google-managed Vertex, and Microsoft Foundry regional pricing.
  The SDK's Anthropic adapter talks to the first-party API.
- Changing the backend gateway. It bills with the pinned SDK release
  (`vidbyte-sdk==0.3.0`), so customers see this fix only after an SDK
  release and a backend pin bump.
- Converting cost arithmetic to `Decimal`. See section 14.

---

## 3. Background & Context

- **Why now:** the 2026-10-27 billing-readiness run made real Anthropic calls
  through the SDK and compared the SDK's cost with Anthropic's pricing page.
  Two scenarios under-billed:
  - Opus 5.5 with `speed: "fast"`, usage `{"input_tokens": 13,
    "output_tokens": 6, ..., "inference_geo": "global", "speed": "fast"}`:
    the truth is 13 x $8 + 6 x $40 per MTok = **$0.000344**, but the SDK
    returned $0.000172 (50% under).
  - Opus 5.5 with `inference_geo: "us"`, the same tokens, and
    `"speed": "standard"`: the truth is (13 x $4 + 6 x $20) x 1.1 per MTok =
    **$0.0001892**, but the SDK returned $0.000172 (9.1% under).
- **Current state:** `AnthropicUsage.from_usage_payload` keeps the whole
  usage dict in `raw`, and the adapter (`vidbyte/providers/anthropic.py`)
  passes the provider's usage dict through unchanged, so `speed` and
  `inference_geo` already reach the parser. `cost_usd` reads only the four
  token buckets and the `cache_creation.ephemeral_1h_input_tokens`
  breakdown.
- **Why `usage` and not the request:** a workspace can default to US-only
  inference (`default_inference_geo: "us"`) with no field on the request, and
  on Opus 4.6 a fast request runs at standard speed and reports
  `"standard"`. Only the response says what was billed.
- **Sources:**
  - https://platform.claude.com/docs/en/about-claude/pricing, sections
    "Fast mode pricing", "Data residency pricing", "Prompt caching" and
    "Long context pricing".
  - https://platform.claude.com/docs/en/build-with-claude/fast-mode, section
    "Checking which speed was used".
  - https://platform.claude.com/docs/en/manage-claude/data-residency,
    sections "Response", "Workspace-level restrictions" and "Pricing".

  These were fetched on 2026-10-27. The live responses showed that models
  before 4.6 report `inference_geo: "not_available"`.

---

## 4. Requirements

### Functional Requirements
1. When `usage.speed == "fast"` and the model's pricebook row has a `fast`
   tier, every bucket is priced at the fast rates: input, output, 5-minute
   write (1.25x fast input), 1-hour write (2x fast input) and cache read
   (the model's own read multiplier x fast input, so 0.05x on Opus 5.5 and
   0.1x on Opus 5 and Opus 4.8).
2. Fast rates apply at every prompt length; no prompt-length tier applies to
   a fast call.
3. When `usage.speed` is absent, null or `"standard"`, the row's standard
   rates apply exactly as before.
4. When `usage.speed` is any other value (an unknown string, wrong case, or a
   non-string), `cost_usd` returns `None`.
5. When `usage.speed == "fast"` and the row has no `fast` tier, `cost_usd`
   returns `None`.
6. When `usage.inference_geo == "us"`, the whole token cost is multiplied by
   `ANTHROPIC_US_INFERENCE_GEO_MULTIPLIER` (1.1), on top of fast mode,
   caching, and the Haiku 5.5 over-100K tier.
7. When `usage.inference_geo` is `"global"`, `"not_available"`, absent or
   null, the multiplier is 1x and the result is bit-identical to today's.
8. When `usage.inference_geo` is any other value, `cost_usd` returns `None`.
9. The pricebook carries the fast rates on `claude-opus-5-5`,
   `claude-opus-5` and `claude-opus-4-8`, and on no other row.
10. `PRICING_AS_OF` moves to `2026-10-27`, and the C010 lock is refreshed
    only through its own `--refresh-lock` command.

### Non-Functional Requirements
- **Performance:** two dict reads and at most one enum lookup per priced
  call. This is negligible.
- **Security:** none. No new input surface; values are read from the
  provider response the SDK already parses.
- **Observability:** an unpriceable modifier surfaces as an unpriced record
  (`UsageRecord.cost_usd is None`, `UsageRollup.cost_complete is False`), the
  same signal an unknown model gives today. `JevUsageAccount` already fails
  closed on it (`UsageAccountingFailure.UNPRICED_CALL`).
- **Reliability:** no exception paths are added for provider data. A
  malformed modifier never corrupts the ledger or drops the token counts.
- **Accuracy:** each test asserts the documented price, computed by hand in
  `Decimal` from the per-MTok rates, to a relative tolerance of 1e-12. That
  is a million times tighter than the repo's default `pytest.approx`. See
  section 10.

---

## 5. High-Level Design

The price of one Anthropic call depends on three things: the model's rates,
the speed it ran at, and where it ran. The pricebook already holds per-model
rates, and `ModelPricing.tier_rates` already exists for named rate variants
(OpenAI's standard, batch, flex and fast rows, and DeepSeek's peak and
off-peak rows). This change adds an `ANTHROPIC_FAST_MODE_RATES` table, keyed
model -> `"fast"` -> rate fields with the same field names as the OpenAI tier
rows, and points the three fast-capable Opus rows' `tier_rates` at it. The
data-residency multiplier applies to every Claude 4.6+ model and every
bucket, so it is one named constant, the same choice the repo made for the
1-hour cache write's 2x.

```
provider usage dict ──> AnthropicUsage.raw
                              │
pricebook row ──> cost_usd ───┼─ _rates_for_speed(row)          -> ModelPricing | None
                              │     speed absent/null/"standard" -> row
                              │     "fast" and row.tier_rates["fast"] -> fast ModelPricing
                              │     anything else                -> None (unpriced)
                              ├─ _inference_geo_multiplier()     -> float | None
                              │     "us" -> 1.1; "global"/"not_available"/absent/null -> 1.0
                              │     anything else                -> None (unpriced)
                              └─ existing bucket formula on the chosen rates, x multiplier
                                        │
                              UsageTracker._record ──> UsageRecord(cost_usd=float|None)
```

`cost_usd` stays the one main function. It picks the rate card for the
reported speed and the multiplier for the reported geography, then runs the
unchanged bucket formula (input, 5-minute writes, 1-hour writes at 2x active
input, cache reads, output) on that rate card. Finally it multiplies by the
geography multiplier. Fast mode reuses the existing formula through a fast
`ModelPricing` built from the tier row, so prompt-caching multipliers apply
on top of fast rates by construction. The fast card has no prompt-length
threshold, which matches "fast mode pricing applies across the full context
window".

The values `usage.speed` and `usage.inference_geo` come from closed sets that
Anthropic documents, so AGENTS.md requires enums for them:
`AnthropicSpeed` and `AnthropicInferenceGeo` in `vidbyte/lib/enums/usage.py`.
They are read straight from `raw` at pricing time, the same way the 1-hour
cache breakdown is read. No new dataclass field is added, so the usage
record's shape, equality and constructor stay unchanged.

---

## 6. Detailed Design

### 6.1 AnthropicUsage cost formula

**File(s):** `vidbyte/agents/pricing/anthropic.py`
**Type:** Modified

#### What it does
Prices one Anthropic Messages call from its native usage. It now honors the
reported speed and inference geography.

#### Interface / API
```python
def cost_usd(self, pricing: ModelPricing | None) -> float | None: ...
def _rates_for_speed(self, pricing: ModelPricing) -> ModelPricing | None: ...
def _inference_geo_multiplier(self) -> float | None: ...
```

#### Logic / Algorithm
1. `cost_usd`: if `pricing` is None or no token field was reported, return
   None (unchanged).
2. `speed_pricing = self._rates_for_speed(pricing)` and
   `geo_multiplier = self._inference_geo_multiplier()`. If either is None,
   return None.
3. Run the existing bucket formula with `speed_pricing` in place of
   `pricing`. That formula covers the threshold tier, cache-read and
   cache-write scaling with the active input rate, and 1-hour writes at 2x
   active input.
4. Return `token_cost * geo_multiplier`. Multiplying by 1.0 is exact in IEEE
   754, so every non-US result is bit-identical to the old one.

`_rates_for_speed(pricing)`:
1. Read `raw.get("speed")`. If it is None, return `pricing`.
2. Convert it to `AnthropicSpeed`. A `ValueError` or `TypeError` returns
   None.
3. If the speed is `STANDARD`, return `pricing`.
4. Look up `(pricing.tier_rates or {}).get(speed.value)`. If nothing is
   there, return None.
5. Return `ModelPricing(input_per_million=row["input_per_million"],
   output_per_million=row["output_per_million"],
   cache_read_per_million=row.get("cached_input_per_million"),
   cache_write_per_million=row.get("cache_write_per_million"))`. It has no
   threshold, which is the full-context-window rule.

`_inference_geo_multiplier()`:
1. Read `raw.get("inference_geo")`. If it is None, return 1.0.
2. Convert it to `AnthropicInferenceGeo`. A `ValueError` or `TypeError`
   returns None.
3. Return `ANTHROPIC_US_INFERENCE_GEO_MULTIPLIER` for `US`, and 1.0 for
   `GLOBAL` and `NOT_AVAILABLE`.

#### Edge Cases & Error Handling
- `speed: null` or `inference_geo: null` means unreported, so it is priced
  as standard. Anthropic reports `"fast"` on every successful fast call and
  `"us"` on every US-only call, so null cannot hide a premium on the
  first-party API.
- `"FAST"`, `"US"`, `"eu"`, `1` and `{}` are unknown, so the call is
  unpriced.
- A fast row missing `input_per_million` or `output_per_million` is a
  pricebook programming error. It raises `KeyError`, which the tracker
  records as a corrupted ledger (fail-closed); a pin test keeps the shipped
  rows complete.
- `"us"` on a pre-4.6 model cannot occur: Anthropic returns 400 for
  `inference_geo` on those models, and they report `"not_available"`. No
  per-model gating is added.

### 6.2 Pricebook fast rates

**File(s):** `vidbyte/lib/registries/pricing.py`
**Type:** Modified

#### What it does
Adds `ANTHROPIC_FAST_MODE_RATES` and sets `tier_rates=` on
`claude-opus-5-5`, `claude-opus-5` and `claude-opus-4-8`. It also bumps
`PRICING_AS_OF` to `2026-10-27`.

#### Interface / API
```python
ANTHROPIC_FAST_MODE_RATES: dict[str, dict[str, dict[str, float]]] = {
    "claude-opus-5-5": {"fast": {"input_per_million": 8.0, "cached_input_per_million": 0.4, "cache_write_per_million": 10.0, "output_per_million": 40.0}},
    "claude-opus-5":   {"fast": {"input_per_million": 10.0, "cached_input_per_million": 1.0, "cache_write_per_million": 12.5, "output_per_million": 50.0}},
    "claude-opus-4-8": {"fast": {"input_per_million": 10.0, "cached_input_per_million": 1.0, "cache_write_per_million": 12.5, "output_per_million": 50.0}},
}
```
Anthropic publishes only fast input and output. The cache fields apply that
model's published caching multipliers to fast input, as the pricing page
says: 5-minute write 1.25x; read 0.05x on Opus 5.5 and 0.1x on Opus 5 and
Opus 4.8. The comment above the table says this.

#### Edge Cases & Error Handling
- Dated IDs (`claude-opus-5-5-20261101`) resolve to the base row through
  release-suffix prefix matching, so they carry its `tier_rates`.
- Opus 4.7 and 4.6 have no fast tier. Anthropic runs a fast request on 4.6
  at standard speed and reports `"standard"`, so a `"fast"` report on them
  would be unpriced.

### 6.3 Data-residency multiplier constant

**File(s):** `vidbyte/lib/constants/pricing.py`
**Type:** Modified

```python
ANTHROPIC_US_INFERENCE_GEO_MULTIPLIER: float = 1.1
```
This sits next to `ANTHROPIC_CACHE_WRITE_1H_INPUT_MULTIPLIER`, with an
`@intent` comment that cites the pricing page.

### 6.4 Usage vocabularies

**File(s):** `vidbyte/lib/enums/usage.py`, `vidbyte/lib/enums/__init__.py`
**Type:** Modified

```python
class AnthropicSpeed(str, Enum):
    STANDARD = "standard"
    FAST = "fast"

class AnthropicInferenceGeo(str, Enum):
    GLOBAL = "global"
    US = "us"
    NOT_AVAILABLE = "not_available"
```
Both are exported from `vidbyte/lib/enums/__init__.py`. The root `vidbyte`
public API does not change.

---

## 7. Data Model Changes

### 7.1 `PROVIDER_PRICING[ANTHROPIC]` rows

**Change type:** Modified. Three rows gain `tier_rates`, and
`PRICING_AS_OF` moves to `2026-10-27`.

**Migration strategy:**
- Forward: `python -m lint.rules.c010_pricebook_vintage_bump --refresh-lock`
  rewrites `lint/pricebook_vintage_lock.json` for the new digests and
  vintage. The backend treats the vintage as the pricebook identity of a
  resumable run, so a run started on the old vintage does not resume on the
  new rates.
- Rollback: revert the commit. The lock reverts with it.

`ModelPricing` and `AnthropicUsage` gain no fields.

---

## 8. API Changes

N/A. There is no HTTP endpoint. The Python surface gains two public enums in
`vidbyte.lib.enums`. `AnthropicUsage.cost_usd` keeps its signature, but it
can now return `None` for a priced model when the response reports a
modifier the pricebook cannot price.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/anthropic-usage-price-modifiers.md` | This design |
| MODIFY | `vidbyte/agents/pricing/anthropic.py` | Price speed and inference geography from usage |
| MODIFY | `vidbyte/lib/registries/pricing.py` | Fast-mode rate table, three `tier_rates`, vintage bump |
| MODIFY | `vidbyte/lib/constants/pricing.py` | `ANTHROPIC_US_INFERENCE_GEO_MULTIPLIER` |
| MODIFY | `vidbyte/lib/enums/usage.py` | `AnthropicSpeed`, `AnthropicInferenceGeo` |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Export the two enums |
| MODIFY | `lint/pricebook_vintage_lock.json` | Written only by `--refresh-lock` |
| CREATE | `tests/features/sdk_model_usage/test_anthropic_price_modifiers.py` | Regression tests |
| MODIFY | `tests/features/sdk_model_usage/README.md`, `FEATURE.md` | File index, contract, regression log |
| MODIFY | `tests/features/sdk_model_catalog/test_catalog_pricing_contract.py` | Vintage pin moves to `2026-10-27` |
| CREATE | `scripts/test_anthropic_usage_price_modifiers.py` | Section 10 verification script (PASS/FAIL per case) |

---

## 10. Testing Plan

Expected costs are written by hand in `Decimal`, from the per-MTok prices on
Anthropic's page, never from `PROVIDER_PRICING`. The SDK returns binary
floats, and no evaluation order of the formula lands exactly on the nearest
double for every vector. A probe over eight vectors found each order 1 ULP
off on at least one. So each case asserts the documented price to a
relative tolerance of 1e-12, which is exact to the cent on any bill under
$10 billion. Test payloads use the wire strings (`"fast"`, `"us"`), not the
enums, so they exercise exactly what Anthropic sends.

### Unit Tests (`AnthropicUsage.cost_usd` against the default pricebook)
- Live Opus 5.5 fast payload: $0.000344. [Silent Failure]
- Live Opus 5.5 US payload: $0.0001892. [Silent Failure]
- Opus 5.5 fast + US, same tokens: $0.0003784. [Silent Failure]
- Opus 5.5 fast + cache (100 in, 1,000 x 5m, 1,000 x 1h, 10,000 read,
  500 out): $0.0508. [Silent Failure]
- Opus 5.5 fast + US + cache, all stacked: $0.05588. [Silent Failure]
- Haiku 5.5 over 100K (1,000 in + 120,000 read, 100 out) + US: $0.007425.
  [Edge Case]
- Haiku 5.5 over 100K with 110,000 1-hour writes + US: $0.121825.
  [Edge Case]
- Haiku 5.5 at exactly 100K input (100 out) + US stays on the base tier:
  $0.011055. [Edge Case]
- Opus 5 fast and Opus 4.8 fast (13 in, 6 out): $0.00043. [Silent Failure]
- Opus 5 fast cache write and read (1,000 x 5m write, 1,000 read):
  $0.0135. [Silent Failure]
- Opus 4.5 `not_available` (13 in, 6 out): $0.000215, bit-identical to the
  same usage with no `inference_geo`. [Hidden Assumption]
- `"global"`, absent, and null geo, and `"standard"`, absent, and null
  speed: all bit-identical to the no-field cost. [Hidden Assumption]
- Fast on a model with no fast rate (Opus 4.7, Opus 4.6, Sonnet 5.5,
  Haiku 5.5) returns None. [Hidden Failure]
- Unknown speed (`"turbo"`, `"FAST"`, `1`, `True`, `{}`) returns None.
  [Hidden Failure]
- Unknown geo (`"eu"`, `"US"`, `0`, `[]`) returns None. [Hidden Failure]
- A caller-registered row whose fast tier omits cache rates prices cache
  buckets the way a `ModelPricing` without them does: reads and writes at
  the input rate. [Hidden Assumption]

### Pricebook pins
- `tier_rates["fast"]` on the three Opus rows equals the published values,
  typed by hand. [Silent Failure]
- Each fast cache rate over the fast input rate equals that row's own
  standard cache rate over its standard input rate, so the derived numbers
  keep the published multipliers. [Silent Failure]
- No other Anthropic row has `tier_rates`. [Hidden Assumption]
- A dated Opus 5.5 ID prices fast at the fast rate. [Edge Case]

### Integration Tests
- `UsageTracker.record_call` with the live fast payload records $0.000344,
  and the rollup is complete. [Silent Failure]
- `UsageTracker.record_call` with an unknown speed keeps the record and its
  tokens, sets `cost_usd` to None and `cost_complete` to False, and leaves
  `recording_integrity` INTACT. [Hidden Failure]
- A full `Agent` run through `AnthropicProvider` in DIRECT mode, with
  `HttpTransport.request` scripted to return a fast + US response, gives
  `get_usage().cost_usd` of $0.0003784 for exactly one call. This proves
  the adapter forwards both fields end to end. [Hidden Assumption]

### Manual / QA Test Cases
1. Given the 2026-10-27 live usage JSON, when it is priced with
   `UsageTracker`, then the costs are $0.000344 (fast) and $0.0001892
   (US). [Silent Failure]
2. Given `python -m lint.rules.c010_pricebook_vintage_bump` after the
   change, then C010 is CLEAN only with the bumped vintage and refreshed
   lock. [Hidden Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Anthropic pricing docs | platform.claude.com, fetched 2026-10-27 | Source of fast rates and the 1.1x multiplier | Rates change. The vintage and lock make a change explicit. |
| Anthropic Messages `usage` | `speed`, `inference_geo` fields | Billing signals | A new value prices as None until the pricebook learns it. |

---

## 12. Rollout & Deployment

- No feature flag. This is a pricing correction.
- Not a breaking API change. The visible behavior changes are higher
  (correct) costs for fast and US calls, and `None` for unpriceable
  modifiers.
- Deployment order: merge, cut an SDK release, then bump the backend's
  `vidbyte-sdk` pin. The gateway bills with `vidbyte-sdk==0.3.0` until then.
- Rollback: revert the PR.

---

## 13. Open Questions

- [ ] Does Vidbyte's own Anthropic workspace default to US-only inference?
  If so, every gateway call costs Vidbyte 1.1x while SDK 0.3.0 bills 1x.
  This is an ops check for the founder.
- [ ] The backend's handling of an unpriced call (`cost_complete=False`)
  should be confirmed to block or flag the charge rather than bill $0.

---

## 14. Alternatives Considered

### Alternative 1: Derive fast cache rates in code by the fast/standard input ratio
- What: store only the published fast input and output, and scale the row's
  cache rates by `fast_input / input`.
- Why rejected: it adds float noise (0.2 x 8 / 4 = 0.4000000000000001) and
  a ratio branch. It also diverges from the existing tier-row shape, which
  carries explicit cache fields. Explicit data plus a consistency test
  gives the same guarantee.

### Alternative 2: A 2x fast multiplier constant
- What: `ANTHROPIC_FAST_MODE_MULTIPLIER = 2.0`.
- Why rejected: Anthropic publishes fast mode as per-model rates, not a
  multiplier, and a constant would silently price a fast call on any model.

### Alternative 3: Bill an unknown modifier at standard, or raise
- What: treat unknown values as standard, or raise from `cost_usd`.
- Why rejected: standard reproduces the under-billing bug for any future
  premium. Raising makes the tracker mark the ledger corrupted and drop the
  record, which loses the token counts. `None` is the repo's existing
  "unknown rate" outcome: the record stays and the rollup says it is
  incomplete.

### Alternative 4: Gate the 1.1x on the model generation (4.6+)
- What: a per-row flag for data-residency eligibility.
- Why rejected: Anthropic rejects `inference_geo` on earlier models, and
  they report `"not_available"`, so `usage` alone is exact. The flag would
  add pricebook data with no behavior.

### Alternative 5: Compute cost in `Decimal`
- What: exact decimal arithmetic inside `cost_usd`, returned as a float.
- Why rejected for this PR: it changes every Anthropic result by up to one
  ULP (about $1e-20), which is unrelated to this bug, and makes Anthropic's
  numerics differ from every other provider's. It can be its own change if
  billing ever needs it.
