---
name: failure
description: >-
  Explains Vidbyte's fixed deterministic failure vocabulary, Session-owned
  routing, built-in recovery ownership, @rule authoring, and fail-open/fail-closed
  behavior. Use this guide before adding a failure code, detector, or recovery.
---

# Failure Skill Guide

Ordinary `try`/`except` scatters the story of what went wrong across whatever
string a raise site happened to write down. One tool returns
`"permission_denied"`, another returns `"PermissionError"`, a third just
returns `None`, and a caller trying to build a retry, a dashboard, or a
training signal on top of that has to reverse-engineer intent from prose. The
Session failure system exists to close that gap: every deterministic failure
the SDK can produce is reduced, before it ever reaches a Session, to one of a
fixed, versioned set of `FailureCode` values with a known phase, status, and
disposition. That is what makes it possible to write a rule once
(`on_match="stop"` for a policy violation) and trust it fires for every future
tool, provider, or runtime that raises the same *kind* of failure, not just
the ones a developer happened to test against.

Vidbyte failures have one shared language and several local owners.

The shared language is `FailureCode` in
`vidbyte.lib.enums.failure`. A failure record says what happened, where it
happened, whether a local mechanism recovered it, and what Session-level action
is allowed. It does not use raw exception text as its identity.

The local owner is the mechanism closest to the boundary, because it has the
context to fix the problem cheaply and immediately; only after it has
genuinely exhausted its own options does escalation make sense:

- `ToolSettings` enforces tool permissions and budgets.
- `ToolErrorPolicy` retries eligible tool errors.
- `ModelRetryMiddleware` retries model calls.
- `AgentFallback` switches provider/model after provider failures.
- Output contracts repair schema conformance inside the agent loop.
- Runtime settings stop work at iteration, token, tool-call, or timeout limits.
- Usage and tracing remain observability mechanisms.

`Session.failures` sits above all of that. It does not compete with any local
mechanism's retry loop; it only observes the *outcome* those mechanisms
publish (via reply metadata or a caught exception), records it as a canonical
`Failure`, and invokes a Session recovery handler only after local recovery is
exhausted — unless a developer rule explicitly asks to route immediately,
which is the escape hatch for failures no local mechanism can safely
interpret on its own, such as "this tool call looks like it targets the wrong
environment."

```python
from vidbyte import (
    Failure,
    FailureCode,
    FailureDisposition,
    MiddlewareHook,
    RuleErrorMode,
    Session,
    StopRecovery,
    rule,
)

session = Session(agent)

@rule(
    code=FailureCode.ACTION_POLICY_VIOLATION,
    on=MiddlewareHook.BEFORE_TOOL_CALL,
    on_match=FailureDisposition.STOP,
    on_error=RuleErrorMode.CLOSED,
)
def forbid_production_delete(context):
    if context.tool_call and context.tool_call.name == "delete_production":
        return Failure(code=FailureCode.ACTION_POLICY_VIOLATION, source="policy", phase="action")
    return None

session.failures.add_rule(forbid_production_delete)
session.failures.on(FailureCode.TOOL_TIMEOUT, StopRecovery(reason="tool timeout"))
```

The default policy is intentionally conservative, and each step exists to
prevent a specific failure mode of a naive failure system:

1. Record every deterministic failure, including failures that were
   recovered — a retry that succeeded on attempt three is still useful
   training signal about where the SDK's assumptions were wrong.
2. Do not repeat a built-in retry or fallback at the Session layer — two
   independent retry loops racing the same operation is a bug, not
   redundancy.
3. Route an exhausted failure to a registered Session handler, so "nobody
   handled this" is never a silent, undetectable state.
4. Record the recovery result and continue, stop, or raise according to that
   handler's disposition, so the Session's own control flow stays as
   explicit and typed as everything else in the SDK.

Failure history is currently in-memory and bounded. It is not part of the
   checkpoint schema yet. A future export design may add it as a versioned
   trajectory artifact.
