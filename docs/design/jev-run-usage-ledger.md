# JevAgent run usage ledger

## What and why

One `JevAgent.arun()` spends tokens in many places: the main generative loop, Jev decision calls (preflight gate, tool selector, scope breadth, recall guard, done checks), and several helper agents that run their own generative loops (clarification, run state, reviewer, handoff, the fresh-continuation agent, and a chosen specialist). Today only the main loop reaches the agent's `UsageTracker`. Every other call reports a scattered, per-feature `JevUsage` or `UsageRollup` that nothing adds up, and every Jev fail-open path drops the billed usage TypeSafe attaches to its errors (`details["usage"]`). `agent.get_usage()` and `agent.response.usage` therefore under-report a run.

This change makes the JevAgent's own `UsageTracker` the single ledger for the whole run. Every generative and decision call, from every agent the run spawns, is recorded once and priced from the SDK pricebook (`ModelPricingRegistry.default()` over `PROVIDER_PRICING`). At the end, the ledger's total, generative, and decision rollups are attached to `agent.response.usage`. If any usage cannot be recorded or priced, the run fails closed with an error telling the user the failure is on Vidbyte's side.

## How it works

```
JevAgent.arun ─► BaseAgent.generate_reply ─► JevRuntime.arun
                                               │  opens JevUsageAccount.scope()  (active ledger = this agent's UsageTracker)
                                               │
   decision calls ── DecisionModelRunner.arun ─┼─► Hook A: ledger.record_call(response, kind=DECISION)
   (gate, selector, done checks, recall guard, │          billed failure: record details["usage"], failed=True, re-raise
    scope breadth, future PRs)                 │
                                               │
   main loop ── AgentRuntime.record_call ──────┼─► existing hook: same tracker, kind=GENERATIVE
                                               │
   helper/specialist agents ── generate_reply ─┼─► Hook B: nested agent records into its own tracker,
   (clarification, run state, reviewer,        │          then merges its rollup into the parent ledger in `finally`
    handoff, fresh continuation, specialist)   │
                                               ▼
                         JevUsageAccount.require_accounted()  at every phase boundary and before returning
                         JevUsageAccount.report()  ─► JevResponse ─► agent.response.usage (JevUsageReport)
```

1. **Active ledger (lib contract).** `vidbyte/lib/usage_ledger.py` holds a `UsageLedger` Protocol and a `ContextVar` naming the ledger for the current run, with `active_usage_ledger()` and `usage_ledger_scope(ledger)`. It lives in `vidbyte/lib/` because the decision runner does; `UsageTracker` satisfies the Protocol structurally, so `lib` never imports `agents`. A ledger is active only inside a JevAgent run, so plain `BaseAgent` behavior does not change.
2. **Hook A: decision model.** `DecisionModelRunner.arun` is the one function every Jev call passes through, including the open PRs that call the runner directly. With a ledger active, it records each response as `UsageKind.DECISION`. On a `VidbyteSdkError` whose `details["usage"]` is a mapping, it records that billed usage as a failed call (the requested model names it) and re-raises, so every caller's fail-open policy is unchanged but the bill is kept.
3. **Hook B: generative agents.** `BaseAgent.generate_reply` checks for an active ledger. If one exists and it is not this agent's own tracker, the agent makes its own tracker the active ledger for its run, then merges `self.get_usage()` into the parent in `finally`, so even a helper that fails still reports what it spent. Each helper keeps its own `get_usage()` (feature records still read it), and the parent receives each run exactly once, so the per-run `reset()` no longer loses usage.
4. **Main loop.** `AgentRuntime` already records every model response into the agent's tracker; `record_call` defaults to `UsageKind.GENERATIVE`, so the runtime is unchanged.
5. **Record shape.** `UsageRecord` gains `kind: UsageKind` and `failed: bool`. `UsageRollup` gains `unaccounted_call_count`, the number of calls that reached `record_call` but produced no record (no parseable usage, unknown provider, or a parse or pricing error). `merge()` carries all three. `rollup(kind=...)` filters calls by kind; operations count only in the unfiltered total.
6. **Fail closed.** `JevUsageAccount` (`vidbyte/agents/jev/usage.py`) owns the policy. `require_accounted()` raises `UsageAccountingError` when the ledger is corrupted, holds an unaccounted call, or holds a call or operation the pricebook could not price. `JevRuntime` calls it after the gate, after a delegated specialist, after the run state is written, after the tool selector, before each finish-attempt continuation, and before returning, so a failure stops further spending at the next phase boundary. The error carries the A003 diagnostic packet with the failure reasons (`UsageAccountingFailure` enum) and counts. `generate_reply` re-raises it unwrapped, so the user sees the usage message rather than a generic `AgentExecutionError`. Fail-open handlers cannot swallow it, because it is raised only from `JevRuntime`, never inside a Jev call.
7. **Structural guard.** `JevAgent` rejects, at construction, a specialist whose `agent` is not a `BaseAgent` or replaces `generate_reply` (as `AggregateAgent` and `MultiAgent` do), because Hook B cannot meter it.
8. **Report.** `JevUsageAccount.report()` builds `JevUsageReport(total, generative, decision)`, three `UsageRollup`s from the same ledger. `JevResponse.finished/stopped/delegated` store it on `JevAgentResponse.usage` and overwrite `metadata["usage_rollup"]` with the total, so `get_usage()`, result metadata, and `agent.response.usage` agree. The old single-preflight-call field becomes `JevAgentResponse.preflight_usage`. The tool selector's metadata also reports the exact Jev model that answered.

## Files

- `vidbyte/lib/usage_ledger.py` (new): `UsageLedger` Protocol, active-ledger ContextVar and scope.
- `vidbyte/lib/enums/usage.py` (new) and `vidbyte/lib/enums/__init__.py`: `UsageKind`, `UsageAccountingFailure`.
- `vidbyte/lib/errors/base.py` and `vidbyte/lib/errors/__init__.py`: `UsageAccountingError`.
- `vidbyte/lib/runners/decision.py`: Hook A.
- `vidbyte/agents/pricing/records.py`, `vidbyte/agents/pricing/tracker.py`: record kind and failure, unaccounted count, guarded pricing, kind-filtered rollup, merge carries the new fields.
- `vidbyte/agents/base.py`: Hook B and the unwrapped re-raise.
- `vidbyte/agents/jev/usage.py` (new): `JevUsageAccount`.
- `vidbyte/agents/jev/runtime.py`, `agent.py`, `response.py`, `preflight.py`, `__init__.py`: scope, phase checks, specialist guard, report, `preflight_usage`, selector model.
- `vidbyte/lib/dataclasses/jev.py`: `JevUsageReport`; `JevAgentResponse.usage` / `preflight_usage`.
- `skills/jev-agent/SKILL.md`: the change-workflow rule on usage.
- Tests: Jev test fakes return priced usage; two preflight assertions move to `preflight_usage`; new `tests/test_jev_usage_ledger.py`.

## Risks and open questions

- **Unpriced models now fail.** A JevAgent whose generative model is missing from the pricebook (for example `gpt-4.1-mini` today) fails closed after its first phase. This is the requested behavior; the fix is a pricebook entry. A construction-time check was rejected because providers such as OpenRouter report their own cost and have no pricebook rows.
- **Spend before the stop.** Checks run at phase boundaries, not after every main-loop call, so one main-loop pass can run before the error.
- **Breaking field change.** `JevAgentResponse.usage` changes from one preflight call's `ProviderUsage` to the run's `JevUsageReport`. The public docs snippet in the `vidbyte` repo (`next-app/app/api/docsRegistry.js`) needs a follow-up wording change.
- **Out of scope.** Per-feature source labels (which feature spent what), per-attempt done/review/handoff history, and metering of nested agents outside a JevAgent run.
- **Open PRs.** #458, #499, #502 and the other Jev PRs that call `DecisionModelRunner` or spawn `BaseAgent`s are metered automatically; their hand-rolled usage summing can be deleted after this lands.

## Verification

- `python scripts/run_ci.py --stage source` (lint, compile, write-path checks, full pytest) and `--stage package`.
- `tests/test_jev_usage_ledger.py` proves: decision, main-loop, helper-agent, and specialist usage all land in one total; billed Jev failures are recorded and the caller still fails open; a helper's two `arun`s are both counted; `response.usage`, `get_usage()` and `metadata["usage_rollup"]` agree; an unpriced call, an unreported usage, and a recording error each raise `UsageAccountingError`; a plain `BaseAgent` outside a JevAgent run is unchanged; a non-`BaseAgent` specialist is rejected.
