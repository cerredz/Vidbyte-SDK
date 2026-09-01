---
name: failure
description: >-
  Explains Vidbyte's fixed deterministic failure vocabulary, Session-owned
  routing, built-in recovery ownership, @rule authoring, and fail-open/fail-closed
  behavior. Use this guide before adding a failure code, detector, or recovery.
---

# Failure Skill Guide

Vidbyte failures have one shared language and several local owners.

The shared language is `FailureCode` in
`vidbyte.sessions.failure.types`. A failure record says what happened, where it
happened, whether a local mechanism recovered it, and what Session-level action
is allowed. It does not use raw exception text as its identity.

The local owner is the mechanism closest to the boundary:

- `ToolSettings` enforces tool permissions and budgets.
- `ToolErrorPolicy` retries eligible tool errors.
- `ModelRetryMiddleware` retries model calls.
- `AgentFallback` switches provider/model after provider failures.
- Output contracts repair schema conformance inside the agent loop.
- Runtime settings stop work at iteration, token, tool-call, or timeout limits.
- Usage and tracing remain observability mechanisms.

`Session.failures` observes those outcomes and records them. It invokes a
Session recovery handler only after local recovery is exhausted, unless a
developer rule explicitly asks to route immediately.

```python
from vidbyte import Failure, FailureCode, Session, StopRecovery, rule

session = Session(agent)

@rule(
    code=FailureCode.ACTION_POLICY_VIOLATION,
    on="before_tool_call",
    on_match="stop",
    on_error="closed",
)
def forbid_production_delete(context):
    if context.tool_call and context.tool_call.name == "delete_production":
        return Failure(code=FailureCode.ACTION_POLICY_VIOLATION, source="policy", phase="action")
    return None

session.failures.add_rule(forbid_production_delete)
session.failures.on(FailureCode.TOOL_TIMEOUT, StopRecovery(reason="tool timeout"))
```

The default policy is intentionally conservative:

1. Record every deterministic failure, including failures that were recovered.
2. Do not repeat a built-in retry or fallback at the Session layer.
3. Route an exhausted failure to a registered Session handler.
4. Record the recovery result and continue, stop, or raise according to that
   handler's disposition.

Failure history is currently in-memory and bounded. It is not part of the
   checkpoint schema yet. A future export design may add it as a versioned
   trajectory artifact.
