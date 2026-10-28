# Design Doc: A capped run checks its spend cap before a middleware retry

**Status:** Implemented
**Author:** Claude
**Created:** 2026-10-28
**Last Updated:** 2026-10-28

## 1. Overview

`AgentLoopSettings.max_spend_usd` must stop a run once its measured spend reaches the cap or can no longer be
measured, and after that stop no further model call may follow (`tests/features/loop_spend_cap/FEATURE.md`). A
`ModelRetryMiddleware` retry broke that rule. `AgentRuntime._invoke_with_middleware` records the failed attempt and
then sends the retry straight away, with no cap check. Two situations produce that extra paid request:
- an in-flight timeout, which #1200 correctly counts as unaccounted, so the ledger is blind;
- a billed failed attempt (a 200 with no usable text) that alone reaches the cap.

The fix calls the existing `_spend_cap_stop` before acting on a retry decision, the same check every loop check
point uses.

## 2. Goals & Non-Goals

### Goals
- A capped run whose ledger is blind, or at its cap, after a failed model call stops with `max_spend` instead of
  sending a middleware retry.
- Uncapped runs retry exactly as before.

### Non-Goals
- Changing `ModelRetryMiddleware`, the fallback switch (already covered: it continues to CP1), or the stop texts.
- Pricing, admission at construction, or any customer-visible amount.

## 3. Background & Context

This came from the phase-2 live billing run on merged `main` `0f50b908`, through the metering proxy:
- **Run:** `A15/timeout-capped-retry` — Haiku 4.5, `max_spend_usd=1.0`, `ModelRetryMiddleware(max_attempts=2)`,
  8 s timeout, and the proxy holding the first reply 25 s.
- **Billed:** 2 calls (the timed-out call plus the retry).
- **Ledger:** 1 call recorded, `unaccounted=1`, `cost_measured=False`; the run then stopped with `max_spend` at CP1.
- **What should have happened:** the retry is a second paid request sent after the meter was already blind. The
  correct outcome is 1 billed call and the stop.

Offline repro on `2a084078` (`repro_A15_retry_after_blind_meter.py`):
- **Timeout case:** 2 requests sent; stop `max_spend`, `unaccounted=1`, measured False.
- **Billed thinking-only reply at the cap:** 2 requests sent; stop `max_spend`.

## 4. Requirements

1. In `_invoke_with_middleware`, when `on_model_error` returns RETRY, call `_spend_cap_stop`.
2. When it returns a stop result, return that result (with the current model-call and compaction counts) instead of
   sleeping and retrying.
3. With no cap, `_spend_cap_stop` returns `None` at once (NFR-1), so uncapped runs are unchanged.

## 5. High-Level Design

```
model call fails -> record failed-call usage (billed, or unaccounted when lost in flight)
               -> middleware.on_model_error
                    RETRY -> _spend_cap_stop -> stop result? return it (max_spend) : retry as before
                    ABORT / raise -> unchanged
```

## 6. Detailed Design

**File:** `vidbyte/agents/runtime.py` (modified), `AgentRuntime._invoke_with_middleware`. Six lines are added
before the retry backoff.

The returned `AgentResult` follows the path a middleware abort already uses:
- `_arun_once` finishes it through `_finish_result`.
- The external callers (`reflexion.py`, `multi_provider_agentic_grader.py`) already handle an `AgentResult` here,
  and the grader already recognises `MAX_SPEND`.

**Edge cases:**
- A retry after a status-bearing error with a measured ledger below the cap still proceeds.
- A blind ledger stops even when its measured part is below the cap; that is the existing blind-stop rule.

## 7. Data Model Changes
None.

## 8. API Changes
None.

## 9. File Change Manifest
| File | Change |
|---|---|
| `vidbyte/agents/runtime.py` | cap check before a middleware retry |
| `tests/features/loop_spend_cap/test_loop_spend_cap_runtime.py` | two regression tests |
| `vidbyte/agents/spend_cap.py`, `vidbyte/agents/README.md` | name the new check |
| `tests/features/loop_spend_cap/FEATURE.md`, `README.md` | contract, regression log, suite map |
| `docs/design/spend-cap-refuses-model-retry.md` | this document |

## 10. Testing Plan

Both tests use only a scripted `HttpTransport._send_once`; everything else is the real runtime, middleware and
ledger. Each test also runs an uncapped control, which must still retry (2 requests, `final_response`).

- [Silent Failure] A billed failed attempt (empty refusal, priced) reaches the cap:
  - capped: 1 request, `max_spend`, the reached text, the ledger holding only the failed call.
  - Fails on `main` (2 requests).
- [Hidden Failure] An in-flight timeout (`httpx.ReadTimeout`) with a $1 cap:
  - capped: 1 request, `max_spend`, the blind text naming 1 call with no usage, `unaccounted=1`, measured False.
  - Fails on `main` (2 requests).
- Live, after the merge: re-run `A15/timeout-capped-retry`. Expect exactly 1 billed call, `max_spend`, and
  `cost_measured=False`.

## 11. Dependencies & External Services
None.

## 12. Rollout & Deployment
SDK only; ships with the next release.

## 13. Open Questions
None.

## 14. Alternatives Considered

### Alternative 1: make `ModelRetryMiddleware` read the ledger
Rejected:
- Middleware has no access to the agent's tracker.
- A custom retry middleware would still bypass the cap.

### Alternative 2: check only when the failure was an in-flight loss
Rejected: a billed failure that reaches the cap must also stop. `_spend_cap_stop` already covers both, with the
existing stop texts and metadata.
