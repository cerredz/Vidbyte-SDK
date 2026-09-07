# Design Doc: Codex Turn-Boundary Middleware

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-07
**Last Updated:** 2026-09-07

---

## 1. Overview

`AgentMiddleware` defines nine lifecycle hooks and `CodexHarnessAgent` runs none of them, so every Vidbyte guardrail, budget check, and audit middleware is inert against a Codex agent. This change wires the three hooks that sit at a boundary Vidbyte actually owns — `before_run`, `after_run`, and `on_model_error` — by reusing the existing `MiddlewarePipeline`. Equally important, it **rejects** the other six at construction time with a message naming the hook, because they sit inside a loop Codex owns and no honest enforcement point exists for them. A `before_tool_call` policy declared `fail_closed=True` that silently never runs is worse than one that refuses to load.

---

## 2. Goals & Non-Goals

### Goals

- Accept a `middleware` tuple on `CodexHarnessAgentSettings` and run its `before_run`, `after_run`, and `on_model_error` hooks around each turn.
- Reuse `MiddlewarePipeline` for dispatch, so `fail_closed`, sleep, event recording, and hook-invocation diagnostics have exactly one implementation in the SDK.
- Reject at construction any middleware overriding one of the six inner-loop hooks, naming the hook in the error.
- Honor `ABORT_RUN` by refusing the turn before the transport is touched.
- Fail loudly, not silently, on a decision this boundary cannot represent (`DENY_TOOL`, `RETRY`) or a transform field it cannot apply.
- Publish middleware metadata and events on the returned `AgentMessage`.

### Non-Goals

- Mapping the six inner-loop hooks onto Codex's native hook system. Codex hooks are configuration-level, can fail open, and `PostToolUse` fires after the command already ran — none of that satisfies a Vidbyte pre-execution decision point. Roadmap tasks H01-H05 own that work and must start from what each native event can actually enforce.
- Applying `MiddlewareTransform.system`, `.provider_messages`, or `.model_visible_tool_result`. See §13 for why `system` in particular needs thread-lifecycle semantics settled first.
- Budget enforcement. `CostBudgetMiddleware` becomes *runnable* here, but whether the SDK ships a Codex budget preset is roadmap task B02.
- A `middleware()` accessor or mutation API. The tuple is construction-time only, matching how every other Codex setting works.

---

## 3. Background & Context

`AgentMiddleware` (`vidbyte/middleware/base.py:21`) is an ABC whose nine hooks all default to `MiddlewareDecision.continue_()`, so a subclass overrides only what it needs. `MiddlewarePipeline` (`vidbyte/middleware/pipeline.py:36`) dispatches them in order and already handles everything hard about it: it catches an exception per hook and converts it through `_exception_decision`, which aborts when `middleware.fail_closed` is true and continues with a `middleware_error_fail_open` event when it is false; it awaits `SLEEP` decisions and continues; it merges `CONTINUE` metadata and transforms in middleware order; and it records both consumer-facing `MiddlewareEvent`s and diagnostic `MiddlewareHookInvocation`s with timings.

That is the solved problem this design inherits. Reimplementing any of it inside the Codex package would create a second definition of `fail_closed` — the exact kind of drift the field guide's *Class-Bound Helpers* entry warns about.

What Codex cannot supply is the other six hooks' decision points. `before_iteration`, `before_model_call`, `after_model_response`, `before_tool_call`, `after_tool_call`, and `after_iteration` all describe positions inside a model/tool loop. `docs/design/codex-harness-agent.md` §13 rejected `AgentRuntimeType` for precisely this reason: "`AgentRuntime` assumes Vidbyte controls model/tool iterations; wrapping Codex there creates nested loops and false middleware/limit guarantees." A completed `TurnResult` reports what happened; it offers no point at which Vidbyte could have said no.

The roadmap's H-series covers the native-hook route, and its completion criteria state the boundary this design holds to: "Each supported middleware mapping is proven at its actual decision point; observational events are never described as enforcement."

---

## 4. Requirements

### Functional Requirements

1. `CodexHarnessAgentSettings` accepts `middleware: tuple[AgentMiddleware, ...]`, defaulting to empty.
2. Construction raises `ConfigurationError` — surfaced as `CodexAgentError` with `CODEX_VIDBYTE_TRANSLATION_FAILED` — when any supplied middleware overrides `before_iteration`, `before_model_call`, `after_model_response`, `before_tool_call`, `after_tool_call`, or `after_iteration`. The message names the middleware and every unsupported hook it overrode.
3. Override detection compares the subclass's function object against `AgentMiddleware`'s, so a subclass that inherits a hook untouched is accepted.
4. An agent with no middleware behaves exactly as before, with no pipeline constructed and no behavior change.
5. `before_run` runs after input and context translation and **before** the transport call.
6. `after_run` runs after the result is translated into an `AgentMessage`.
7. `on_model_error` runs when the transport raises, before the exception propagates.
8. An `ABORT_RUN` decision from `before_run` raises `CodexAgentError` with `CODEX_MIDDLEWARE_ABORTED`, carrying the decision's reason, and performs zero native calls.
9. An `ABORT_RUN` decision from `after_run` raises the same error after the turn has already run, because the turn cannot be un-run; the error names `after_run` as the operation so a caller can tell the two apart.
10. A `DENY_TOOL` or `RETRY` decision raises `CodexAgentError` with `CODEX_MIDDLEWARE_UNSUPPORTED`, because no tool boundary and no retry loop exists here and silently ignoring the request would misrepresent the policy as satisfied.
11. A `CONTINUE` decision whose transform sets `system`, `provider_messages`, or `model_visible_tool_result` raises `CODEX_MIDDLEWARE_UNSUPPORTED`, naming the field. Transform `metadata` is applied.
12. `MiddlewareContext.hook`, `agent_name`, `message`, and `elapsed_seconds` are populated; fields describing an inner loop (`iteration_count`, `tool_call`, `model_response`) stay at their defaults, which honestly signals "not observable here."
13. The reply's metadata carries the pipeline's merged middleware metadata and its recorded events.
14. `on_model_error` never replaces the original exception. Its own decisions are recorded, but the transport's exception is what propagates.

### Non-Functional Requirements

- **Performance:** three hook dispatches per turn against a tuple that is usually empty. Immeasurable against a Codex turn.
- **Scalability:** the pipeline is constructed once per agent, and its event lists are bounded by hooks-per-turn. A long-lived agent's event list does grow; §13 records that as an open question rather than pretending it is solved.
- **Security:** middleware is caller-supplied code the caller already trusts. This change adds no new execution surface — it runs code the caller explicitly attached.
- **Observability:** `MiddlewareHookInvocation` timings and `MiddlewareEvent` records reach the caller through the reply metadata.
- **Reliability:** `fail_closed=True` middleware that raises aborts the turn; `fail_closed=False` continues with an event. Both behaviors come from `MiddlewarePipeline` unchanged.

---

## 5. High-Level Design

Two pieces, plus a settings field.

`CodexMiddlewareValidator` runs at construction, inside `CodexVidbyteTranslator.translate_agent`, which is already the place every shared Vidbyte abstraction is resolved before a Codex process can start. It walks each middleware's class, compares every unsupported hook's function object against `AgentMiddleware`'s default, and raises on the first middleware that overrode any of them. Doing this at construction rather than at the first turn is the whole point: a policy that cannot be enforced should fail when it is declared, not silently during the run it was meant to govern.

`CodexMiddlewareRunner` runs at each turn boundary. It builds a `MiddlewareContext`, delegates dispatch to a `MiddlewarePipeline`, and interprets the returned `MiddlewareDecision` for a boundary that has no tool call and no retry loop. It owns no dispatch logic, no `fail_closed` handling, and no event recording — all of that is `MiddlewarePipeline`'s, reused as-is.

The decision interpretation is where the honesty lives. `CONTINUE` proceeds. `SLEEP` never reaches the runner, because the pipeline awaits it internally and continues. `ABORT_RUN` becomes a classified `CodexAgentError`. `DENY_TOOL` and `RETRY` also become classified errors — not because they are invalid decisions, but because they are valid decisions this boundary cannot carry out, and a caller who returns `RETRY` is entitled to find out that nothing retried rather than to believe it did.

```
CodexHarnessAgent.__init__
   |
   |-- CodexVidbyteTranslator.translate_agent()
   |       |-- CodexMiddlewareValidator.validate()   <- NEW: reject 6 inner hooks
   |                                                    ConfigurationError, names the hook
   v
CodexHarnessAgent.arun()
   |
   |-- context translation
   |-- CodexMiddlewareRunner.before_run()   -> ABORT_RUN? raise, zero native calls
   v
CodexTransport.run()
   |  raise                              | success
   v                                     v
  on_model_error() then re-raise      result translation
   (original exception, never replaced)   |
                                          |-- after_run()  -> ABORT_RUN? raise (turn already ran)
                                          v
                                     AgentMessage + middleware metadata/events
```

---

## 6. Detailed Design

### 6.1 Middleware settings field

**File(s):** `vidbyte/lib/dataclasses/codex.py`
**Type:** Modified

#### What it does

Carries the caller's middleware onto the agent settings record.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class CodexHarnessAgentSettings:
    ...
    middleware: tuple[AgentMiddleware, ...] = ()
```

`AgentMiddleware` is annotated under the module's existing `TYPE_CHECKING` block, because `vidbyte.middleware` is an orchestration-tier package and `vidbyte.lib` may not import it at runtime under the A006 dependency graph.

#### Logic / Algorithm

1. `__post_init__` requires a tuple whose every element exposes the nine hook attributes and a `middleware_name`, duck-typed — the same approach the record already uses for `context_manager`, and the only one available without a runtime import.

#### Edge Cases & Error Handling

- **A list instead of a tuple.** Rejected, matching every other sequence field on this record.
- **An object that is not middleware at all.** Rejected by the duck-typed check, before the orchestration-layer validator would fail more obscurely.

### 6.2 CodexMiddlewareValidator and CodexMiddlewareRunner

**File(s):** `vidbyte/agents/codex/middleware.py`
**Type:** New file

#### What it does

Rejects unrepresentable middleware at construction, and runs the three supported hooks at each turn boundary.

#### Interface / API

```python
class CodexMiddlewareValidator:
    """Rejects middleware whose hooks have no Codex enforcement point."""

    @classmethod
    def validate(cls, middleware: Sequence[AgentMiddleware]) -> None: ...

    @staticmethod
    def _unsupported_overrides(middleware: AgentMiddleware) -> tuple[str, ...]: ...


class CodexMiddlewareRunner:
    """Runs the turn-boundary middleware hooks Codex can honestly support."""

    def __init__(self, middleware: Sequence[AgentMiddleware]) -> None: ...

    @property
    def enabled(self) -> bool: ...

    async def before_run(self, request: CodexMiddlewareRequest) -> Mapping[str, Any]: ...
    async def after_run(self, request: CodexMiddlewareRequest) -> Mapping[str, Any]: ...
    async def on_model_error(self, request: CodexMiddlewareRequest) -> None: ...

    def metadata(self) -> dict[str, Any]: ...
```

`CodexMiddlewareRequest` is a frozen slots dataclass in `vidbyte/lib/dataclasses/codex.py` holding `agent_name: str`, `prompt: str`, `elapsed_seconds: float`, and `error: BaseException | None`.

`CODEX_UNSUPPORTED_MIDDLEWARE_HOOKS` is a frozenset in `vidbyte/lib/constants/codex.py` naming the six hooks, so the list is data rather than a literal buried in a loop.

#### Logic / Algorithm

`validate`:
1. For each middleware, collect the unsupported hook names whose function object on `type(middleware)` is not `AgentMiddleware`'s own.
2. Raise `ConfigurationError` naming the middleware and every hook it overrode, plus the reason: Codex owns its inner loop, so no enforcement point exists.

`before_run` / `after_run`:
1. Build a `MiddlewareContext` with the hook, agent name, message, and elapsed seconds.
2. Await the matching `MiddlewarePipeline` method.
3. Interpret the decision through one shared `_apply` helper and return the transform's metadata.

`on_model_error`:
1. Build a context carrying the raised exception in `MiddlewareContext.error`.
2. Await `pipeline.on_model_error` and discard its decision beyond recording, because the original exception must propagate unchanged.

`_apply` dispatches on `decision.action` through a mapping rather than an if/else ladder, so the unsupported set is visible in one place and a future `MiddlewareAction` member fails loudly instead of falling through a final `else`.

#### Edge Cases & Error Handling

- **Empty middleware tuple.** `enabled` is false, no pipeline work happens, and the agent's hot path is unchanged.
- **`SLEEP`.** Handled inside `MiddlewarePipeline._run`, which awaits and continues, so the runner never observes it. Documented in the file header so a reader does not add dead handling for it.
- **A raising `fail_closed=True` middleware.** The pipeline converts it to `ABORT_RUN` with a `middleware_error` reason, so it aborts through the same path as an explicit abort.
- **An unknown future `MiddlewareAction`.** The dispatch mapping raises `CODEX_MIDDLEWARE_UNSUPPORTED` rather than silently continuing.

### 6.3 CodexHarnessAgent wiring

**File(s):** `vidbyte/agents/codex/agent.py`
**Type:** Modified

#### Logic / Algorithm

1. `__init__` builds `self._middleware = CodexMiddlewareRunner(self.settings.middleware)`.
2. `arun` awaits `before_run` after context translation and before the transport call.
3. The transport call is wrapped so a raised exception awaits `on_model_error` and then re-raises with a bare `raise`.
4. After result translation, `arun` awaits `after_run`, then merges the pipeline's metadata and events into the reply.
5. Because `AgentMessage` is frozen, the merge produces a replacement message via `dataclasses.replace`, not a mutation.

#### Edge Cases & Error Handling

- **Cancellation.** `on_model_error` runs for `Exception` only; a `BaseException` such as `asyncio.CancelledError` propagates without invoking middleware, because a cancelled turn is not a model error and running caller code during cancellation unwinding invites a second failure. The S019 lint rule enforces that cancellation is re-raised unchanged.
- **`after_run` aborting.** The turn has already executed and its side effects on disk are real. The error says so through its `operation` value rather than implying the turn was prevented.

### 6.4 Failure vocabulary

**File(s):** `vidbyte/lib/enums/failure.py`
**Type:** Modified

Adds `CODEX_MIDDLEWARE_ABORTED = "codex.middleware_aborted"` and `CODEX_MIDDLEWARE_UNSUPPORTED = "codex.middleware_unsupported"`. Two members rather than one, because they need different operator responses: an abort is policy working as designed, while an unsupported decision is a configuration mistake to fix.

---

## 7. Data Model Changes

N/A - no persisted records, no database, no migration. One dataclass (`CodexMiddlewareRequest`) and one settings field are added in memory only.

---

## 8. API Changes

N/A - no HTTP endpoints. The public Python surface gains one settings field and two `FailureCode` members, both additive.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/codex-middleware.md` | This design document |
| CREATE | `vidbyte/agents/codex/middleware.py` | `CodexMiddlewareValidator`, `CodexMiddlewareRunner` |
| MODIFY | `vidbyte/lib/dataclasses/codex.py` | `middleware` field, `CodexMiddlewareRequest` |
| MODIFY | `vidbyte/lib/constants/codex.py` | `CODEX_UNSUPPORTED_MIDDLEWARE_HOOKS` (A007) |
| MODIFY | `vidbyte/lib/enums/failure.py` | Two new `CODEX_MIDDLEWARE_*` codes |
| MODIFY | `vidbyte/agents/codex/config.py` | Validate middleware in `translate_agent` |
| MODIFY | `vidbyte/agents/codex/agent.py` | Own the runner; run the three hooks; merge metadata |
| MODIFY | `vidbyte/agents/codex/__init__.py` | Export `CodexMiddlewareRequest` |
| MODIFY | `vidbyte/agents/__init__.py` | Re-export on the agents facade |
| MODIFY | `vidbyte/__init__.py` | Re-export for public-export integrity (S015) |
| CREATE | `tests/test_codex_middleware.py` | Feature tests for the Testing Plan below |
| CREATE | `scripts/test-codex-middleware.py` | Phase 5 verification script |

Totals: 4 create, 8 modify, 0 delete.

---

## 10. Testing Plan

All tests run offline against a fake transport.

### Unit Tests

- `CodexMiddlewareValidator` -> `accepts middleware overriding only before_run` — [Edge Case]
- `CodexMiddlewareValidator` -> `accepts middleware overriding no hooks at all` — [Edge Case]
- `CodexMiddlewareValidator` -> `rejects middleware overriding before_tool_call, naming the hook` — [Hidden Failure] — the headline defect this whole design exists to prevent: a `fail_closed=True` tool policy that loads successfully and never runs.
- `CodexMiddlewareValidator` -> `names every unsupported hook a middleware overrode, not just the first` — [Silent Failure] — fixing one named hook and re-running should not reveal a second one only on the next attempt.
- `CodexMiddlewareValidator` -> `rejects each of the six inner-loop hooks` (parameterized) — [Edge Case]
- `CodexMiddlewareValidator` -> `accepts a subclass of a subclass that overrides nothing new` — [Hidden Assumption] — override detection must walk the MRO, not just the immediate class dict.
- `CodexMiddlewareRunner` -> `is disabled for an empty middleware tuple` — [Edge Case]
- `CodexMiddlewareRunner` -> `raises CODEX_MIDDLEWARE_UNSUPPORTED for a DENY_TOOL decision` — [Hidden Failure] — silently ignoring it would report a denied tool as permitted.
- `CodexMiddlewareRunner` -> `raises CODEX_MIDDLEWARE_UNSUPPORTED for a RETRY decision` — [Hidden Failure]
- `CodexMiddlewareRunner` -> `raises CODEX_MIDDLEWARE_UNSUPPORTED naming the transform field for a system transform` — [Silent Failure] — a dropped system override changes what the caller believes the agent was told.
- `CodexMiddlewareRunner` -> `applies transform metadata` — [Edge Case]
- `CodexMiddlewareRunner` -> `populates hook, agent_name, and message on the context` — [Silent Failure] — a middleware that inspects `ctx.message` and finds `""` makes a wrong decision without erroring.
- `CodexMiddlewareRunner` -> `leaves inner-loop context fields at their defaults` — [Hidden Assumption] — proves the runner does not fabricate an `iteration_count` of 1.
- `CodexHarnessAgentSettings` -> `rejects a middleware list rather than a tuple` — [Hidden Assumption]
- `CodexHarnessAgentSettings` -> `rejects an object that is not middleware` — [Hidden Assumption]

### Integration Tests

The flow to prove is that a real `MiddlewarePipeline` drives a real turn. Only the transport is faked, because the defects here — an abort that still calls the provider, a `fail_closed` error that does not abort, a swallowed transport exception — only appear in the wired lifecycle.

- A `before_run` returning `ABORT_RUN` raises `CODEX_MIDDLEWARE_ABORTED` and the fake transport records zero calls. [Hidden Failure] — an abort evaluated after the transport call would have already spent tokens and possibly edited files.
- A `fail_closed=True` middleware whose `before_run` raises aborts the turn with zero transport calls. [Hidden Failure] — proves the pipeline's exception policy is genuinely in force rather than reimplemented and diverged.
- A `fail_closed=False` middleware whose `before_run` raises lets the turn proceed, and the reply's middleware events include `middleware_error_fail_open`. [Silent Failure] — the inverse: a fail-open middleware must not abort.
- A transport exception invokes `on_model_error` and still propagates the transport's own exception type, not a middleware-derived one. [Hidden Failure] — requirement 14; the caller must be told what actually went wrong.
- An `after_run` returning `ABORT_RUN` raises with `operation="after_run"` **after** the transport was called exactly once. [Silent Failure] — proves the two abort points are distinguishable, so a caller cannot read an after-run abort as "the turn never happened."
- Two middleware run in declared order, and their `CONTINUE` metadata merges with later keys winning. [Silent Failure] — reversed order silently changes which policy has the final say.
- An agent with an empty middleware tuple produces a reply byte-identical to one built before this change. [Hidden Assumption] — the no-middleware path must stay untouched.

### Manual / QA Test Cases

1. Given a middleware subclass overriding `before_tool_call`, when a `CodexHarnessAgent` is constructed with it, then construction fails with a message naming `before_tool_call` — before any turn runs. — [Hidden Failure]
2. Given a `before_run` middleware that aborts on a keyword in the prompt, when a matching prompt is submitted, then no Codex process starts and the caller sees `codex.middleware_aborted`. — [Edge Case]
3. Given a middleware returning `RETRY`, when a turn runs, then the caller sees `codex.middleware_unsupported` rather than a turn that quietly did not retry. — [Silent Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `openai-codex` | 0.147.0, optional extra | Reached only after `before_run` passes | None added |

No dependency additions. `MiddlewarePipeline` is reused unchanged.

---

## 12. Rollout & Deployment

No feature flag. The change is additive and the default is an empty middleware tuple, so existing agents behave identically. The one intentionally breaking behavior is by design and cannot affect existing code: constructing an agent with inner-loop middleware now fails, and no existing caller can be doing that because the settings record had no `middleware` field before this change.

This is PR 4 of five independent Codex-translation PRs, each branched from `origin/main`. It should be merged after PR 3 (`feat/codex-speed-tracking`); it adds another collaborator to `__init__` and another await into `arun`, adjacent to PRs 2 and 3.

---

## 13. Open Questions

- [ ] Should `MiddlewareTransform.system` eventually rewrite the developer instructions? It is feasible — `before_run` precedes the transport call, which is where `developer_instructions` is composed — but the semantics need settling first: does a rewrite apply to this turn only, or persist for the thread, given that `thread_resume` re-sends instructions? Rejected loudly for now rather than applied with a guessed lifetime.
- [ ] `MiddlewarePipeline` accumulates events for the life of the pipeline, and the Codex runner holds one per agent rather than per turn. For a long-lived thread that list grows. Should the runner reset per turn, matching the usage and speed trackers, at the cost of losing cross-turn middleware history?
- [ ] Should `on_model_error` be able to convert a transport failure into a recovered result (an `AgentFallbackSettings`-style path)? That is roadmap task B05 and needs its own design; today the hook observes and cannot substitute.

---

## 14. Alternatives Considered

### Alternative 1: Map the six inner hooks onto Codex's native hook system

- What: Translate `before_tool_call` to a native `PreToolUse` hook, `after_tool_call` to `PostToolUse`, and so on.
- Why rejected: Native Codex hooks are configuration-level and can fail open, and `PostToolUse` fires after the command already ran. A `fail_closed=True` Vidbyte policy mapped onto a fail-open native path would be reported as enforced while not being enforced — the single worst outcome available in this design space. The roadmap's H-series covers this properly, starting from what each native event can actually enforce.

### Alternative 2: Accept inner-loop middleware and silently skip those hooks

- What: Run the three supported hooks and ignore the rest.
- Why rejected: A guardrail that loads without complaint and never executes is indistinguishable, from the caller's side, from one that is working. Failing at construction costs the caller one clear error; silently skipping costs them the incident.

### Alternative 3: Reimplement hook dispatch inside the Codex package

- What: A small Codex-local loop over the middleware, calling the three hooks directly.
- Why rejected: It would duplicate `fail_closed` handling, sleep handling, decision merging, and event recording. Two implementations of `fail_closed` is two behaviors that drift, and the second one is the one nobody tests.

### Alternative 4: Ignore `DENY_TOOL` and `RETRY` as no-ops

- What: Treat them as `CONTINUE`, since neither has a meaning at this boundary.
- Why rejected: They are valid decisions the caller deliberately returned. A caller who returns `RETRY` and gets one attempt has been told something false about their own policy. Raising costs them a clear error; ignoring costs them a wrong belief.
