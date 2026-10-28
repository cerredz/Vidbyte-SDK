# Design Doc: An actor-model call lost in flight is unmeasured spend

**Status:** Implemented
**Author:** Claude
**Created:** 2026-10-28
**Last Updated:** 2026-10-28

## 1. Overview

The `actor_model_broadcast` runtime sends the user's prompt to every actor, so six actors (five prebuilt and the
root) each send a model request at once. The root's answer completes the run, and the broker then cancels every
other actor's task, including the five requests still waiting on the provider. Those requests reached the provider
and were billed, but they left no record and were not counted as unaccounted, so the run's ledger reported itself as
fully measured while most of its spend was missing. This change records every actor call that fails after it was
sent: billed usage when the error carries it, otherwise one unaccounted call when the request was lost in flight
(cancelled, or timed out with no HTTP status) in DIRECT mode. The broker also waits for the cancelled actors to stop
before it returns, so those records reach a parent ledger.

## 2. Goals & Non-Goals

### Goals
- A DIRECT actor request cancelled while it waits on the provider counts as one unaccounted call, so
  `cost_measured` is False and a capped parent fails closed, as #1200 already does for a timed-out linear call.
- A status-less timeout in an actor call counts the same way.
- A billed 200 with no usable text in an actor call is recorded as a failed call with its usage, as the linear
  runtime records it.
- The records land before `BaseActorRuntime.arun` returns, so `BaseAgent` merges them into a parent ledger.

### Non-Goals
- Letting cancelled actors finish their requests so their exact usage is known (changes run latency and semantics).
- Gateway modes (`AUTO`, `VIDBYTE_MANAGED`): the gateway meters and bills those calls itself; #1200 left them alone
  for the same reason.
- The linear runtime, which #1200 already covers.

## 3. Background & Context

Live evidence (phase 2 of the 2026-10-27 billing-readiness run, metering proxy on 127.0.0.1:8792/8793, merged
`main` `0f50b908`): every `actor_model_broadcast` run sent six billed requests while the agent's ledger recorded
one or two, with `unaccounted_call_count == 0` and `cost_measured == True`.

| Run | Proxy truth (6 calls) | SDK ledger | Unrecorded |
|---|---|---|---|
| claude-haiku-4-5 BC2 | $0.005383 | $0.000089 (1 call) | 98% |
| claude-haiku-4-5 BC1 | $0.007278 | $0.000791 (2 calls) | 89% |
| claude-sonnet-5-5 L1 | $0.010086 | $0.008094 (5 calls) | 20% |
| claude-haiku-5-5 BC4 | $0.0005978 | $0.0000128 (1 call) | 98% |

Mechanism, in `vidbyte/agents/runtimes/actor/broker.py`:
- `BroadcastActorRuntime.send` puts the boot message into every actor's inbox.
- Each actor's `invoke_actor_completion` awaits `RunnerHandle.invoke`; it records a call only after the reply returns.
- `BaseActorRuntime.arun`'s `finally` block calls `task.cancel()` on every actor task and returns at once.
  `CancelledError` lands inside the pending HTTP request; nothing is recorded. `cancel()` only requests the stop, so
  even a recording made in the cancellation handler would run after `BaseAgent` merged the run's tracker into its
  parent.

`AgentRuntime._record_failed_call_usage` (#1200) is the linear runtime's rule for the same situation; the actor
broker never calls it.

## 4. Requirements

### Functional Requirements
1. When an actor call raises after it was sent and the error carries billed usage (`exc.details["usage"]`), the
   active ledger records it with `record_billed_failure`.
2. Otherwise, when the error is `asyncio.CancelledError` or a `ProviderRequestError` with `status_code is None`, and
   the handle's mode is `TextModelMode.DIRECT`, the active ledger counts one unaccounted call.
3. A provider error with an HTTP status records nothing (Anthropic does not bill errors).
4. `BaseActorRuntime.arun` waits for every cancelled actor task to finish before it returns.
5. `UsageLedger` (the Protocol) declares `record_unaccounted_call`, which `UsageTracker` already implements.

### Non-Functional Requirements
- No new dependency; no change to any price, admission rule, or customer-visible amount.
- Behaviour of point-to-point and the default actor runtime is unchanged when nothing is lost.

## 5. High-Level Design

```
actor task ── invoke_actor_completion ── RunnerHandle.invoke ──> provider
                     │ success: ledger.record_call(raw)
                     │ failure: _record_failed_actor_call(exc)
                     │     billed usage on error -> record_billed_failure
                     │     cancelled / status-less, DIRECT -> record_unaccounted_call
arun finally: cancel every actor task -> await gather(tasks) -> return -> BaseAgent merges into parent
```

## 6. Detailed Design

### 6.1 BaseActorRuntime.invoke_actor_completion
**File(s):** `vidbyte/agents/runtimes/actor/broker.py` **Type:** Modified
The model call is wrapped in an inner `try`; any `BaseException` calls `_record_failed_actor_call(exc, target_model)`
and re-raises. The success path is unchanged.

### 6.2 BaseActorRuntime._record_failed_actor_call
**Type:** New private helper. Mirrors `AgentRuntime._record_failed_call_usage`: billed usage first, then the lost-
in-flight rule restricted to DIRECT. The model label is the actor's override, else the runner config's model.
Edge cases: no active ledger -> nothing; `KeyboardInterrupt` and other non-request errors -> nothing.

### 6.3 BaseActorRuntime.arun cleanup
After `task.cancel()` for every task, `await asyncio.gather(*tasks, return_exceptions=True)`. `AgentActor.start`
catches `CancelledError` and returns, so the wait is bounded by one event-loop turn per actor.

### 6.4 UsageLedger Protocol
**File(s):** `vidbyte/lib/usage_ledger.py` Adds `record_unaccounted_call(self) -> None` to the Protocol.

## 7. Data Model Changes
None.

## 8. API Changes
None public. `UsageLedger` gains a method its only implementation (`UsageTracker`) already has.

## 9. File Change Manifest
| File | Change |
|---|---|
| `vidbyte/agents/runtimes/actor/broker.py` | record failed actor calls; await cancelled actors |
| `vidbyte/lib/usage_ledger.py` | Protocol method |
| `tests/features/sdk_model_usage/test_actor_in_flight_failure_usage.py` | new regression tests |
| `tests/features/sdk_model_usage/README.md`, `FEATURE.md` | index, log, test map |
| `docs/design/actor-cancelled-calls-unmeasured.md` | this document |

## 10. Testing Plan

### Unit / feature tests (`test_actor_in_flight_failure_usage.py`; only `HttpTransport._send_once` is scripted)
- [Silent Failure] Broadcast: root answered at once, five actors held 0.5 s and cancelled -> 1 call recorded,
  5 unaccounted, `cost_measured` False, cost equal to the answered call. Fails on `main` (0 unaccounted).
- [Hidden Failure] The same run under a parent `usage_ledger_scope`: the parent receives the 5 unaccounted calls.
  Fails on `main`, and fails with only the recording change (the cleanup wait is required).
- [Edge Case] Point-to-point: one call, measured, nothing unaccounted (passes on `main` and after).
- [Hidden Failure] Status-less timeout in an actor call -> 1 unaccounted. Fails on `main`.
- [Hidden Assumption] 529 with a status -> nothing recorded, still measured (passes on `main` and after).
- [Silent Failure] Thinking-only billed 200 in an actor call -> one failed record priced exactly. Fails on `main`.

### Integration / live
- Re-run `actor_model_broadcast` live through the metering proxy after merge: proxy rows (6) == recorded calls +
  unaccounted calls, `cost_measured` False.

## 11. Dependencies & External Services
None.

## 12. Rollout & Deployment
SDK only; ships with the next release. No backend pin change is required.

## 13. Open Questions
- Should broadcast runs instead await the other actors' replies (exact usage, slower runs)? Left for the founder.

## 14. Alternatives Considered
### Alternative 1: shield in-flight actor requests from cancellation and record their usage
Exact cost, but every broadcast run would wait for its slowest actor and keep paying for answers it discards.
Rejected as a behaviour change outside a billing fix.
### Alternative 2: count only in the broker's cleanup (number of tasks busy at cancel time)
Busy does not mean a request is in flight (an actor may be sending a message), so it over- and under-counts.
