# Design Doc: Session Failure Vocabulary and Deterministic Failure Router

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-01
**Last Updated:** 2026-09-01

---

## 1. Overview

Add a central, Session-owned failure vocabulary and router at
`vidbyte/sessions/failure/`. The router gives every deterministic failure a
stable `FailureCode`, records the observed outcome and local handler, evaluates
developer rules declared with `@rule`, and invokes higher-level recovery only
after the SDK's existing retry, fallback, validation, budget, and middleware
mechanisms have been exhausted. The implementation also adds the initial
recovery package and repository-level `skills/failure/` guidance so future
agents extend one taxonomy instead of introducing raw error strings or a
second policy engine.

---

## 2. Goals & Non-Goals

### Goals

- Create a fixed, categorized deterministic failure vocabulary covering Session,
  configuration, input/output contracts, model/provider, tool/action, runtime,
  workflow, data/state, resource, and observability failures.
- Expose a typed `Failure` record that keeps stable machine-readable identity
  separate from optional human/debug details.
- Expose `Session.failures` as the public Session failure router.
- Record failures from completed replies, stop reasons, middleware events, and
  caught SDK exceptions without changing the existing local recovery behavior.
- Preserve existing retry, model fallback, tool policy, output-contract, budget,
  and fail-open/fail-closed implementations as the owners of immediate control.
- Route only exhausted or explicitly escalated failures to Session recovery by
  default, preventing duplicate retries and fallback loops.
- Add an explicit `@rule` decorator with lifecycle hook, match disposition,
  priority, and rule-error posture.
- Provide reusable recovery objects for continue, stop, raise, fork, compact,
  teacher handoff, model aggregation, and human-review workflows.
- Add focused unit/integration tests and an executable verification script.
- Add top-level `skills/failure/` documentation for the vocabulary, design
  philosophy, current features, authoring process, and extension guidance.

### Non-Goals

- Do not replace `ToolSettings`, `ToolErrorPolicy`, `ModelRetryMiddleware`,
  `AgentFallback`, output contracts, usage accounting, or middleware policy.
- Do not introduce one exception subclass per failure code.
- Do not make raw exception text the taxonomy or failure identity.
- Do not implement probabilistic/LLM-judge failures in this change.
- Do not change the unrelated `vidbyte-harnesses` repository.
- Do not persist a second failure database or change the Session checkpoint
  schema in this release.
- Do not automatically run expensive cross-run recovery for every recorded
  failure.

---

## 3. Background & Context

The SDK already has mature local failure controls. `AgentMiddleware` exposes
runtime lifecycle hooks and a `fail_closed` policy; `MiddlewarePipeline` turns
middleware exceptions into abort-or-continue decisions. `ToolSettings` owns
deterministic tool denials and budgets, `ToolErrorPolicy` owns bounded tool
retries, `ModelRetryMiddleware` retries model calls, and `AgentFallback` owns
provider/model switching. Output contracts repair schema failures inside the
loop, while `AgentStopReason` and runtime metadata expose budget and terminal
states. Session persistence deliberately fails open by default.

Those components currently produce useful but separate names and metadata. A
buyer or future training system cannot reliably group a provider response
failure, exhausted fallback, malformed tool arguments, and an unsafe action
without a shared vocabulary. A Session is the correct aggregation boundary
because it already owns checkpoints, forks, resumption, and the agent binding
seam. It can observe local outcomes while keeping local enforcement in place.

The design therefore separates detection, local handling, recording, and
escalation. A failure handled by a built-in mechanism is still recorded as
learning signal, but Session recovery runs only for an exhausted or explicitly
routed failure. Fail-open versus fail-closed is represented independently for a
matched rule and for errors thrown by the rule or recovery handler.

---

## 4. Requirements

### Functional Requirements

1. `FailureCode` must be a finite, versionable string enum with deterministic
   codes grouped by category.
2. Every `Failure` must carry a code, phase, status, disposition, source, and
   safe structured details; raw error text must be optional and non-identity.
3. `FailureRouter` must support `record`, `emit`, `history`, `add_rule`,
   `remove_rule`, `on`, and `evaluate` operations.
4. `Session` must expose a lazily stable `failures` property initialized with
   the Session and available after construction and resume.
5. Session reply recording must normalize `AgentStopReason`, contract metadata,
   middleware events, fallback metadata, tool-call states, usage integrity, and
   Session persistence markers into canonical failures.
6. Session exception capture must map known SDK exception families to canonical
   failure codes while preserving exception chaining at the runtime boundary for
   optional re-raising.
7. Existing local retry/fallback/validation/budget decisions remain the first
   recovery owner; Session routes only after exhaustion unless a rule explicitly
   requests immediate routing.
8. `@rule` must attach metadata without global import-time registration; rules
   must be explicitly added to a Session router.
9. Rules must support synchronous and asynchronous callables returning
   `Failure | None` and must honor `on_match`, `on_error`, and `priority`.
10. A fail-closed rule error must produce a terminal failure and stop/raise
    according to the configured disposition; a fail-open rule error must be
    recorded and execution must continue.
11. Recovery handlers must be classes in `sessions/failure/recovery/`, accept
    explicit parameters, and expose bounded results rather than silently
    mutating state.
12. Built-in recovery handlers must support continue, stop, raise, fork,
    compaction callback, teacher handoff callback, model aggregation callback,
    and human-review callback workflows.
13. Recovery handler errors must follow an explicit `on_error` posture and must
    never recursively invoke the same failed handler.
14. The public Session and top-level `vidbyte` import surfaces must re-export
    the stable failure types, decorator, router, and recovery classes.
15. All new public behavior must have unit/integration coverage and an
    executable script that reports PASS/FAIL for every design-doc test case.

### Non-Functional Requirements

- No new runtime dependency.
- Failure recording must be in-memory, bounded by an optional `max_history`,
  and must not add a network or model call.
- Details must be JSON-safe where possible and must not contain credentials.
- Recording a failure must not turn an existing fail-open persistence,
  tracing, or usage error into a run-ending exception.
- Rule ordering must be deterministic by descending priority and registration
  order for ties.
- Existing public APIs and checkpoint serialization remain backward compatible.
- Public classes and methods follow the SDK's class-bound helper and typed
  dataclass conventions.

---

## 5. High-Level Design

Create `vidbyte.sessions.failure` as a small package with typed contracts,
decorated rules, a Session-bound router, and a `recovery/` subpackage. The
router records normalized events in memory and exposes explicit route handlers.
It is attached by `Session` and is also available to code that receives a
Session from the existing agent binding seam.

Existing mechanisms remain boundary owners. The router reads their structured
metadata at `record_turn`, observes middleware hooks through a Session-bound
middleware bridge, and captures exceptions at Session/agent boundaries. It
records both intermediate handled failures and terminal/exhausted failures.
Only records with `status=exhausted` or an explicit `route` disposition invoke
Session recovery by default.

```text
[model/tool/runtime boundary]
          |
          v
[existing retry, fallback, policy, contract, budget mechanism]
          |
          +--> [FailureRouter records observed/handled/recovered]
          |
          +--> [exhausted or explicit route]
                         |
                         v
                [Session recovery handler]
                  fork / compact / distill /
                  aggregate / review / stop
```

The first implementation uses adapters over existing metadata rather than
rewriting every built-in. Future built-ins can emit directly through the same
router sink when a precise mid-operation event is required.

---

## 6. Detailed Design

### 6.1 Failure contracts and vocabulary

**File(s):** `vidbyte/sessions/failure/types.py`
**Type:** New file

#### What it does

Defines the fixed deterministic vocabulary and immutable records used by all
failure producers and recovery consumers.

The initial categories and codes are:

- Configuration: `configuration.invalid`, `configuration.missing_required`,
  `configuration.unsupported_combination`, `configuration.unknown_model`,
  `configuration.invalid_schema`, `configuration.invalid_provider`,
  `configuration.invalid_tool`, `configuration.invalid_middleware`,
  `configuration.invalid_runtime`, `configuration.invalid_argument`.
- Input/output: `input.empty`, `input.invalid`, `input.type_invalid`,
  `output.missing`, `output.invalid`, `output.schema_violation`,
  `contract.unsatisfied`, `serialization.invalid`.
- Model/provider: `model.request_failed`, `model.response_invalid`,
  `model.timeout`, `model.rate_limited`, `model.authentication_failed`,
  `model.not_found`, `model.unsupported`, `model.context_limit`,
  `model.content_filtered`, `model.retry_exhausted`,
  `model.fallback_exhausted`, `provider.selection_failed`,
  `provider.configuration_invalid`.
- Tool/action: `tool.not_found`, `tool.arguments_invalid`,
  `tool.permission_denied`, `tool.disabled`, `tool.timeout`,
  `tool.rate_limited`, `tool.execution_failed`, `tool.result_invalid`,
  `tool.result_missing`, `tool.retry_exhausted`, `tool.call_limit_reached`,
  `tool.calls_per_iteration_limit`, `tool.identical_call_limit`,
  `tool.consecutive_failure_limit`, `tool.error_limit`,
  `tool.sliding_window_limit`, `tool.loop_limit`, `action.policy_violation`,
  `action.unsafe`, `action.forbidden`, `action.invalid_arguments`,
  `action.wrong_target`, `action.out_of_order`, `action.duplicate`,
  `action.precondition_failed`, `action.no_progress`, `action.looping`,
  `action.partial`, `action.not_applied`, `action.conflict`,
  `action.idempotency_violation`, `action.unexpected_side_effect`.
- Runtime/resource: `runtime.max_iterations`, `runtime.max_tokens`,
  `runtime.max_tool_calls`, `runtime.timeout`, `runtime.middleware_abort`,
  `runtime.middleware_error`, `runtime.error`, `runtime.cancelled`,
  `runtime.context_build_failed`, `runtime.compaction_failed`,
  `runtime.queue_limit`, `resource.exhausted`.
- Session/state/data: `session.not_found`, `session.checkpoint_missing`,
  `session.serialization_failed`, `session.version_mismatch`,
  `session.persistence_failed`, `session.resume_failed`, `session.fork_failed`,
  `session.rewind_invalid`, `session.scope_denied`, `state.corrupted`,
  `state.conflict`, `data.not_found`, `data.malformed`, `data.incomplete`,
  `data.stale`, `data.conflict`, `data.source_unavailable`,
  `data.permission_denied`.
- Workflow/team: `workflow.definition_invalid`, `workflow.validation_failed`,
  `workflow.stage_failed`, `workflow.routing_failed`,
  `workflow.transition_limit`, `agent.handoff_failed`,
  `agent.transfer_failed`, `team.task_blocked`, `team.replan_limit`,
  `team.unrecoverable`.
- Observability: `usage.recording_corrupted`, `trace.capture_failed`,
  `trace.export_failed`, `recovery.handler_failed`, `rule.evaluation_failed`.

The exact enum values are part of the public contract. New codes require a
design update and documentation entry; callers should group by the category
prefix when they need forward-compatible reporting.

#### Interface / API

```python
class FailureCode(str, Enum): ...
class FailurePhase(str, Enum): ...
class FailureStatus(str, Enum): ...
class FailureDisposition(str, Enum): ...
class RuleErrorMode(str, Enum): ...
class FailureSeverity(str, Enum): ...

@dataclass(frozen=True, slots=True)
class Failure: ...

@dataclass(frozen=True, slots=True)
class RecoveryAttempt: ...
```

`Failure.from_exception(exc, ...)` maps known SDK exception families and keeps
only safe exception type/details. `Failure.as_dict()` converts enum fields to
strings and returns a JSON-safe mapping.

#### Logic / Algorithm

1. Validate and coerce enum inputs in `__post_init__`.
2. Require a non-empty `source` and canonical `FailureCode`.
3. Copy details into an immutable mapping-compatible representation while
   dropping credential-looking keys.
4. Map exception class/module and known metadata keys to a code.
5. Preserve optional `parent_id`, `iteration`, and `step` for trajectory joins.

#### Edge Cases & Error Handling

- Unknown exceptions map to `runtime.error`; they never become a new dynamic
  code.
- Empty details are valid.
- Non-JSON detail values are stringified safely and bounded.
- A failure record cannot itself raise because a caller supplied a malformed
  detail value.

### 6.2 Decorated developer rules

**File(s):** `vidbyte/sessions/failure/rules.py`
**Type:** New file

#### What it does

Defines `@rule` and the immutable `FailureRule` descriptor. The decorator only
attaches metadata to a callable; `FailureRouter.add_rule()` performs scoped
registration and validation.

#### Interface / API

```python
@rule(code=FailureCode.ACTION_POLICY_VIOLATION, on="before_tool_call", on_match="stop", on_error="closed", priority=100)
def rule_function(context: object) -> Failure | None: ...

class FailureRule: ...
```

The callable may be synchronous or asynchronous and must return `Failure | None`.
`on_match` is `record`, `continue`, `route`, `stop`, or `raise`. `on_error` is
`open` or `closed`. Rules are ordered by descending priority, then registration
order.

#### Logic / Algorithm

1. Validate decorator arguments immediately.
2. Attach a private descriptor to the callable without executing it.
3. Convert the descriptor into a `FailureRule` during explicit registration.
4. During evaluation, await awaitables, normalize a returned failure, and apply
   the configured disposition.
5. On a rule exception, record `rule.evaluation_failed`; continue for open
   mode, or stop/raise for closed mode.

#### Edge Cases & Error Handling

- A non-callable registration raises `TypeError`.
- A rule returning an arbitrary object raises a deterministic rule error and
  follows `on_error`.
- Duplicate function registration is ignored by identity.
- Rules that match before a tool call can block it; after-run rules cannot
  retroactively block an action.

### 6.3 Session failure router

**File(s):** `vidbyte/sessions/failure/router.py`
**Type:** New file

#### What it does

Owns Session-scoped failure history, rule registration, code-to-recovery
bindings, normalization of existing SDK metadata, and escalation. It is not a
second retry loop.

#### Interface / API

```python
class FailureRouter:
    def __init__(self, session: object, *, max_history: int = 512, enabled: bool = True) -> None: ...
    def record(self, failure: Failure) -> Failure: ...
    def emit(self, code: FailureCode, *, phase: FailurePhase, source: str, status: FailureStatus = FailureStatus.OBSERVED, disposition: FailureDisposition = FailureDisposition.RECORD, details: Mapping[str, Any] | None = None) -> Failure: ...
    def history(self, *, code: FailureCode | None = None, status: FailureStatus | None = None) -> tuple[Failure, ...]: ...
    def add_rule(self, rule: Callable[..., Any] | FailureRule) -> FailureRule: ...
    def remove_rule(self, rule: Callable[..., Any] | FailureRule) -> None: ...
    def on(self, code: FailureCode, recovery: RecoveryHandler, *, include_recovered: bool = False) -> None: ...
    async def evaluate(self, hook: str, context: object) -> tuple[Failure, ...]: ...
    def capture_reply(self, reply: object) -> tuple[Failure, ...]: ...
    def capture_exception(self, exc: BaseException, *, phase: FailurePhase = FailurePhase.RUNTIME, source: str = "session") -> Failure: ...
```

#### Logic / Algorithm

1. Record a bounded immutable history entry.
2. Normalize deterministic metadata into codes using a class-bound normalizer.
3. Mark local handling in `handled_by` and preserve intermediate attempts.
4. Route only exhausted or explicitly routed entries unless the binding opts
   into recovered failures.
5. Invoke the selected recovery object once per failure id.
6. Record a `RecoveryAttempt` with outcome and error posture.

#### Edge Cases & Error Handling

- `max_history=0` is rejected; the oldest records are evicted at the bound.
- Disabled routers still accept no-op `record` calls but do not evaluate rules or
  recovery.
- A broken recovery handler records `recovery.handler_failed` and applies its
  configured `on_error` mode.
- If Session persistence is already failing, the failure remains in memory and
  is attached to reply metadata when mutable; the router never recursively writes
  to the same failing store.

### 6.4 Recovery package

**File(s):** `vidbyte/sessions/failure/recovery/base.py`,
`vidbyte/sessions/failure/recovery/builtins.py`,
`vidbyte/sessions/failure/recovery/__init__.py`
**Type:** New files

#### What it does

Provides class-based, parameterized recovery handlers. `RecoveryHandler` is a
small protocol/base contract; built-ins are explicit and composable.

#### Interface / API

```python
class RecoveryHandler(Protocol):
    name: str
    on_error: RuleErrorMode
    def recover(self, failure: Failure, *, session: object) -> RecoveryResult: ...

class ContinueRecovery: ...
class StopRecovery: ...
class RaiseRecovery: ...
class ForkRecovery: ...
class CompactRecovery: ...
class TeacherHandoffRecovery: ...
class AggregateRecovery: ...
class HumanReviewRecovery: ...
```

Parameters are explicit: `at`, `tools`, `middleware`, `policy`, `trace`,
`label`, `compact`, `teacher`, `aggregator`, `reviewer`, `max_attempts`,
`timeout_seconds`, `on_error`, and `metadata` as applicable. Fork and callback
handlers return a `RecoveryResult` containing the produced object or callback
result; they do not hide side effects.

#### Logic / Algorithm

1. Validate handler parameters at construction.
2. Verify the Session exposes the required operation before running.
3. Invoke the operation once with the failure context.
4. Return a bounded success/failure result.
5. Let the router decide whether to continue, stop, or raise based on the
   result and configured disposition.

#### Edge Cases & Error Handling

- Fork without a checkpoint returns a failed result with
  `session.fork_failed` rather than a raw traceback.
- Callback recovery requires a callable and rejects absent callbacks.
- Compact/handoff/aggregate callbacks may be async; the router's async route
  method awaits them.
- `RaiseRecovery` raises the typed `FailureRaisedError`; the owning Session
  boundary preserves and re-raises the original exception after open recovery.

### 6.5 Session integration

**File(s):** `vidbyte/sessions/session.py`, `vidbyte/sessions/__init__.py`,
`vidbyte/__init__.py`, `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Creates and exposes `Session.failures`, captures reply metadata and exceptions,
and preserves existing persistence semantics. `BaseAgent.generate_reply()` will
notify the bound router when an SDK execution exception is about to be wrapped,
so direct `agent.arun()` calls receive the same failure signal as
`session.arun()` calls.

#### Logic / Algorithm

1. Construct the router before initial Session metadata is written.
2. Bind the Session to the agent using the existing seam.
3. Capture normalized reply failures after runtime metadata exists.
4. Capture known exceptions before `AgentExecutionError` wrapping.
5. Keep persistence fail-open; annotate a mutable reply and in-memory history
   when storage fails.
6. Re-export public contracts from `vidbyte.sessions` and `vidbyte`.

#### Edge Cases & Error Handling

- Multi-agent facades that reject durable Session binding remain unchanged.
- Existing Session resume/fork behavior carries an empty new router unless
  failures are explicitly exported in a future schema version.
- The Session router is not serialized in checkpoints.

### 6.6 Repository failure skill documentation

**File(s):** `skills/failure/README.md`, `skills/failure/vocabulary.md`,
`skills/failure/authoring.md`
**Type:** New files

#### What it does

Documents the fixed vocabulary, local-owner/Session-router philosophy, current
features and integrations, rule decorator usage, fail-open/fail-closed choices,
recovery parameters, and future guidance for agents/models.

---

## 7. Data Model Changes

### 7.1 In-memory Failure and Recovery records

**Change type:** New

```python
Failure(
    id: str,
    code: FailureCode,
    phase: FailurePhase,
    source: str,
    status: FailureStatus,
    disposition: FailureDisposition,
    severity: FailureSeverity,
    summary: str | None,
    details: Mapping[str, Any],
    handled_by: str | None,
    parent_id: str | None,
    iteration: int | None,
    step: str | None,
)
```

No checkpoint schema migration is made. Failure history is runtime-local until
a later explicitly versioned Session export design.

---

## 8. API Changes

### 8.1 `Session.failures`

**Change type:** New

```python
session.failures.record(failure)
session.failures.add_rule(rule_function)
session.failures.on(FailureCode.TOOL_TIMEOUT, ForkRecovery(...))
session.failures.history(status=FailureStatus.EXHAUSTED)
```

### 8.2 `vidbyte.sessions.failure` exports

**Change type:** New

The package exports `Failure`, `FailureCode`, `FailurePhase`, `FailureStatus`,
`FailureDisposition`, `FailureSeverity`, `RuleErrorMode`, `FailureRule`,
`FailureRouter`, `rule`, `RecoveryResult`, and all initial recovery handlers.

### 8.3 Errors

**Change type:** New internal typed error

`FailureRaisedError` is used only by `RaiseRecovery` when there is no original
exception. It does not replace existing SDK exceptions.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/session-failure-vocabulary.md` | Source-of-truth architecture and test plan |
| CREATE | `vidbyte/sessions/failure/__init__.py` | Public failure package exports |
| CREATE | `vidbyte/sessions/failure/types.py` | Fixed vocabulary and typed records |
| CREATE | `vidbyte/sessions/failure/rules.py` | `@rule` decorator and descriptors |
| CREATE | `vidbyte/sessions/failure/router.py` | Session-scoped ledger, normalization, and routing |
| CREATE | `vidbyte/sessions/failure/recovery/__init__.py` | Recovery exports |
| CREATE | `vidbyte/sessions/failure/recovery/base.py` | Recovery contracts and results |
| CREATE | `vidbyte/sessions/failure/recovery/builtins.py` | Initial parameterized recovery handlers |
| MODIFY | `vidbyte/sessions/session.py` | Construct and expose router; capture reply/exception outcomes |
| MODIFY | `vidbyte/sessions/__init__.py` | Re-export failure API |
| MODIFY | `vidbyte/__init__.py` | Re-export top-level failure API |
| MODIFY | `vidbyte/agents/base.py` | Capture bound-session exceptions before wrapping |
| CREATE | `skills/failure/README.md` | Entry-point design and usage guide |
| CREATE | `skills/failure/vocabulary.md` | Full deterministic code catalogue |
| CREATE | `skills/failure/authoring.md` | Rule/recovery extension guidance |
| CREATE | `tests/test_session_failures.py` | Unit and integration coverage |
| CREATE | `scripts/test-session-failure-vocabulary.py` | Executable all-case verification script |

No files are deleted.

---

## 10. Testing Plan

### Unit Tests

- [Edge Case] Every `FailureCode` has a category prefix and stable string value.
- [Edge Case] `Failure` accepts empty details and optional parent/iteration data.
- [Hidden Failure] Credential-looking detail keys are removed or bounded.
- [Silent Failure] `Failure.as_dict()` emits enum values as strings, not enum reprs.
- [Hidden Assumption] Unknown exception types map to `runtime.error`.
- [Edge Case] `FailureRouter(max_history=1)` evicts exactly the oldest record.
- [Hidden Failure] A malformed detail object cannot make `record()` raise.
- [Silent Failure] History filtering by code and status returns the correct
  subset in insertion order.
- [Hidden Assumption] Disabled routers do not evaluate rules or recoveries.
- [Edge Case] `@rule` rejects non-callables and invalid option strings.
- [Hidden Failure] A synchronous rule and an asynchronous rule both evaluate.
- [Silent Failure] Rule priority ordering is descending and tie ordering is
  registration order.
- [Hidden Assumption] A rule returning a non-`Failure` object follows its error
  mode rather than being silently treated as success.
- [Hidden Failure] Fail-open rule exceptions record `rule.evaluation_failed`
  and continue.
- [Hidden Failure] Fail-closed rule exceptions produce a terminal failure.
- [Edge Case] Duplicate rule registration does not run a rule twice.
- [Hidden Failure] Recovery handler exceptions record
  `recovery.handler_failed` without recursive invocation.
- [Silent Failure] `ContinueRecovery` returns a continue disposition.
- [Silent Failure] `StopRecovery` returns the configured reason and metadata.
- [Hidden Assumption] `RaiseRecovery` without an original exception raises the
  typed fallback error.
- [Edge Case] Fork recovery with no Session head returns a structured failure.
- [Hidden Assumption] Callback recovery rejects a non-callable callback.
- [Hidden Failure] Async callback recovery is awaited and its result preserved.
- [Silent Failure] Recovery parameters (`at`, `label`, `metadata`, and
  `on_error`) are passed unchanged.

### Integration Tests

- [Hidden Assumption] A new Session exposes `session.failures` and a stable
  router identity.
- [Silent Failure] A normal final reply produces no false failure.
- [Silent Failure] Runtime `stop_reason=max_tokens` maps to
  `runtime.max_tokens`.
- [Silent Failure] Runtime tool-budget stop reasons map to their distinct tool
  codes rather than one generic code.
- [Hidden Failure] Middleware abort and middleware exception metadata map to
  different canonical codes.
- [Hidden Failure] Existing fallback metadata records provider failure and
  fallback outcome without invoking Session recovery after success.
- [Hidden Failure] An exhausted fallback is routed once to the Session handler.
- [Hidden Failure] A schema violation is recorded after the failed turn remains
  checkpointable.
- [Hidden Failure] A fail-open Session persistence error remains non-terminal
  and is recorded in memory/reply metadata.
- [Hidden Assumption] Direct bound `agent.arun()` exception capture reaches the
  same Session router as `session.arun()`.
- [Hidden Failure] `Session.resume()` creates a functioning empty router and
  preserves existing checkpoint behavior.
- [Silent Failure] Public imports from `vidbyte` and `vidbyte.sessions` resolve
  every documented failure symbol.

### Manual / QA Test Cases

1. Given a Session with a `before_tool_call` fail-closed rule, when the rule
   matches, then the tool is blocked before execution and the failure contains
   the canonical action code.
2. Given a tool timeout with local retries configured, when the first attempt
   fails and the second succeeds, then the history contains the recovered
   failure and Session recovery does not run.
3. Given an exhausted tool retry, when the route is configured with
   `ForkRecovery(at=...)`, then exactly one child Session is returned.
4. Given a trace exporter failure, when the trace is optional, then the run
   continues and the failure is marked fail-open.
5. Given a safety rule whose evaluator crashes, when `on_error="closed"`, then
   the action is stopped and a terminal rule-evaluation failure is visible.

### Executable verification

`python scripts/test-session-failure-vocabulary.py` runs every case above that
can be exercised without a live model/provider, prints `PASS` or `FAIL` per
case, prints a final `X/Y tests passed` summary, and exits non-zero on failure.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python | `>=3.11` | Dataclasses, enums, async inspection | None beyond existing runtime |
| Existing Vidbyte SDK classes | Current `main` | Session, runtime metadata, middleware and recovery seams | Metadata shape changes require adapter updates |

No external service or dependency is added.

---

## 12. Rollout & Deployment

- No feature flag is required; constructing a Session enables recording with a
  bounded in-memory router.
- Existing behavior remains unchanged unless a developer registers a rule or
  recovery handler.
- The first release records known outcomes but routes only exhausted failures.
- Rollback is a normal package rollback or removal of the Session integration;
  no data migration is required.
- If a downstream caller cannot import the new symbols, remove only the new
  re-export lines while retaining the package internals for a follow-up fix.

---

## 13. Open Questions

- [ ] Should failure history become part of a future versioned Session export
  bundle, or remain an external trajectory artifact?
- [ ] Which semantic/action failure codes should be promoted from developer
  rules into SDK detectors after real harness data is collected?
- [ ] Should a future `SessionFailureMiddleware` be automatically attached for
  all linear agents, or only when rules are registered?
- [ ] Should custom code namespaces be allowed, or should unmatched custom
  rules always use a canonical policy-violation parent code?

---

## 14. Alternatives Considered

### Alternative 1: Replace all existing failure mechanisms with Session recovery

- What: Move retry, fallback, schema correction, and limits into one Session
  policy engine.
- Why rejected: It duplicates mature boundary logic, breaks direct Agent usage,
  and creates unclear ownership for immediate enforcement.

### Alternative 2: Keep independent raw errors and only document them

- What: Add a documentation catalogue without a typed runtime abstraction.
- Why rejected: Future agents cannot reliably aggregate or route failures, and
  raw exception text remains the de facto vocabulary.

### Alternative 3: Define one Python exception class per failure code

- What: Use `Failure1Error`, `Failure2Error`, and so on as the public API.
- Why rejected: Exception inheritance is a poor fit for recovered/intermediate
  events, creates a large brittle class surface, and loses lifecycle metadata.

### Alternative 4: Register decorated rules globally at import time

- What: The decorator immediately adds rules to a process-wide registry.
- Why rejected: It leaks policy across Sessions and tests, makes imports mutate
  runtime behavior, and is unsafe for concurrent runs.

### Alternative 5: Persist every failure as a new checkpoint

- What: Add one durable checkpoint for every intermediate failure.
- Why rejected: It changes checkpoint semantics and storage cost. Failure history
  can be made durable later through an explicit schema/version design.
