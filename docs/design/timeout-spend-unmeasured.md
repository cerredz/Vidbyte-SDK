# Design Doc: A model call lost in flight is unmeasured spend

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-27
**Last Updated:** 2026-10-27

## 1. Overview

When a DIRECT model call fails with a `ProviderRequestError` that has no HTTP status, the request may have reached the
provider and been billed. This covers a read timeout, a dropped connection, and a stream that broke mid-reply. The
runtime's failed-call branch (`AgentRuntime`, the `except Exception` around `handle.invoke`) records a failure only when
the error carries billed usage. So the timed-out attempt left no trace in the ledger: `cost_measured` stayed True, and a
`max_spend_usd` run kept spending while it believed its meter was complete. This change counts each such attempt as one
unaccounted call. `cost_measured` then turns False, and the spend cap fails closed with its existing "model calls
reported no usage" cause.

## 2. Goals & Non-Goals

### Goals
- Each attempt that fails with a status-less `ProviderRequestError` and no billed usage adds 1 to
  `UsageRollup.unaccounted_call_count`.
- A capped run stops with the blind-meter text instead of treating the unknown bill as $0.
- Failures that carry a status (4xx/5xx: the provider answered and reported the outcome) are unchanged.
- A failure that already carries billed usage is recorded once, as today, and is not also counted as unaccounted.

### Non-Goals
- Distinguishing a connect failure (never sent, so $0) from a read timeout. The transport maps both to the same
  status-less error. Treating both as unmeasured fails closed, which is the safe direction for billing.
- Cancellation (`BaseException`) and the Jev `DecisionModelRunner` path. Both have the same shape of gap and are named
  as follow-ups.

## 3. Background & Context

`cost_measured` and the spend cap read `unaccounted_call_count` (`vidbyte/agents/spend_cap.py`). The repro
`repro_N5_timeout_spend_unmeasured.py` sends a Haiku call that times out, then falls back to Sonnet. The ledger shows
one call and `cost_measured=True`. It exits 1 on `origin/main` f0896962.

## 4. Requirements

### Functional Requirements
1. `UsageTracker.record_unaccounted_call()` adds one to the unaccounted count and nothing else.
2. In the runtime's failed-call branch: if the error carries billed usage, call `record_billed_failure` (unchanged).
   Otherwise, if it is a `ProviderRequestError` whose `status_code` is None, call `record_unaccounted_call()`.
3. Each attempt is counted, so a timed-out retry counts again.

### Non-Functional Requirements
- No new I/O. Metering stays fail-open for execution: it never raises into the loop.

## 5. High-Level Design

```
handle.invoke raises -> billed usage on error? -> record_billed_failure
                     -> else ProviderRequestError with no status -> record_unaccounted_call
                     -> retry / fallback / raise (unchanged)
```

## 6. Detailed Design

### 6.1 UsageTracker.record_unaccounted_call
**File:** `vidbyte/agents/pricing/tracker.py` (Modified). `def record_unaccounted_call(self) -> None`.

### 6.2 AgentRuntime failed-call branch
**File:** `vidbyte/agents/runtime.py` (Modified). Adds one `elif` after the billed-usage check.

## 7. Data Model Changes
N/A: `UsageRollup` is unchanged, and its existing `unaccounted_call_count` carries the signal.

## 8. API Changes
New public method `UsageTracker.record_unaccounted_call()`. `UsageLedger` (the lib Protocol) is unchanged, because no
lib-level caller needs it yet.

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/agents/pricing/tracker.py` | Add `record_unaccounted_call` |
| MODIFY | `vidbyte/agents/runtime.py` | Count a status-less request failure |
| CREATE | `tests/features/sdk_model_usage/test_in_flight_failure_usage.py` | Regression tests |
| MODIFY | `tests/features/sdk_model_usage/FEATURE.md`, `README.md` | Contract, regression log, file index |
| CREATE | `docs/design/timeout-spend-unmeasured.md` | This doc |

## 10. Testing Plan

### Unit Tests
- `test_record_unaccounted_call_leaves_cost_but_clears_cost_measured`. [Silent Failure]

### Integration Tests (real adapters, runtime, fallback and pricing; scripted `HttpTransport._send_once`)
- `test_a_timed_out_call_then_fallback_is_unmeasured`: an `httpx.ReadTimeout` on Haiku, then Sonnet answers. The result
  is `unaccounted_call_count == 1`, `cost_measured` is False, and the Sonnet cost is still recorded. [Silent Failure]
- `test_a_capped_run_stops_blind_after_a_timeout`: with `max_spend_usd`, the reply carries the blind-meter stop text that
  names `1 model calls reported no usage`. [Hidden Failure]
- `test_a_provider_error_with_a_status_stays_measured`: a 429 followed by the fallback gives `unaccounted == 0`.
  [Hidden Assumption: a status means that the provider reported the outcome]
- `test_billed_usage_on_a_status_less_error_is_recorded_once`: a status-less error that carries usage gives one failed
  record and `unaccounted == 0`. [Hidden Failure: double count]
- `test_each_timed_out_attempt_counts`: two timeouts before a fallback answer give `unaccounted == 2`. [Edge Case]

### Manual / QA
1. Given `origin/main`, when `repro_N5_timeout_spend_unmeasured.py` runs, then it exits 1. On this branch it exits 0.

## 11. Dependencies & External Services
None. No socket opens in any test.

## 12. Rollout & Deployment
Gateway customers get this fix only after an SDK release and a backend pin bump. A capped run that hits a provider
timeout then stops as unmeasured instead of continuing. Rollback is a revert.

## 13. Open Questions
- [ ] Should a cancelled in-flight call (agent timeout, task cancel), and a timed-out Jev decision call, also count as
  unaccounted? They are the same gap, and I recommend it as a follow-up.
- [ ] Should the transport tag connect-phase failures (never sent) so that they stay measured at $0?

## 14. Alternatives Considered
### Record a $0 failed call
- Why rejected: it would claim a measured $0 for a call that may have been billed.
### Count in the transport
- Why rejected: the transport has no ledger. The runtime is the one place that owns the run's tracker
  (field guide: "Keep model usage accounting agent-owned").
