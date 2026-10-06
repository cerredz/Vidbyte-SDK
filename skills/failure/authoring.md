# Failure Authoring and Extension Guide

## Add a rule, not a new exception class

Use `@rule` to describe an observable condition. Register the decorated function
on the Session that should own the policy. Importing a module must not change
another Session's behavior.

```python
from vidbyte import (
    Failure,
    FailureCode,
    FailureDisposition,
    FailurePhase,
    MiddlewareHook,
    RuleErrorMode,
    rule,
)

@rule(
    code=FailureCode.ACTION_WRONG_TARGET,
    on=MiddlewareHook.AFTER_TOOL_CALL,
    on_match=FailureDisposition.ROUTE,
    on_error=RuleErrorMode.OPEN,
    priority=50,
)
def detect_wrong_target(context):
    if context.tool_result and context.tool_result.metadata.get("target_ok") is False:
        return Failure(
            code=FailureCode.ACTION_WRONG_TARGET,
            source="target_check",
            phase=FailurePhase.ACTION,
            details={"tool": context.tool_call.name},
        )
    return None

session.failures.add_rule(detect_wrong_target)
```

Use these dispositions deliberately:

- `record`: preserve the signal without changing execution.
- `continue`: record and keep going.
- `route`: invoke the Session handler for the code.
- `stop`: stop the current operation cleanly.
- `raise`: surface a typed terminal error.

`on_error` answers a different question. Set it to `closed` when a detector
failure could permit an unsafe action. Set it to `open` for optional telemetry
or quality observation where the detector itself should not halt the run.

## Add a recovery handler

Bind one of the built-ins with explicit parameters:

```python
session.failures.on(
    FailureCode.CONTRACT_UNSATISFIED,
    ForkRecovery(at=session.head, label="contract-repair"),
)
```

Available handlers are `ContinueRecovery`, `StopRecovery`, `RaiseRecovery`,
`ForkRecovery`, `CompactRecovery`, `TeacherHandoffRecovery`,
`AggregateRecovery`, and `HumanReviewRecovery`.

Callback handlers receive `(failure, session)` and may be synchronous or
asynchronous. Keep callbacks bounded with explicit `max_attempts`,
`timeout_seconds`, model lists, queues, or other parameters. Return a
`RecoveryResult` only through the built-in wrapper; do not hide a second retry
loop inside a callback.

## Choosing a code

Ask three questions:

1. Is this a configuration, boundary, action, state, resource, or observability
   failure?
2. Is there already a code with the same remediation meaning?
3. Would a buyer use this code to write a data-collection or repair brief?

If the answer to the second question is yes, reuse the existing code. If no
code fits, document the gap before adding one. New codes must be stable,
category-prefixed, and added to both the enum and `skills/failure/vocabulary.md`.

## Future agents and models

When extending this system:

- Prefer structured action facts (`tool`, `target`, `precondition`, `state`,
  `attempt`, and `outcome`) over prose error messages.
- Record recovered failures; a successful retry is still useful training signal.
- Keep local retry/fallback ownership at the boundary that understands it.
- Route only after local recovery is exhausted unless safety requires a
  pre-action rule.
- Never infer that a raw exception is retryable. Use the existing policy and
  idempotency checks.
- Preserve fail-open/fail-closed intent separately for a matched failure and a
  detector/recovery implementation error.
- Keep failure records credential-free and bounded.
- Treat failure-code changes as data-contract changes: update tests, docs, and
  downstream aggregation together.
- For a new recovery mode, add its own file under
  `vidbyte/sessions/failure/recovery/` (one category per file, e.g.
  `teacher_handoff_recovery.py`), back its constructor inputs with a
  dataclass in `vidbyte/lib/dataclasses/failure_recovery.py`, and define its
  handler-error posture explicitly rather than inheriting a default silently.
