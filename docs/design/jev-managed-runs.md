# Managed Jev runs

## What and why

Vidbyte's backend has a managed Jev gateway at `/api/v1/models/typesafe`. A
developer calls it with a `vb_live_` Vidbyte key, Vidbyte calls TypeSafe on
their behalf, and the cost comes out of their Vidbyte wallet. The backend
groups calls into runs, keyed by an `X-Vidbyte-Run-Id` header. It bills whole
cents as a run's total grows and rounds up the last part-cent when the run is
closed through `POST /api/v1/models/runs/{run_id}/close`.

The SDK already routes Jev decisions through Vidbyte's managed gateway by
default. Each decision currently lacks a run ID, though, and the SDK never
closes a run. As a result:

- Every call from one key on one day lands in a single "daily" bucket, so no
  run has its own cost and a charge cannot be traced to a run.
- The last part-cent of each run is only collected by the backend's idle
  cleanup job, an hour later.

Retries have a related gap. The adapter generates an idempotency key for each
retried decision but never sends it, so the gateway cannot tell a retry from a
new call. The companion backend change (Vidbyte repo,
`docs/design/model-gateway-idempotent-retries.md`) replays a saved answer for a
repeated key. This SDK change sends the key.

## How it works

1. **Existing managed mode.** The run wrapper uses
   `DecisionModelConfig.vidbyte_managed()` and its existing pinned gateway and
   credential handling. This change adds only the close URL for a scoped run.
2. **A run scope.** `JevManagedRun(config)` is an async context manager that
   puts a `JevManagedRunScope(run_id="jev:<uuid4 hex>")` into a `ContextVar`
   for the duration of the block. A context variable follows the run into
   `asyncio.gather` fan-out without threading a parameter through the gate,
   done checks, continuation, and tool selector. A nested `JevManagedRun`, for
   example a specialist JevAgent, joins the outer run and does not close it.
   For direct TypeSafe configs, the scope does nothing.
3. **Headers.** In managed mode, the TypeSafe adapter adds:
   - `X-Vidbyte-Run-Id` from the active scope, and marks the scope as used;
   - `Idempotency-Key` when the call can be retried.

   Direct TypeSafe calls receive neither managed header.
4. **Close.** When the outermost scope exits, it calls
   `DecisionModelRunner.aclose_run(run_id)`, but only if a call was made, since
   the backend has no session for a run that made no calls. The adapter sends
   that POST with no retries. Closing is best-effort: an SDK error during close
   is logged and never fails the agent's run, because the backend's cleanup job
   closes the run anyway.
5. **JevAgent.** `JevRuntime.arun` runs its whole body inside
   `JevManagedRun(runtime_settings.decision)`.

The context variable lives in `vidbyte/providers/typesafe.py`, the only module
that reads it. Putting it under `vidbyte/lib/jev/` would create an import
cycle: `lib/jev` → `runners` → `providers` → `lib/jev`.

## Files

- `vidbyte/lib/constants/jev.py`: run-close path, managed run headers, and run
  ID prefix.
- `vidbyte/lib/dataclasses/jev.py`: `JevManagedRunScope`.
- `vidbyte/lib/dataclasses/model_configs.py`: close URL resolution using the
  existing managed-mode endpoint.
- `vidbyte/providers/typesafe.py`: the context variable, managed headers,
  `close_run`.
- `vidbyte/lib/runners/decision.py`: `aclose_run`.
- `vidbyte/lib/jev/managed.py` (new) and `vidbyte/lib/jev/__init__.py`:
  `JevManagedRun`.
- `vidbyte/agents/jev/runtime.py`: wrap `arun`.
- `tests/test_jev_managed_runs.py` (new).

## Risks and open questions

- Closing adds one HTTP call at the end of each managed run. It is bounded by
  the config's timeout and sent with no retries.
- Run IDs are client-generated UUIDs. The backend scopes each run to the key
  that opened it, so a guessed ID cannot touch another user's run.

## Verification

- New tests cover:
  - a direct call sends no new headers;
  - one run ID across every call in a scope, and different IDs across runs;
  - `Idempotency-Key` on retried managed calls;
  - close sent once, to the right URL, only after a call;
  - a nested scope joins its parent and does not close it;
  - a close failure does not raise;
  - JevAgent runs open and close a managed run.
