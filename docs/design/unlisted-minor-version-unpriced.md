# Design Doc: An unlisted minor version is unpriced, not priced as its major

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-27
**Last Updated:** 2026-10-27

## 1. Overview

`ModelPricingRegistry.resolve` falls back to the longest priced key that a model id extends, if the rest of the id is a
release suffix. `_is_release_suffix` rejects only lettered suffixes (`-flash`), so a digit suffix such as `-6` counts as
a release. `claude-opus-5-6` is therefore priced as `claude-opus-5`. The spend cap's construction check
(`AgentSpendCap.model_refusal`) trusts the same lookup, so it admits a model whose real price is unknown. The usage
ledger then reports a confident but wrong cost. This change treats a one- or two-digit dash number as a minor version,
which is a different SKU, so the id resolves to `None` and every caller fails closed.

## 2. Goals & Non-Goals

### Goals
- `claude-opus-5-6`, `claude-sonnet-5-6`, `claude-fable-5-2`, `mistral-large-4-1` and similar ids resolve to `None`.
- A dated snapshot of such an id (`claude-opus-5-6-20261201`) also resolves to `None`. Without this, it would be priced
  as `claude-opus-5`. This is the shape a response's `model` field can report.
- Real releases still price: `-20251001`, `-0915`, `-250930`, `-2026-03-05`, `-latest`, `.0`.
- A spend-capped agent on `claude-opus-5-6` is refused at construction, before any paid call.

### Non-Goals
- Dotted minor versions on a major-only key, such as `glm-5.4` priced as `glm-5`. The existing test
  `test_custom_table_prices_releases_by_prefix_but_not_variants` locks `m-1.2` as a release of `m-1`. Changing that is a
  pricing-policy decision, so it is left to the founder (§13).
- No rate, row, `PRICING_AS_OF` or vintage-lock change.

## 3. Background & Context

The SDK's `UsageTracker` is the billing meter for both `max_spend_usd` and the Vidbyte gateway. A wrong price that is
still present keeps `cost_complete` true, so the error is silent. That is worse than the `None` this registry already
uses for unknown models. The bug was reproduced offline by `repro_15_prefix_sibling_price.py`, which exits 1 on
`origin/main` f0896962.

## 4. Requirements

### Functional Requirements
0. A remainder that does not start with a separator (`-` or `.`) is not a release: `glm-4.5v` is GLM's vision model,
   and `claude-opus-50` is not Opus 5. This is the same bug in mid-token form, and the sweep found real ids such as
   `glm-4.5v` and `glm-4.6v` that it priced as their text siblings.
1. A remainder that starts with `-` followed by one or two digits and then `-` or the end of the string is not a
   release.
2. Requirement 1 also applies after leading patch tokens (`.1-6`), so `glm-5.1-6` does not fall through to `glm-5`.
3. Every other remainder keeps today's verdict.

### Non-Functional Requirements
- No change to any id in `ProviderModelRegistry`'s catalog. An offline sweep of 152 catalog ids found that none changes
  resolution.
- Lookup cost is unchanged: one precompiled regex match per candidate key.

## 5. High-Level Design

`_is_release_suffix` gains two early returns after the `-latest` check. The first rejects a remainder with no
separator. The second rejects one that matches a precompiled class pattern, `_MINOR_VERSION_SUFFIX`. There are no other components.

## 6. Detailed Design

### 6.1 ModelPricingRegistry._is_release_suffix
**File:** `vidbyte/lib/registries/pricing.py` (Modified)
1. `-latest` is a release, as before.
2. A remainder with no leading `-` or `.` is not a release.
3. A remainder that matches `(?:\.\d+)*-\d{1,2}(?:-|$)` is a minor version, so the function returns False.
4. Otherwise a lettered dash suffix is a variant, as before.

Edge cases: date groups (`-2026-03-05`) start with four digits, so they stay releases. `-001`-style revisions have three
digits, so they also stay releases.

## 7. Data Model Changes
N/A: no record or schema changes.

## 8. API Changes
N/A: same signatures. `resolve` returns `None` for more ids.

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/lib/registries/pricing.py` | Minor-version suffix is not a release |
| MODIFY | `tests/test_agent_pricing.py` | Regression tests for the resolver |
| MODIFY | `tests/features/loop_spend_cap/test_loop_spend_cap_refusals.py` | The spend cap refuses the unlisted id |
| CREATE | `docs/design/unlisted-minor-version-unpriced.md` | This doc |

## 10. Testing Plan

### Unit Tests
- `PricingPrefixFallbackTests.test_an_unlisted_minor_version_does_not_inherit_its_majors_rate` checks Opus, Sonnet,
  Haiku and Fable `5-N`, and `mistral-large-4-1`. [Silent Failure]
- `...test_a_dated_snapshot_of_an_unlisted_minor_version_stays_unpriced` checks `claude-opus-5-6-20261201`, and checks
  that `claude-opus-5-5-6` is not priced as `claude-opus-5`. [Hidden Failure]
- `...test_a_suffix_without_a_separator_is_another_model` checks `glm-4.5v`, `glm-4.6v`, `claude-opus-50`, `gpt-5.45`
  and `grok-4.55`. [Silent Failure]
- `...test_release_markers_still_price_like_their_base_key` is extended with `claude-opus-5-5-20261015`,
  `claude-sonnet-5-5-latest` and `gpt-5.4-2026-03-05`. [Hidden Assumption: two-digit date groups]
- `...test_custom_table_minor_versions_are_unpriced_but_dated_releases_are_not` covers `m-1-2`, `m-1-12`,
  `m-1-2-20260101`, `m-1.2-3`, `m-10` and `m-1v` (unpriced), and `m-1-2026-01-01`, `m-1-0915`, `m-1-001` and `m-1.2`
  (priced). [Edge Case]

### Integration Tests
- `test_a_capped_agent_on_an_unlisted_minor_version_is_refused`: `BaseAgent(..., max_spend_usd=1.0)` on
  `anthropic:claude-opus-5-6` raises the spec's unpriced message, and the uncapped control constructs. [Silent Failure]

### Manual / QA
1. Given `origin/main`, when `repro_15_prefix_sibling_price.py` runs, then it exits 1. On this branch it exits 0.
   [Silent Failure]

## 11. Dependencies & External Services
None.

## 12. Rollout & Deployment
Gateway customers get this fix only after an SDK release and a backend pin bump. A customer who requests an unlisted minor
version is then refused (spend cap) or metered as unpriced, instead of being billed at the older model's rate. No flag.
Rollback is a revert.

## 13. Open Questions
- [ ] Founder: should a dotted minor on a major-only key (`glm-5.4`, `MiniMax-M3.1`, `kimi-k3.1`) also be unpriced?
  Today it inherits the major's rate, and an existing test locks `m-1.2` as a release.

## 14. Alternatives Considered
### `re.fullmatch(r"-\d{1,2}", remainder)` (the probe fix)
- Why rejected: `claude-opus-5-6-20261201` would still be priced as Opus 5. `claude-opus-5-5-6` would move from
  `claude-opus-5-5` to the older `claude-opus-5`.
### A whitelist of release shapes
- Why rejected: it is a larger behavior change across every provider, and nothing here requires it.
