# Enforce AgentLoopSettings.timeout_seconds in the Linear Runtime

## Overview

`AgentLoopSettings.timeout_seconds` is validated at construction, exported into
session checkpoints, and accepted by the YAML document schema — but the linear
agent runtime never enforces it. `to_runtime_config()` drops the field,
`AgentRuntimeConfig` has no place to carry it, and `_budget_stop` checks only
`max_iterations`, `max_tokens`, and `max_tool_calls`. Any consumer that sets the
value (the vidbyte research harness sets 3600s/600s/600s today) is silently
unbounded in wall-clock time.

This change makes the existing setting real: the deadline flows into
`AgentRuntimeConfig` and the runtime stops at the first iteration boundary past
the deadline, with a new `AgentStopReason.TIMEOUT` stop reason.

## Goals

- `AgentLoopSettings.timeout_seconds`, when set, bounds the wall-clock duration
  of one direct agent run (`AgentRuntime._arun_once`).
- The stop is graceful: it produces a normal `AgentResult` with
  `metadata["stop_reason"] == "timeout"`, identical in shape to every other
  budget stop, so callers that already switch on stop reasons need no new
  error-handling path.
- Enforcement is checked between iterations via the existing middleware clock,
  which keeps the check deterministic under a faked clock and avoids any
  cancellation mid-tool-call or mid-model-call.
- Backward compatible: agents that do not set `timeout_seconds` (the default)
  behave exactly as before.

## Non-Goals

- Cancelling an in-flight model call or tool call at the deadline. A hung model
  call is bounded by the per-call HTTP `timeout_seconds` on the runner config
  and a hung tool call by `ToolSettings.tool_timeout_seconds`; this change adds
  the loop-level layer between them. Hard cancellation composes badly with
  non-idempotent tool writes and is deliberately out of scope.
- Enforcing the deadline in the prosecutor-defender-judge algorithm
  (`vidbyte/agents/algorithms/prosecutor_defender_judge.py`), multi-agent
  runners, or `Harness.execute(timeout_seconds=...)` — each already has its own
  timeout mechanism.
- Adding `timeout_seconds` to the model-visible loop-settings prompt block
  (`_render_loop_settings_block`). That block is intentionally limited to
  countable budgets; changing model-visible prompt text has wider behavioral
  blast radius than this PR warrants.

## Background

The runtime loop (`vidbyte/agents/runtime.py:231`) checks budgets at the top of
every iteration through `_budget_stop` (line 1726). Elapsed wall-clock time is
already a first-class concept in the runtime: `started_at =
self.middleware.clock()` (line 186) and `elapsed_seconds` is computed for
output-contract floors (line 1810). The missing pieces are only the plumbing
(settings → runtime config) and one more check in `_budget_stop`.

Layered timeout design after this change, innermost first:

1. `BaseAgent(timeout_seconds=...)` → per-model-call HTTP timeout (exists).
2. `ToolSettings.tool_timeout_seconds` → per-tool-call `asyncio.wait_for`
   (exists, `runtime.py:1275`).
3. `AgentLoopSettings.timeout_seconds` → whole-loop deadline (**this PR**).
4. `Harness.execute(timeout_seconds=...)` → per-harness-execution deadline
   (exists, unused by the main repo today).

## Requirements

1. `AgentRuntimeConfig` gains `timeout_seconds: float | None = None`, validated
   in `__post_init__` as a strictly positive number when provided.
2. `AgentLoopSettings.to_runtime_config()` forwards `timeout_seconds`.
3. `AgentStopReason` gains `TIMEOUT = "timeout"`.
4. `_budget_stop` compares elapsed wall-clock time (middleware clock minus
   `started_at`) against `config.timeout_seconds` and returns a stopped result
   when the deadline has passed.
5. The stop message names the configured limit, matching the existing
   "stopped after reaching max_iterations." phrasing.
6. `_render_loop_settings_block` docstring no longer claims `timeout_seconds`
   has no live runtime measurement; the block itself stays unchanged.

## High-Level Design

Three files change. `vidbyte/lib/dataclasses/agents.py` extends the two
contracts (`AgentStopReason`, `AgentRuntimeConfig`). `vidbyte/agents/settings/
loop.py` forwards the field in `to_runtime_config()`. `vidbyte/agents/runtime.py`
threads `started_at` into `_budget_stop` and adds the elapsed-time check after
the existing three budget checks.

The check is placed in `_budget_stop` (not around the loop with
`asyncio.timeout`) so a deadline expiry cannot interrupt a tool mid-write; the
run stops cleanly at the next iteration boundary, exactly like max_iterations.
When multiple budgets are exceeded simultaneously, the existing checks win
because they run first; either stop reason is honest in that case.

## Detailed Design

### `vidbyte/lib/dataclasses/agents.py`

Add to `AgentStopReason` (after `MAX_ERROR_CALLS`, before the sliding-window
entry's neighbors — placed with the other budget-stop reasons):

```python
TIMEOUT = "timeout"
```

Extend `AgentRuntimeConfig` with the field and validation, mirroring the
existing `__post_init__` loop for int budgets but handling float semantics:

```python
timeout_seconds: float | None = None
```

```python
if self.timeout_seconds is not None and self.timeout_seconds <= 0:
    raise ValueError("timeout_seconds must be greater than zero when provided.")
```

### `vidbyte/agents/settings/loop.py`

`to_runtime_config()` adds one keyword: `timeout_seconds=self.timeout_seconds`.
No new validation — `AgentLoopSettings._validate_timeout_seconds` already ran
at construction and `AgentRuntimeConfig.__post_init__` re-checks defensively.

### `vidbyte/agents/runtime.py`

`_budget_stop` gains a `started_at: float` keyword parameter and appends the
deadline check:

```python
def _budget_stop(self, *, iteration_count: int, tokens_used: int | None, contexts: Sequence[ToolCallContext], started_at: float) -> AgentResult | None:
    # Returns a stopped result when any configured loop budget or wall-clock deadline is exhausted.
    ...
    if self.config.timeout_seconds is not None and self.middleware.clock() - started_at >= self.config.timeout_seconds:
        return self._stopped_result(
            "Agent runtime stopped after reaching timeout_seconds.",
            stop_reason=AgentStopReason.TIMEOUT,
            iteration_count=iteration_count,
            tokens_used=tokens_used,
            contexts=contexts,
        )
    return None
```

The single call site (line 250) passes `started_at=started_at`, which is
already in scope.

`_render_loop_settings_block`'s docstring drops `timeout_seconds` from the
"intentionally excluded" example list and instead notes the deadline is
enforced at the budget check but kept out of model-visible prompt text.

## Data Model Changes

N/A - no persisted schema changes. Session checkpoints already round-trip
`loop.timeout_seconds` through `_export_loop_settings` /
`_restore_loop_settings` (vidbyte/agents/base.py:476, 534); restored settings
now pick up enforcement automatically.

## API Changes

Additive only:

- `AgentRuntimeConfig.timeout_seconds` (new optional field).
- `AgentStopReason.TIMEOUT` (new enum member; string value `"timeout"` appears
  in `AgentResult.metadata["stop_reason"]`, which is documented as
  machine-readable reason text).

No existing signature, field, or default changes.

## File Change Manifest

| Action | File | Change |
|---|---|---|
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | `AgentStopReason.TIMEOUT`; `AgentRuntimeConfig.timeout_seconds` + `__post_init__` validation |
| MODIFY | `vidbyte/agents/settings/loop.py` | Forward `timeout_seconds` in `to_runtime_config()`; header docstring line |
| MODIFY | `vidbyte/agents/runtime.py` | `_budget_stop` deadline check + `started_at` parameter, call-site update, `_render_loop_settings_block` docstring |

3 files modified; 0 created; 0 deleted.

## Dependencies

None. No new imports beyond `AgentStopReason`/`AgentRuntimeConfig`, already
imported in every touched file.

## Rollout

Backward compatible by default: `timeout_seconds` defaults to `None`, and
`AgentLoopSettings` validation (positive float) already rejects bad values at
construction. Consumers that already set the value — notably the vidbyte
research harness's `config.yaml` (3600/600/600) — gain enforcement the moment
they upgrade the SDK pin, which is the intended effect and the reason the
values were configured in the first place. SDK version stays `0.1.0` until the
maintainer's next release cut; the vidbyte repo pins by commit.

Canonical CI: `python -m pip install -e ".[dev]"` then `python scripts/run_ci.py`
(from the worktree: source stage with `PYTHONPATH` set to the worktree root,
package stage without, per the local CI verification field guide).

## Open Questions

- Should the model-visible loop-settings block eventually show elapsed/limit
  time so an agent can wrap up before the deadline? Deferred: prompt-text
  changes deserve their own PR with snapshot comparisons.

## Alternatives Considered

- **Wrap the whole loop in `asyncio.timeout`** (as `harnesses/execution.py`
  and `workflows/machine.py` do). Rejected: hard cancellation can kill a
  non-idempotent tool (e.g. a `save_source` DB write) mid-flight, and the
  layered design already bounds each call individually. Between-iteration
  checking gives the same guarantee with strictly safer failure semantics.
- **Enforce at `BaseAgent.arun`** rather than the runtime. Rejected: the
  runtime owns all other budget enforcement and the middleware clock;
  duplicating the deadline one level up splits budget logic across files.
- **New `deadline_seconds` field** distinct from the existing
  `timeout_seconds`. Rejected: the field already exists, is documented, and is
  set by consumers; adding a second spelling of the same concept guarantees
  confusion about which one is real.
