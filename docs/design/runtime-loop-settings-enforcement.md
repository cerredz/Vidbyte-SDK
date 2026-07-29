# Design Doc: Runtime Loop Settings Enforcement

**Status:** Approved
**Author:** Codex
**Created:** 2026-07-17
**Last Updated:** 2026-07-17

---

## 1. Overview

This change closes the gap between the public `AgentLoopSettings` contract and the default direct text runtime. `max_parallel_tool_calls`, `max_retries`, `timeout_seconds`, `context_window_budget`, and `allowed_tools` are currently accepted and validated but are dropped by `to_runtime_config()` and therefore cannot affect execution. The implementation will carry all five settings into `AgentRuntimeConfig`, enforce them at the runtime boundaries where they apply, expose machine-readable stop reasons for hard limits, and update the canonical SDK documentation so no setting is described as reserved after it becomes operational.

---

## 2. Goals & Non-Goals

### Goals

- Preserve all five currently dropped `AgentLoopSettings` fields in `AgentRuntimeConfig`.
- Enforce a hard wall-clock timeout around the full direct text run, including attached context-window algorithms, middleware, model calls, and tool calls.
- Treat `max_retries` as the maximum number of retries after an initial failed model invocation and stop deterministically when the retry budget is exhausted.
- Execute model-requested tool calls with an observable concurrency ceiling when `max_parallel_tool_calls` is configured, while preserving provider order in recorded contexts and model-visible tool results.
- Enforce `context_window_budget` before every model invocation by deterministically trimming removable conversation history and refusing the invocation when non-removable input alone exceeds the budget.
- Enforce `allowed_tools` both by hiding disallowed user-tool schemas from the model and by denying an attempted disallowed call before permission checks, validation, or tool execution.
- Preserve the internal `isDone` control tool regardless of the user-tool allowlist.
- Keep behavior unchanged for each setting whose value is `None`.
- Update runtime metadata and documentation so enforcement decisions are discoverable.

### Non-Goals

- Adding or modifying automated tests or verification scripts; this workflow intentionally makes no test-file changes.
- Retrying failed tool bodies. Tool retries can duplicate non-idempotent side effects and require a separate opt-in/idempotency contract.
- Enforcing these direct-loop settings in MCTS, actor-model, image, video, audio, embedding, or other non-direct-text runtime paths.
- Providing provider-specific exact tokenizers. Context-window enforcement will use the deterministic approximation already established by the compaction subsystem.
- Changing the public `AgentLoopSettings` constructor, its existing validation rules, or the legacy flat `BaseAgent` keyword surface.
- Turning `compaction_trigger_tokens` or `compaction_target_tokens` into new runtime behavior; those fields are outside the five-field bug report.
- Changing user-supplied middleware APIs or removing the existing retry, runtime-limit, tool-policy, or compaction middleware classes.

---

## 3. Background & Context

`AgentLoopSettings` is the public configuration object attached to every `BaseAgent`. Its constructor validates ten loop-related settings, but `AgentLoopSettings.to_runtime_config()` currently forwards only `max_iterations`, `max_tokens`, `max_tool_calls`, and the two compaction values. The internal frozen `AgentRuntimeConfig` consequently has no representation for `max_parallel_tool_calls`, `max_retries`, `timeout_seconds`, `context_window_budget`, or `allowed_tools`.

The original `docs/design/agent-loop-settings.md` and `skills/agentic-loop-settings/SKILL.md` explicitly deferred enforcement of these five fields. The default linear runtime now has the required integration points: an async run boundary, middleware-aware model invocation retry handling, before/after tool hooks, provider message transforms, deterministic context compaction, and an internal tool catalog. The current runtime still executes parsed tool calls sequentially and its loop-settings docstring says only iteration, token, and tool-call counts are tracked.

Relevant architecture discovered during the audit:

- `BaseAgent` resolves a public `AgentLoopSettings`, calls `to_runtime_config()`, and passes the result into a newly constructed runtime.
- `AgentRuntime` is the default direct text model/tool loop. It adds the internal `isDone` tool, invokes middleware at explicit lifecycle boundaries, accumulates provider-reported token use, and records tool call contexts.
- `_invoke_with_middleware()` already supports middleware-requested model retries but has no configuration-owned retry ceiling.
- Tool calls are parsed as an ordered sequence and processed one at a time by `_process_tool_call()`.
- `MessageHistoryCompactionMiddleware` and `ContextCompactionEngine` already provide deterministic approximate-token trimming with provider-message conversion support.
- `ToolPolicyMiddleware` establishes the security precedent that internal tools remain allowed by default, even when user tools are allowlisted.
- The project supports Python 3.11+, so the standard-library `asyncio` timeout and concurrency primitives are available without a dependency change.

The repository is currently on `feat/context-minimal-fanout-trace` with unrelated untracked files. This design file uses a new path and does not alter or overwrite those files. After approval, the implementation phase must still create a clean isolated worktree from an updated `main` as required by the workflow.

---

## 4. Requirements

### Functional Requirements

1. `AgentLoopSettings.to_runtime_config()` must copy `max_parallel_tool_calls`, `max_retries`, `timeout_seconds`, `context_window_budget`, and `allowed_tools` without changing their values.
2. `AgentRuntimeConfig` must define those five fields with `None` defaults and preserve the existing frozen, slotted dataclass contract.
3. `AgentRuntimeConfig.__post_init__()` must validate positive configured numeric limits consistently with the public settings object.
4. With all five settings unset, the direct text runtime must preserve its current sequential tool execution, exception propagation, tool exposure, context construction, and lack of a wall-clock deadline.
5. When `timeout_seconds` is configured, the runtime must apply one wall-clock deadline to the complete `AgentRuntime.arun()` operation rather than resetting the timeout per iteration, retry, model call, or tool call.
6. When the deadline expires, the in-flight async operation must be cancelled and the runtime must return an `AgentResult` whose metadata contains `stop_reason="timeout"` and the configured timeout value.
7. When `max_retries` is configured, one initial failed model call must be followed by no more than `max_retries` additional attempts for that model step.
8. A user middleware `ABORT_RUN` decision must still stop immediately; a user middleware `RETRY` decision may request a retry but may not exceed the configuration-owned `max_retries` ceiling.
9. When no retry middleware requests a retry, a configured `max_retries` value must itself enable immediate retries so the setting has standalone behavior.
10. Exhausting configured model retries must return an `AgentResult` with `stop_reason="max_retries"`, the retry count, the configured limit, and the final error type in metadata.
11. When `max_parallel_tool_calls` is `None`, the runtime must retain one-at-a-time tool execution.
12. When `max_parallel_tool_calls=N`, the runtime must execute at most `N` user or internal tool bodies concurrently within one model response; `N=1` must remain strictly sequential.
13. Concurrent tool results, `ToolCallContext` records, and model-visible provider messages must be committed in the model's original tool-call order, not task-completion order.
14. The internal `isDone` call must act as an ordering barrier: calls after the first `isDone` in the same model response must not be dispatched.
15. Bounded dispatch must honor the remaining `max_tool_calls` allowance before launching a batch so concurrency cannot overshoot the existing total tool-call ceiling.
16. Before-tool middleware decisions must be evaluated before a tool body is dispatched, and after-tool middleware plus context primitive binding must be finalized in provider order.
17. When `context_window_budget` is configured, the runtime must estimate the complete model-visible input before each model call, including the current prompt, system/context string, tool schemas, response-format payload, and provider conversation messages.
18. Context estimation must use the existing deterministic four-characters-per-token approximation where an exact counter is not available.
19. If estimated input exceeds `context_window_budget`, the runtime must trim the oldest removable conversation messages using the existing provider-boundary-aware compaction path, then re-estimate the input.
20. If the fixed/non-removable input still exceeds the budget after trimming, the runtime must skip the model invocation and return an `AgentResult` with `stop_reason="context_window_budget"` plus before/after estimates and the configured budget.
21. Context-budget enforcement must occur after `before_model_call` middleware transforms so later transforms cannot silently re-expand the call beyond the configured ceiling.
22. When `allowed_tools` is configured, provider schemas must contain only listed user tools plus runtime-internal tools.
23. A call to an unlisted user tool must be converted into a denied `ToolCallContext` and error `ToolResult` before registry lookup, permission checks, validation, or execution.
24. `allowed_tools=()` must deny every user tool while continuing to expose and permit internal `isDone`.
25. Denied calls must remain visible in normal tool-call accounting and result metadata.
26. `AgentStopReason` must add `TIMEOUT`, `MAX_RETRIES`, and `CONTEXT_WINDOW_BUDGET` values for the three new hard-stop outcomes.
27. Runtime and canonical skill documentation must distinguish hard-stop limits, bounded behavior settings, and settings omitted from the live `current/limit` prompt block.

### Non-Functional Requirements

- **Backward compatibility:** all new runtime-config fields are additive and default to `None`; existing callers that construct `AgentRuntimeConfig` positionally are not supported by the documented keyword-based style, but existing field order will remain unchanged before the appended fields.
- **Security:** disallowed tools must never reach permission validation or execution. Internal `isDone` remains exempt to avoid trapping the loop.
- **Reliability:** timeout and retry limits must be owned by the runtime configuration and must not be bypassable by user middleware. Tool execution exceptions continue to become normal failed tool results rather than automatic side-effecting retries.
- **Determinism:** context trimming, result ordering, and recorded call ordering must not depend on task completion timing.
- **Concurrency:** only tool bodies execute concurrently. Middleware preparation/finalization and shared transcript/context mutations remain ordered to avoid races in `run_state`, middleware events, provider messages, and `ContextManager`.
- **Performance:** unset settings add only constant-time branches. Configured concurrency may reduce wall-clock tool latency; context-budget estimation is linear in the size of the serialized model input.
- **Observability:** new hard stops use stable enum values and bounded metadata; allowlist denials use a stable reason; context compaction reports estimated tokens and removed-message counts.
- **Cancellation:** Python async cancellation is best-effort for non-cooperative work. A synchronous tool offloaded to a thread may continue outside the cancelled coroutine even though the runtime returns a timeout result.
- **Verification:** no new tests or verification scripts will be added. Implementation verification will use compilation plus the existing relevant unittest and agent-loop-settings script suites.

---

## 5. High-Level Design

The public-to-internal conversion remains the single configuration handoff. `AgentLoopSettings.to_runtime_config()` will pass all five fields into an expanded `AgentRuntimeConfig`; `BaseAgent` requires no wiring change because it already stores the public settings and passes the converted object into every constructed runtime.

`AgentRuntime` will enforce each setting at the narrowest authoritative boundary. The outer `arun()` boundary owns the wall-clock timeout. `_invoke_with_middleware()` owns model retries and final call-option context budgeting. Runtime tool catalog construction plus pre-execution checks own `allowed_tools`. A new ordered batch coordinator around the existing tool-call lifecycle owns `max_parallel_tool_calls` and prevents concurrent execution from racing mutations of middleware state, transcript messages, tool-call history, and context primitives.

```text
AgentLoopSettings
        |
        v
to_runtime_config()  -- carries every field --> AgentRuntimeConfig
        |
        v
AgentRuntime.arun() -- one absolute timeout
        |
        +--> model step -- retry ceiling --> context-budget check --> runner
        |
        +--> parsed tools -- allowlist/preflight --> bounded body execution
                                      |                |
                                      +---- ordered finalization ----+
```

The three settings that can terminate a run gain explicit stop reasons: timeout, retry exhaustion, and an irreducibly over-budget context. The concurrency and allowlist settings shape execution without ending the run by themselves. The existing loop-settings prompt block will continue to show only values with meaningful live `current/limit` counters; its documentation will explicitly say that the other settings are nevertheless enforced at runtime boundaries.

---

## 6. Detailed Design

### 6.1 Public-to-Runtime Settings Conversion

**File(s):** `vidbyte/agents/settings/loop.py`
**Type:** Modified

#### What it does

Updates the conversion method so every validated field needed by the direct runtime crosses into the internal configuration object.

#### Interface / API

```python
def to_runtime_config(self) -> AgentRuntimeConfig: ...
```

The returned object will include:

```python
AgentRuntimeConfig(
    max_iterations=self.max_iterations,
    max_tokens=self.max_tokens,
    max_tool_calls=self.max_tool_calls,
    compaction_trigger_tokens=self.compaction_trigger_tokens,
    compaction_target_tokens=self.compaction_target_tokens,
    max_parallel_tool_calls=self.max_parallel_tool_calls,
    max_retries=self.max_retries,
    timeout_seconds=self.timeout_seconds,
    context_window_budget=self.context_window_budget,
    allowed_tools=self.allowed_tools,
)
```

#### Logic / Algorithm

1. Preserve the lazy import that avoids a module cycle.
2. Pass all existing fields unchanged.
3. Append the five missing keyword arguments.
4. Update the method comment so it no longer claims only a subset is understood.

#### Edge Cases & Error Handling

- `None` remains `None` and disables the corresponding runtime behavior.
- `allowed_tools=()` remains an empty tuple rather than being normalized to `None`.
- Validation remains owned by `AgentLoopSettings._validate()` for the public path and by `AgentRuntimeConfig.__post_init__()` for direct internal construction.

---

### 6.2 Internal Runtime Contract and Stop Reasons

**File(s):** `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified

#### What it does

Expands the immutable runtime contract and adds machine-readable stop reasons for the new hard limits.

#### Interface / API

```python
class AgentStopReason(str, Enum):
    TIMEOUT = "timeout"
    MAX_RETRIES = "max_retries"
    CONTEXT_WINDOW_BUDGET = "context_window_budget"


@dataclass(frozen=True, slots=True)
class AgentRuntimeConfig:
    max_iterations: int | None = None
    max_tokens: int | None = None
    max_tool_calls: int | None = None
    compaction_trigger_tokens: int | None = None
    compaction_target_tokens: int | None = None
    max_parallel_tool_calls: int | None = None
    max_retries: int | None = None
    timeout_seconds: float | None = None
    context_window_budget: int | None = None
    allowed_tools: tuple[str, ...] | None = None
```

#### Logic / Algorithm

1. Append the fields to preserve the order of every existing dataclass field.
2. Extend positive-integer validation with `max_parallel_tool_calls`, `max_retries`, and `context_window_budget`.
3. Validate `timeout_seconds > 0.0` when set.
4. Leave `allowed_tools` unchanged because the public object already defines its tuple contract and an empty tuple has meaningful semantics.

#### Edge Cases & Error Handling

- Direct construction with zero or negative numeric limits raises `ValueError`, matching the existing internal contract.
- No persistence or serialization migration is required.
- `AgentRuntimeStats` remains unchanged; detailed new enforcement information is carried in result metadata.

---

### 6.3 Direct Runtime Enforcement

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Makes the five settings operational in the direct text runtime without moving policy back into `BaseAgent`.

#### Interface / API

The public `AgentRuntime.arun(...) -> AgentResult` signature remains unchanged. Internal helpers will be introduced or decomposed along these responsibilities:

```python
async def _arun_without_timeout(...) -> AgentResult: ...
async def _invoke_with_middleware(...) -> tuple[object | AgentResult, int]: ...
async def _apply_context_window_budget(...) -> tuple[dict[str, Any] | AgentResult, dict[str, Any]]: ...
async def _process_tool_calls(...) -> AgentResult | None: ...
async def _execute_tool_batch(...) -> tuple[tuple[ToolCallContext, ToolResult], ...]: ...
def _runtime_tools(self, tools: Tools) -> Tools: ...
def _tool_allowed(self, call: ToolCall) -> bool: ...
def _estimated_model_input_tokens(self, message: str, call_options: Mapping[str, Any]) -> int: ...
```

Exact private helper names may be adjusted during implementation to fit the existing class, but their responsibilities and behavior are fixed by this design.

#### Logic / Algorithm

1. **Timeout boundary:** move the current body of `arun()` into an unbounded private method. When `config.timeout_seconds` is set, execute that method inside one Python 3.11 async timeout context. Convert deadline expiry into a stopped result with `AgentStopReason.TIMEOUT` and `timeout_seconds` metadata. Do not reset the deadline for retries or algorithm sub-runs.
2. **Retry ceiling:** initialize a per-model-step retry counter in `_invoke_with_middleware()`. Preserve all current before-call, tracing, and error-hook behavior. Honor middleware aborts immediately. Honor middleware retries or configuration-driven retries only while the counter is below `max_retries`; otherwise return a `MAX_RETRIES` stopped result. With `max_retries=None`, preserve current middleware-only retry behavior and exception propagation.
3. **Context-budget enforcement:** after applying all `before_model_call` transforms and before starting the model span/incrementing the actual model-call count, estimate the serialized model input. If over budget, calculate the fixed-input cost, compact removable provider messages with the existing boundary-aware compaction engine using the remaining budget, and estimate again. If still over budget, return `CONTEXT_WINDOW_BUDGET` without invoking the runner. Record the configured budget, before/after estimates, and removed-message count in result metadata/run-state metadata.
4. **Allowed tool catalog:** construct the runtime-facing tool catalog from only allowed user tools when an allowlist is present, then always add internal tools. This filters both context tool descriptions and provider-native schemas. Keep the unfiltered user catalog available for normal SDK inspection.
5. **Allowed call defense:** before middleware or tool lookup, reject a non-internal tool call whose name is not in `allowed_tools`. Convert it with the existing denied-tool result shape and a stable `tool_not_allowed_by_loop_settings` reason. Count and append it like any other denied call.
6. **Bounded dispatch:** replace the direct `for call in tool_calls` execution loop with an ordered batch coordinator. Default batch size is one. A configured batch size is `max_parallel_tool_calls`, further capped by remaining `max_tool_calls` and by the first `isDone` barrier.
7. **Ordered lifecycle:** run before-tool policy/preflight in provider order. Execute only approved tool bodies concurrently for the current batch using `asyncio.gather`; `execute_tool_call()` already normalizes ordinary exceptions into result objects. Then run after-tool middleware, primitive binding, context recording, and provider-message appends sequentially in provider order.
8. **Stop handling:** if a before-tool decision aborts, finish already-dispatched prior work and return the abort without dispatching subsequent calls. If after-tool middleware aborts, return after ordered finalization of results already executed in that concurrent batch. If `isDone` is reached, return its result and never dispatch later calls from the same model response.
9. **Documentation in code:** rewrite `_render_loop_settings_block()` documentation to state that only live counters are rendered, while retries, timeout, context budget, allowlist, and concurrency are enforced elsewhere. The rendered block format remains backward compatible.

#### Edge Cases & Error Handling

- An empty allowlist exposes only internal runtime tools.
- A model may hallucinate a hidden tool; the defense-in-depth execution check denies it without revealing validation or permission behavior.
- A timeout while a model/tool coroutine is running triggers cancellation. Non-cooperative synchronous work may continue in its own thread; this limitation is documented.
- A context budget smaller than the fixed system prompt, current user message, tool schemas, or response-format payload fails closed before provider I/O.
- Context trimming never changes the user-provided `BaseAgentContext`; it only transforms the current model call options.
- Approximate token accounting can be conservative or permissive relative to a provider tokenizer, but it is deterministic across runs.
- Tool-call results complete out of order internally but are committed in provider order.
- If after-tool middleware aborts for one member of a concurrent batch, later members of that already-launched batch may have completed; their calls remain recorded rather than hidden.
- `max_tool_calls` is checked before batch launch to prevent concurrency from creating the current possible per-response overshoot.

---

### 6.4 Canonical Documentation

**File(s):** `skills/agentic-loop-settings/SKILL.md`, `README.md`
**Type:** Modified

#### What it does

Makes public guidance match the enforced implementation.

#### Interface / API

N/A - documentation-only changes; no additional Python interface is introduced.

#### Logic / Algorithm

1. Move the five settings from the skill guide's reserved table into enforced runtime behavior.
2. Define `max_retries` as model-call retries after the initial attempt and explicitly state that tool-body retries are not automatic.
3. Document the three new stop reasons and the allowlist denial behavior.
4. Document deterministic approximate context budgeting and provider-order-preserving bounded tool execution.
5. Replace the future-roadmap bullets for these fields with current behavior and remaining limitations.
6. Update the README's direct-runtime safeguard paragraph and example to show `AgentLoopSettings` as the surface for the advanced limits.
7. Preserve the explanation that only live numeric counters appear in the injected loop-settings block.

#### Edge Cases & Error Handling

- Documentation must not claim exact tokenizer enforcement.
- Documentation must not imply the settings apply to non-direct-text runtimes.
- Documentation must state the internal-tool exemption for `allowed_tools`.

---

## 7. Data Model Changes

### 7.1 `AgentRuntimeConfig`

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class AgentRuntimeConfig:
    max_iterations: int | None = None
    max_tokens: int | None = None
    max_tool_calls: int | None = None
    compaction_trigger_tokens: int | None = None
    compaction_target_tokens: int | None = None
    max_parallel_tool_calls: int | None = None
    max_retries: int | None = None
    timeout_seconds: float | None = None
    context_window_budget: int | None = None
    allowed_tools: tuple[str, ...] | None = None
```

**Migration strategy:**

- Forward migration: additive in-memory fields with `None` defaults; `AgentLoopSettings.to_runtime_config()` begins populating them.
- Rollback plan: revert the field additions and conversion/enforcement code. No stored data requires rollback.

### 7.2 `AgentStopReason`

**Change type:** Modified

```python
class AgentStopReason(str, Enum):
    TIMEOUT = "timeout"
    MAX_RETRIES = "max_retries"
    CONTEXT_WINDOW_BUDGET = "context_window_budget"
```

**Migration strategy:**

- Forward migration: additive enum values surfaced only when the corresponding new enforcement path triggers.
- Rollback plan: revert the values with the runtime enforcement code; no persistence is involved.

---

## 8. API Changes

N/A - no HTTP endpoints are affected. The existing Python SDK API becomes functional rather than gaining new constructor parameters:

- `AgentLoopSettings(max_parallel_tool_calls=...)` now bounds tool-body concurrency.
- `AgentLoopSettings(max_retries=...)` now bounds and enables model-call retries.
- `AgentLoopSettings(timeout_seconds=...)` now applies a whole-run deadline.
- `AgentLoopSettings(context_window_budget=...)` now applies a deterministic approximate hard input budget.
- `AgentLoopSettings(allowed_tools=...)` now filters and enforces user-tool access.
- `AgentResult.metadata["stop_reason"]` may now be `"timeout"`, `"max_retries"`, or `"context_window_budget"`.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/runtime-loop-settings-enforcement.md` | Approval-gated source of truth for the fix |
| MODIFY | `vidbyte/agents/settings/loop.py` | Carry all five public settings into runtime config |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add runtime fields, validation, and hard-stop enum values |
| MODIFY | `vidbyte/agents/runtime.py` | Enforce timeout, retries, bounded tool concurrency, context budget, and allowed tools |
| MODIFY | `skills/agentic-loop-settings/SKILL.md` | Replace reserved behavior with accurate enforced semantics |
| MODIFY | `README.md` | Document the operational advanced loop settings |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library `asyncio` | Python 3.11+ | Whole-run timeout and bounded concurrent tool execution | Low; already used throughout the SDK |
| `vidbyte.middleware.compaction` | Internal | Provider-boundary-aware deterministic history trimming | Medium; runtime imports an existing middleware implementation layer |
| `vidbyte.tools.Tools` | Internal | Build the runtime-visible allowlisted tool catalog | Low; existing runtime catalog abstraction |
| External services | N/A | No network service is added; providers are invoked through existing runner handles | None |

---

## 11. Rollout & Deployment

- No feature flag is required. Each behavior is opt-in through a setting that previously had no runtime effect.
- The change is behaviorally breaking only for callers that already set one of the five fields while relying on it being ignored. That reliance is contrary to the field names and documentation intent, but the release notes should call it out.
- Deployment is a normal Python package release; no service ordering or data migration is needed.
- Before the draft PR is opened, run `python -m compileall vidbyte`, the existing direct-runtime/middleware unittest modules, and `python scripts/test-agent-loop-settings.py`. No new test or verification files will be created.
- Rollback is a single PR revert. All new config fields default to `None`, and there are no persisted artifacts.
- The implementation branch will be created from updated `main` in an isolated worktree only after explicit approval. If `main` is dirty, pull fails, or worktree creation fails, implementation stops and reports the blocker.

---

## 12. Open Questions

- [x] Confirmed: `max_retries` applies to model invocations only in this fix. The existing retry hook and original roadmap target `_invoke_with_middleware()`, while automatic tool retries can duplicate non-idempotent side effects.
- [x] Confirmed: deterministic approximate input-token enforcement is acceptable for `context_window_budget`. Exact provider tokenization would require new provider/tokenizer contracts and dependencies; the implementation reuses the SDK's existing four-characters-per-token compaction convention.
- [x] Confirmed: internal `isDone` remains exempt from `allowed_tools`. This matches the existing `ToolPolicyMiddleware` security contract and prevents an empty allowlist from creating a non-terminating loop.

---

## 13. Alternatives Considered

### Alternative 1: Auto-Install Existing Built-In Middleware for Every Setting

- What: Convert settings into `ModelRetryMiddleware`, `RuntimeLimitMiddleware`, `ToolPolicyMiddleware`, and `MessageHistoryCompactionMiddleware` instances.
- Why rejected: boundary-only elapsed checks are not a hard timeout, user middleware ordering can bypass a retry ceiling, context compaction would not account for fixed input, and middleware alone cannot implement provider-order-preserving concurrent tool dispatch. Existing middleware remains reusable for explicit user policy.

### Alternative 2: Reject More Than `max_parallel_tool_calls` Calls Per Model Response

- What: Treat the field as a per-response call-count limit and deny calls beyond it.
- Why rejected: the canonical contract defines a concurrency ceiling, not a total-call ceiling. The separate `max_tool_calls` field already owns total invocation count.

### Alternative 3: Keep Tool Execution Sequential and Declare the Concurrency Limit Vacuously Enforced

- What: Carry the field into runtime config but make no execution change because sequential execution never exceeds a positive concurrency ceiling.
- Why rejected: the setting would still have no observable effect, contradicting its documented purpose and the request for runtime limits that are actually enforced.

### Alternative 4: Retry Model and Tool Failures Uniformly

- What: Re-run failed tool calls using the same `max_retries` budget as model calls.
- Why rejected: tools can perform partial external side effects before failing, and the current tool contract does not declare idempotency or retryability. Model-only retries are safe within the existing retry architecture.

### Alternative 5: Pass `context_window_budget` to the Provider as Output `max_tokens`

- What: Reuse provider generation limits rather than estimate and compact input context.
- Why rejected: the setting explicitly governs context-window input, while provider `max_tokens` generally governs generated output. Conflating them would not cap history, tool results, primitives, schemas, or system text.
