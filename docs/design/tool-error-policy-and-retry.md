# Design Doc: Tool Error Policy & Retry

**Status:** Implemented
**Author:** Claude
**Created:** 2026-07-05
**Last Updated:** 2026-07-05

> **Doc 3 of 3** in the tool-error initiative.
> 1. `tool-error-taxonomy-and-authoring` — the *author* layer (`ToolError`/`ToolErrorKind`/`retryable`). **Prerequisite.**
> 2. `provider-aware-tool-error-rendering` — the *render* layer (`format_tool_result` per-provider envelopes). **Prerequisite** (this doc drives its verbosity/redaction knobs).
> 3. **`tool-error-policy-and-retry`** (this doc) — the *decide* layer. Declarative settings on `AgentLoopSettings` plus a built-in middleware that retries transient errors, gates on idempotency, enriches model-visible results, and controls loop continuation.
>
> This doc consumes Docs 1 and 2. Build it last.

---

## 1. Overview

With Doc 1 producing structured tool errors and Doc 2 rendering them per provider, this doc decides *what the loop does* about a tool error: retry it (silently, with backoff, when it's transient and the tool is idempotent), reflect it to the model (when the model should fix its own arguments), enrich the model-visible message (verbosity, hints, redaction), or — as a circuit breaker — abort the run after too many failures. The user proposed "tool policy settings on the agent loop settings (retry_number, include full error message, etc.)" — this doc delivers that as a nested `ToolErrorPolicy` on `AgentLoopSettings`, and implements the behavior as a built-in `ToolErrorPolicyMiddleware` rather than baking control flow into the runtime. A key finding drives one required runtime change: the `after_tool_call` middleware hook currently does **not** honor a `retry` decision (only `ABORT_RUN` and a result transform), so tool-call retry needs new, minimal runtime plumbing to re-invoke a tool call with backoff.

---

## 2. Original User Prompts

**Prompt 1:** question for the vidbyte-sdk/ repo, in regards to our tools (vidbyte/tools). right now what is the lifecycle behind tooling errors during the agent runtime. For example, how do we handle schema/arguements errors, execution errors, etc, and what are some other types of tools errors that could potentially occur?

**Prompt 2:** well before we get to exact implementation I want to express my intent. I basically first want each error tool to have its own tool errors (argeument errors, execution error, etc). I seems like we have these already, and if there are any more error classes we could define for our tools please briefly describe these (also I think it is a very good idea for each tool to potentially come with like a custom string message just incase there is some very nuonced detail about the error, ex: like a terminal command tool would come with like a 'make sure you are running the terminal commands on the right operations system' or something like that, and we could add these first class error messages to the tools themselves). Then, with these tool error messages I want make it so that these error messages actually get propagated to the agent and get filled within the context window so that if we have a tool error the run doesnt just stop and the agent can actually see information about tool error. How can we add this and what is the cleanest entry point. The idea that I had was we add like some "tool policy" settings to the vidbyte/agent/settings (agent loop settings), and then with these settings we can derive the tool error/execution logic in the agent class (tool settings like retry_number, include full error message, etc, I feel like you could do a better job of deriving exact settings for this). What do you think about all of this?

**Prompt 3:** great, can you decompose all of this into like 2-3 design docs and one thing that I want you to remember is to take into considers that each providers takes in tools in a specific way, so just make sure you take this into consideration in your design docs

---

## 3. Structured Conversation Notes

### Key Decisions

- **Declarative knobs live on settings; behavior lives in middleware.** Add a nested `ToolErrorPolicy` to `AgentLoopSettings` (the user's requested location), but implement the retry/enrich/abort behavior as a built-in `ToolErrorPolicyMiddleware`. Rationale: `runtime.py` is already ~1400 lines owning resolution, permissions, tracing, compaction, and the loop; retry/backoff/enrichment is a cross-cutting concern the middleware layer was built for, and the SDK already ships model-call retry middlewares (`ModelRetryMiddleware`, `ExponentialBackoffRetryMiddleware`) plus a `ToolPolicyMiddleware`, `circuit_breaker`, and `rate_limit` — this is the established pattern.
- **The proposed settings, refined** (improving on the user's `retry_number` / `include full error message`):
  - `max_retries_per_tool_call: int = 0` — silent programmatic retry budget per call. **Wire the already-existing-but-dead `AgentLoopSettings.max_retries`** (`loop.py:57`, currently referenced nowhere) into this, or supersede it.
  - `retry_on: frozenset[ToolErrorKind] = {TIMEOUT, RATE_LIMITED, UPSTREAM_ERROR}` — which kinds are eligible for silent retry. Defaults to the transient set.
  - `retry_backoff_base_seconds: float = 0.5`, `retry_backoff_multiplier: float = 2.0`, `retry_backoff_cap_seconds: float = 30.0` — exponential backoff, mirroring `ExponentialBackoffRetryMiddleware`'s proven formula (`exponential_backoff_retry.py:92`).
  - `retry_only_idempotent: bool = True` — **only silently retry tools whose `ToolPermission` is `SAFE`/`READ`** (or explicitly flagged idempotent). Prevents double-writes/double-charges on `WRITE`/`EXECUTE` tools.
  - `error_verbosity: ErrorVerbosity = STANDARD` — enum `MINIMAL | STANDARD | FULL`, **replacing the user's `include_full_error_message` bool** because there are genuinely three tiers (MINIMAL "tool failed"; STANDARD "kind + message + hint"; FULL "+ exception detail/traceback for dev").
  - `include_remediation_hint: bool = True` — surface the tool-authored hint (Doc 1).
  - `mark_provider_error_flag: bool = True` — enable Doc 2's `is_error`/`status` provider affordances.
  - `redact_exception_details: bool = True` — sanitize raw `{exc}` strings (addresses the leak at `runtime.py:1009`/`:1102`).
  - `on_unrecoverable: UnrecoverableAction = CONTINUE` — after retries exhausted or a terminal error, either `CONTINUE` (let the model react — current behavior) or `ABORT_RUN`.
  - `max_total_tool_errors: int | None = None` — circuit breaker: abort the run after N total tool errors, to stop an agent burning tokens in an error loop.
- **Two retry philosophies, both encoded.** (a) *Silent/programmatic* retry for transient infra kinds (`TIMEOUT`/`RATE_LIMITED`/`UPSTREAM_ERROR`) — the model never sees the failed attempts; the runtime re-invokes with backoff. (b) *Reflective* retry for `INVALID_ARGUMENTS` and similar terminal-for-identical-call kinds — no silent retry; the enriched error is surfaced so the *model* fixes its arguments next iteration (this is the existing loop-continues behavior). `retry_on` selects (a); everything else falls to (b).
- **Idempotency gating is a first-class safety requirement, not a nicety.** Silent retry of a non-idempotent tool is a footgun precisely on the tools where errors cost the most. Gate on the existing `ToolPermission` enum (`tools.py:35`).

### Rejected Alternatives

- **Baking retry/abort logic directly into `AgentRuntime.execute_tool_call` / the loop.** Rejected as the *primary* home — it grows an already-overloaded file and makes the policy non-composable. HOWEVER, a *minimal* runtime change is unavoidable (see the retry-plumbing finding) — the loop must learn to honor a tool-call retry decision. The distinction: runtime gains the *mechanism* to re-invoke; the middleware owns the *policy* of when.
- **Reusing `ModelRetryMiddleware` / `ExponentialBackoffRetryMiddleware` directly.** Rejected — those hook `on_model_error` and retry *model* calls, not tool calls. Different lifecycle hook (`after_tool_call`), different retry target. We imitate their structure (per-run state in `ctx.run_state`, backoff formula) but need a new middleware.
- **A flat `include_full_error_message: bool`** (user's phrasing). Refined to the 3-tier `ErrorVerbosity` enum for the reasons above.
- **Letting the model do all retries (no silent retry).** Rejected — a network `TIMEOUT` or `RATE_LIMITED` shouldn't consume a model turn and pollute context; those are infra concerns best retried silently.

### Constraints & Assumptions

- **CRITICAL FINDING — `after_tool_call` does not support retry today.** In the runtime, the `after_tool_call` decision is consumed at `runtime.py:1332-1338`: only `MiddlewareAction.ABORT_RUN` is handled, plus the `transform.model_visible_tool_result` at `:1341-1342`. The `MiddlewareAction.RETRY` value *exists* (`middleware.py:50`) and `MiddlewareDecision.retry(...)` *exists* (`middleware.py:134`), but its docstring says "Retry the failed **model** call" and it is only interpreted in the `on_model_error` path. **Therefore tool-call retry requires new runtime plumbing**: the tool-call execution site (around `runtime.py:1308-1344`) must, on a retry decision from `after_tool_call` (or from a dedicated policy hook), sleep for the backoff and re-invoke `execute_tool_call` for the same `ToolCall`, up to the budget, before appending the (final) result to `messages`.
- **`AgentLoopSettings` is a plain validated class** (`loop.py:35`), not a dataclass, with `_validate*` methods and a `to_runtime_config()` that maps a subset to the internal `AgentRuntimeConfig`. The new `tool_error_policy` field should follow the same validation-in-`__init__` pattern; `ToolErrorPolicy` itself can be a small validated class or frozen dataclass. `_render_loop_settings_block` (`runtime.py:1211`) intentionally excludes `max_retries`/`timeout_seconds`/`allowed_tools` from the model-visible loop-settings block (`:1216` comment) — tool-error policy is runtime behavior, likewise not shown to the model.
- **How settings reach the middleware:** decide the wiring. Options: (a) `AgentLoopSettings` (or the agent base) constructs and registers a `ToolErrorPolicyMiddleware(policy)` automatically when `tool_error_policy` is set; (b) the runtime reads the policy and passes it to `format_tool_result` (Doc 2) and applies retry inline. Recommendation: (a) for enrichment + retry policy via middleware, since middleware is the composable seam — but the *retry re-invocation mechanism* is the runtime change from the finding above. Confirm during implementation which hook the middleware uses to *request* a tool retry.
- Must preserve today's default behavior when no policy is set: loop continues on tool error, no retries, error output visible to model. All new knobs default to a no-op-ish or safe posture (`max_retries_per_tool_call=0`, `on_unrecoverable=CONTINUE`).

### Clarifications & Answers

- **Q (from Doc 2 hand-off): who owns verbosity/redaction?** A: This doc *defines* the knobs; Doc 2 *implements* the rendering that honors them. The middleware (or runtime) passes the policy-derived `ToolErrorRenderOptions` into `format_tool_result`.
- **Q: does the run stop today on tool error?** A: No (established in conversation) — the loop already continues (`runtime.py:1339-1343`). This doc adds *optional* stopping (`on_unrecoverable=ABORT_RUN`, `max_total_tool_errors`) and *optional* silent retry — it does not change the default continue behavior.

### Terminology / Glossary

- **Silent / programmatic retry** — runtime re-invokes the tool call with backoff; the model never sees the intermediate failures.
- **Reflective retry** — the enriched error is surfaced to the model, which decides to change its next tool call.
- **Idempotency gate** — restricting silent retry to `SAFE`/`READ` (or flagged-idempotent) tools.
- **Circuit breaker** — aborting the run after `max_total_tool_errors` cumulative failures.
- **`ToolErrorPolicy`** — the new nested settings object on `AgentLoopSettings`.
- **`ToolErrorPolicyMiddleware`** — the new built-in middleware implementing the policy.

### Implementation Hints for the Downstream Model

- **Settings:** `vidbyte/agents/settings/loop.py`. Add `tool_error_policy: ToolErrorPolicy | None` to `AgentLoopSettings.__init__` and validate it. Define `ToolErrorPolicy` (+ `ErrorVerbosity`, `UnrecoverableAction` enums) either here or in a sibling `vidbyte/agents/settings/tool_error.py`. Export from `vidbyte/agents/settings/__init__.py` (currently exports only `AgentLoopSettings`, `:14`). Consider whether `to_runtime_config()` (`loop.py:99`) needs to carry the policy into `AgentRuntimeConfig` (`lib/dataclasses/agents.py`).
- **Middleware:** new `vidbyte/middleware/builtins/tool_error_policy.py`. Subclass `AgentMiddleware` (`middleware/base.py:21`). Relevant hooks: `after_tool_call` (enrich the result via `MiddlewareDecision.continue_(transform=MiddlewareTransform(model_visible_tool_result=...))`, and/or request retry) and `before_run` (init per-run state in `ctx.run_state[self.__class__]`, following `ModelRetryMiddleware._ModelRetryRunState` at `retry.py:23`). Register it in `vidbyte/middleware/builtins/__init__.py`.
- **`MiddlewareContext` gives you** `tool_call`, `tool_result`, `tool_is_internal`, `run_state`, `provider`, `metadata` (`middleware.py:151-175`) — everything needed to classify and decide. Read `result.metadata` for the Doc 1 `error`/`hint`/`retryable` keys; read the tool's `ToolPermission` for the idempotency gate (you may need the spec — see how `_tool_is_internal`/`_get_tool` resolve specs at `runtime.py:1057-1076`).
- **THE runtime change (unavoidable, keep it minimal):** at the tool-call execution site (`runtime.py:1308-1344`), teach the loop to honor a tool-retry decision — on retry, `await asyncio.sleep(backoff)` and re-call `self.execute_tool_call(call, ...)` up to the budget, then append only the final result. Decide the cleanest signal: either extend the `after_tool_call` decision handling to interpret `MiddlewareAction.RETRY` for tool calls (symmetric with `on_model_error`), or add a small dedicated retry loop in the runtime driven by the policy. Prefer extending the existing `after_tool_call` handling for symmetry. Update `MiddlewareDecision.retry`'s docstring (`middleware.py:142`) which currently says "model call."
- **Backoff formula:** copy `ExponentialBackoffRetryMiddleware._compute_delay` (`exponential_backoff_retry.py:92`) — capped exponential with optional jitter — for consistency.
- **Idempotency:** `ToolPermission` enum at `lib/dataclasses/tools.py:35` (`SAFE`/`READ`/`WRITE`/`EXECUTE`). Gate silent retry to `{SAFE, READ}` unless a future `idempotent` flag says otherwise.
- **Circuit breaker prior art:** `vidbyte/middleware/builtins/circuit_breaker.py` and `rate_limit.py` — read them; `max_total_tool_errors` may be expressible by composing/extending the existing circuit breaker rather than reinventing.
- **Prior design docs to imitate:** `docs/design/agent-loop-settings.md` (how settings were added), `docs/design/middleware-builtins-expansion.md` and `docs/design/agent-runtime-middleware.md` (middleware conventions), `docs/design/concurrent-middleware-safety.md` (per-run state must live in `ctx.run_state`, NOT on the instance, for concurrency safety — note `ExponentialBackoffRetryMiddleware` keeps `self._attempts` which the concurrency doc would flag; prefer `ModelRetryMiddleware`'s `run_state` approach).
- **Do NOT** put verbosity/redaction rendering logic in the middleware — that's Doc 2's `format_tool_result`. The middleware only *chooses* the `ToolErrorRenderOptions` and passes them down (or sets them where the runtime reads them before calling the formatter).

### Open Questions

- **Retry request mechanism:** extend `after_tool_call`'s `RETRY` handling in the runtime, or add a dedicated policy-driven retry loop? Recommendation: extend `after_tool_call` for symmetry with `on_model_error`. Needs the user's/implementer's confirmation since it touches runtime control flow.
- **Auto-registration vs. explicit:** should setting `AgentLoopSettings.tool_error_policy` auto-insert `ToolErrorPolicyMiddleware`, or must the developer add the middleware themselves? Recommendation: auto-register when the policy is present, so the settings object is self-contained (matches the user's mental model of "set it on settings and behavior follows").
- **`max_retries` reconciliation:** the existing dead `AgentLoopSettings.max_retries` (`loop.py:57`) — repurpose it as the tool-call retry budget, or leave it for model-call retries and add a distinct `max_retries_per_tool_call`? Recommendation: distinct field to avoid ambiguity; consider deprecating/clarifying `max_retries`.
- **Interaction with `deny_tool` / `middleware_denied`:** a denied tool is a terminal state (`DENIED`), never retried. Confirm the policy skips denied results.
- **Compaction ordering:** ensure `ToolResultCompactionMiddleware` (`runtime.py:86`) doesn't truncate away the enriched error's leading `[tool_error ...]` line/hint. Coordinate ordering of the two middlewares.

---

## 4. Goals & Non-Goals

### Goals

- Add a nested `ToolErrorPolicy` (+ `ErrorVerbosity`, `UnrecoverableAction`) to `AgentLoopSettings`, validated in the existing style.
- Implement a built-in `ToolErrorPolicyMiddleware` that: silently retries transient, idempotent tool calls with exponential backoff; reflects terminal errors to the model; enriches the model-visible result (via Doc 2 render options); and optionally aborts on unrecoverable errors or a total-error circuit breaker.
- Add the minimal runtime plumbing to honor a tool-call retry decision (re-invoke with backoff).
- Wire the currently-dead retry budget and the Doc 2 verbosity/redaction knobs.
- Preserve today's default behavior when no policy is configured.

### Non-Goals

- The error taxonomy / `ToolError` (Doc 1).
- Provider-specific rendering mechanics (Doc 2) — this doc only *selects* options.
- Per-tool execution *timeouts* (the `asyncio.wait_for` wrapper). `TIMEOUT` kind is consumed here for retry classification, but adding actual timeout enforcement is a separate follow-up (flag it).
- Model-call retry behavior (already covered by existing middlewares).

---

## 5. Background & Context

The user wants tool errors to be actionable: the run continues, the model sees a useful message, and transient failures get retried without the model having to babysit them. The audit shows the loop already continues on error, the SDK already has a mature middleware system and model-call retry builtins, and `AgentLoopSettings` already has an unused `max_retries` field — but there is no tool-call retry, no idempotency gating, no verbosity control, and the `after_tool_call` hook can't request a retry. This doc closes those gaps with a settings-plus-middleware design consistent with existing SDK patterns, plus the one small runtime change needed to make tool retry possible.

---

## 6. Requirements

1. `AgentLoopSettings` MUST accept an optional `tool_error_policy: ToolErrorPolicy`, validated (positive ints, non-negative delays, consistent backoff) in the existing `_validate*` style.
2. `ToolErrorPolicy` MUST expose: `max_retries_per_tool_call`, `retry_on` (set of `ToolErrorKind`), backoff params, `retry_only_idempotent`, `error_verbosity`, `include_remediation_hint`, `mark_provider_error_flag`, `redact_exception_details`, `on_unrecoverable`, `max_total_tool_errors`.
3. A `ToolErrorPolicyMiddleware` MUST silently retry a failed tool call when its `kind ∈ retry_on`, retries remain, and (if `retry_only_idempotent`) the tool's `ToolPermission ∈ {SAFE, READ}`; using capped exponential backoff.
4. On a non-retryable/terminal error, the middleware MUST enrich the model-visible result per `error_verbosity`/`include_remediation_hint`/`redact_exception_details` (delegating the actual shaping to Doc 2's `format_tool_result` via render options) and let the loop continue — unless `on_unrecoverable == ABORT_RUN`.
5. The runtime MUST honor a tool-call retry decision by sleeping the backoff and re-invoking `execute_tool_call` for the same call, up to the budget, appending only the final result to `messages`.
6. When cumulative tool errors in a run reach `max_total_tool_errors` (if set), the run MUST abort with a clear reason.
7. Per-run counters (retry attempts, total errors) MUST live in `ctx.run_state`, not on the middleware instance (concurrency safety).
8. With no `tool_error_policy` configured, behavior MUST be identical to today (continue on error, no retry, error output visible).
9. Silent retry MUST NOT apply to denied (`DENIED` / `middleware_denied`) results.

---

## 7. Non-Functional Requirements

- **Reliability:** idempotency gate is mandatory to prevent duplicate side effects on retry. Backoff must be capped to avoid unbounded waits; overall retries bounded by budget and by `AgentLoopSettings.timeout_seconds`/`max_iterations`.
- **Concurrency:** per-run state in `ctx.run_state` keyed by middleware class (follow `concurrent-middleware-safety.md`); the middleware instance must be reusable across concurrent runs.
- **Security:** `redact_exception_details=True` by default; raw exception internals must not reach the model or logs when redaction is on.
- **Observability:** retry attempts, backoff delays, and circuit-breaker trips SHOULD be emitted as `MiddlewareEvent`s / trace metadata (the pipeline already records middleware decisions).
- **Performance:** error/retry path only; success path unaffected. Backoff sleeps are the only added latency and are bounded by the cap.

---

## 8. High-Level Design

Add a validated `ToolErrorPolicy` (plus `ErrorVerbosity` and `UnrecoverableAction` enums) and hang it off `AgentLoopSettings.tool_error_policy`. When present, the agent auto-registers a built-in `ToolErrorPolicyMiddleware(policy)`. The middleware initializes per-run counters in `before_run` and acts in `after_tool_call`: it reads the structured error (Doc 1 metadata) off `ctx.tool_result`, and (a) if the kind is in `retry_on`, retries remain, and the idempotency gate passes, requests a tool-call retry with a computed backoff delay; (b) otherwise, enriches the model-visible result by returning a `continue` decision whose `MiddlewareTransform.model_visible_tool_result` carries the policy-selected render options for Doc 2's formatter; (c) increments the total-error counter and, if it crosses `max_total_tool_errors` or `on_unrecoverable == ABORT_RUN` on a terminal error, returns `abort`.

The one runtime change: the tool-call execution site (`runtime.py:1308-1344`) is taught to honor a tool retry — on a retry decision it sleeps the backoff and re-invokes `execute_tool_call` for the same `ToolCall`, looping up to the budget, and only appends the final result via `format_tool_result`. This mirrors the existing `on_model_error → MiddlewareAction.RETRY` handling, extended to the tool path; `MiddlewareDecision.retry`'s docstring is generalized accordingly.

Data flow: tool fails → Doc 1 structured `ToolResult` → `after_tool_call` fires → `ToolErrorPolicyMiddleware` classifies via `kind`/`retryable` and checks `retry_on` + idempotency + budget. If retryable: runtime sleeps backoff, re-invokes the call, model never sees the intermediate failures. If terminal/exhausted: middleware enriches render options, runtime calls Doc 2's `format_tool_result` to produce the provider-native envelope, appends it to `messages`, and either continues (default) or aborts (policy). Cumulative errors feed the circuit breaker.

```
tool fails -> ToolResult{kind, hint, retryable}   [Doc 1]
                     |
              after_tool_call hook
                     v
        ToolErrorPolicyMiddleware  (reads ctx.tool_result, ctx.run_state)
          |
          |-- kind in retry_on AND budget left AND (permission in {SAFE,READ} if gated)
          |        -> request RETRY(sleep=backoff)
          |             -> [runtime] asyncio.sleep; re-invoke execute_tool_call   [RUNTIME CHANGE]
          |                (loop; model never sees intermediate failures)
          |
          |-- else (terminal / exhausted)
          |        -> continue_(transform=render_options)  --> Doc 2 format_tool_result
          |             -> provider-native error envelope appended to messages
          |             -> total_errors++ ; if >= max_total_tool_errors OR on_unrecoverable==ABORT_RUN
          |                                   -> abort("tool_error_circuit_break")
          v
   loop continues (default) or aborts (policy)

Settings:  AgentLoopSettings.tool_error_policy = ToolErrorPolicy(...)   [loop.py]
             -> auto-registers ToolErrorPolicyMiddleware
```

---
