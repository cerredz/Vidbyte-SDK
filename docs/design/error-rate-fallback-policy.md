# Design Doc: Elevated Error-Rate (Within-Run) Fallback Policy

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-19
**Last Updated:** 2026-08-19

---

## 1. Overview

This adds `ErrorRatePolicy`, a third per-hop fallback policy stacked directly on top of PR #339 (`feat/agent-fallback-policies`, currently open, unmerged). It answers a question the existing policies do not: what about a provider that is not down, just flaky — say one call in five 500s or times out, where retry-then-fallback handles each failure individually and the retry usually succeeds, so every call *looks* fine but the run quietly pays the retry tax on every single call for the rest of the loop? `ErrorRatePolicy` tracks cumulative attempts and failures per chain index across the run and, once a model's failure ratio crosses its per-hop ceiling, skips that model proactively on the next iteration instead of making it earn another retry cycle first. The mechanism is structurally like `CostBudgetPolicy`'s top-of-iteration checkpoint, but the signal is new: raw attempt-level accounting recorded at the model-call site, because the failures this policy exists to detect (the ones a retry recovers) are invisible everywhere in the runtime today.

---

## 2. Goals & Non-Goals

### Goals

- Add `ErrorRatePolicy(max_error_ratio_by_hop: Sequence[float], *, min_attempts: int = 3)` to `vidbyte/agents/fallback/policies.py`, exposing `hop_values()` (for the existing generic validation) and `error_ratio_for(index)` (mirroring `budget_for`/`deadline_for`).
- Add `AgentFallback.advance_after_error_rate(index, *, attempts, failures)` in `vidbyte/agents/fallback/chain.py`, mirroring `advance_after_success`'s guard shape.
- Record cumulative (attempts, failures) per chain index on the `AgentRuntime` instance — the only mutable new state — at the model-call site inside `_invoke_with_middleware`, where every invoke attempt (including retries) is visible.
- Wire a new `AgentRuntime._error_rate_fallback_transition(...)` into the same top-of-iteration checkpoint `_cost_fallback_transition` already occupies in `arun`, sequential after the cost check.
- Reuse the existing `policy_attempt_record`/`result_metadata`/`_publish_fallback_metadata`/`_record_fallback_span` machinery verbatim, with reason string `"error_rate_exceeded"` — no new metadata shape, no new span kind.
- Ship as a stacked commit on `feat/agent-fallback-policies`, exported from the same two `__init__.py` files and documented in the same README section, with a base branch of `feat/agent-fallback-policies` (not `main`).

### Non-Goals

- **Changing `AgentFallbackSettings` validation.** `_validate_policy_hop_values` already duck-types on `hop_values()` and validates length plus positive-non-bool numbers — confirmed by reading the actual (unmerged) implementation. `ErrorRatePolicy` needs zero new validation code in `settings.py`.
- **Per-hop `min_attempts`.** The warm-up floor is a single policy-level scalar, not a second per-hop array. A per-hop compound `(min_attempts, ratio)` tuple would break the generic `hop_values()` element validation (plain positive numbers required). No stated need for per-hop floors.
- **Counting non-provider failures.** A failure is counted only when `self.fallback.is_model_error(exc)` — the chain's own definition of a provider-level failure. Cancellation (`CancelledError` is a `BaseException`, not an `Exception`, so it never enters the counting except block at all) and tool/configuration errors stay out of the ratio.
- **Cross-run persistence.** This is a within-run policy by title; state outlives no run. Cross-run failure state is the future Rate-Limit Circuit-Breaker (PR #339's catalog item 3) and is deliberately not built here.
- **Resetting the counter per hop.** Counts are keyed by chain index and the chain is monotonic — once the run leaves an index it never returns — so per-index cumulative counts need zero reset sites. A "tokens spent since arriving at this hop" style reset would require tracking state this design does not need.
- **Wiring into `BaseAgent._run_non_text_runner`.** Same exclusion PR #339 already made for `CostBudgetPolicy` — that path has no per-iteration checkpoint loop to hang a proactive check off of.
- **New test files**, per the `/design-doc-no-tests` workflow. The existing suite must stay green.
- **Any of the other brainstormed conditions** (output-quality, tool-call reliability, rate-limit circuit breaker, confidence escalation — PR #339 Section 14). Not built here.

---

## 3. Background & Context

### Why now

This is a direct continuation of the fallback-policy brainstorm that produced PR #339's Section 14 catalog and the user's explicit request: give the developer the ability to declare that when a provider's errors rise above a certain percentage across a run, a fallback model is used instead of paying the retry tax for the rest of the loop. The framing was confirmed in the design conversation: cumulative per model across the run, not per-call; checked at the same top-of-loop point as the cost policy; a policy that fires even though every individual failure technically recovered.

### Current state (verified in this repo, this session, against the actual unmerged branch — not the PR description)

- PR #339 (`feat/agent-fallback-policies`, base `main`, 5 commits, unmerged) moved the fallback subsystem into `vidbyte/agents/fallback/` (`chain.py`, `settings.py`, `policies.py`, `__init__.py`) and added `LatencyPolicy` and `CostBudgetPolicy`.
- `vidbyte/agents/fallback/policies.py` (on the branch) defines both policies as plain classes exposing `hop_values() -> tuple[float, ...]` plus one policy-specific getter (`deadline_for`/`budget_for`) returning the value for a chain index or `None` past the array. Neither validates its own array (constructed before the chain length is known); all array validation is centralized in `AgentFallbackSettings._validate_policy_hop_values`, which duck-types on `hop_values()` and requires `len(values) == len(self.models)` and positive non-bool numbers per element — read directly from the actual (unmerged) file, this needs zero changes for a third policy class.
- `vidbyte/agents/fallback/chain.py`'s `AgentFallback` folds over `self.policies` via `_first_policy_value(self, index, attr)` (first non-`None` result wins) — the pattern `error_ratio_for` would mirror. The chain is immutable and agent-owned (`BaseAgent.__init__` builds it once via `AgentFallback.from_spec`); the only mutable fallback state is loop-local (`fallback_index`, `fallback_attempts`, `fallback_errors` in `AgentRuntime.arun`), which is what keeps the chain safe under concurrent `arun_sequentially`/`asyncio.gather` use. **Mutable counters therefore must not live on the chain.**
- `AgentRuntime` is constructed fresh per run by `BaseAgent._runtime()` (verified in `vidbyte/agents/base.py`: `return runtime_cls(...)` inside `_runtime()`, called per `arun`/`generate_reply`), and receives `fallback=self.fallback` (the shared chain) and `usage_tracker=self._usage_tracker` (agent-owned but `reset()` per run). Instance state on `AgentRuntime` is therefore per-run state — the safe home for the new tally.
- `AgentRuntime._invoke_with_middleware` (`runtime.py`, lines 687-782 on the branch) is the only place every invoke attempt is visible: a `while True` retry loop where `before_model_call` middleware can decide RETRY. Success returns at line 743; a provider error enters `except Exception as exc:` (line 744), gets offered to `on_model_error` middleware (which may RETRY → `continue`), and only a non-retryable raise escapes to the outer loop's `except BaseException` and `_fallback_transition`. **Failures a retry recovers never reach `_fallback_transition` — they are recorded nowhere today.** This is the gap the policy exists to close and the reason the tally must be recorded inside `_invoke_with_middleware`, not in the error path.
- The latency wrap added by PR #339 already threads `timeout_seconds=self.fallback.deadline_for(fallback_index)` into `_invoke_with_middleware` from the call site at `runtime.py:360` — the precedent for passing fallback-chain state (`fallback_index`) into this function. `asyncio.TimeoutError` is `TimeoutError` (aliased since 3.11), which is in `DEFAULT_FALLBACK_ERRORS` and so counts as a model error — a recovered latency timeout counts toward the error ratio, which is desired (timeouts are part of the stated flaky profile).
- The top-of-iteration checkpoint (`runtime.py:270-286`) is a single `if self.fallback is not None and iteration_count > 0:` block that calls `_cost_fallback_transition` and, on a non-`None` result, reassigns `handle`, `provider`, `tool_schemas`, `messages`, `fallback_index`, and calls `_publish_fallback_metadata`. This is the exact insertion point for a second, sequential check. The token-budget design doc (`docs/design/token-budget-fallback-policy.md`, unmerged design doc on `main`) establishes the same insertion pattern for a second proactive check; this PR stacks on #339 directly and will trivially conflict with that doc's future implementation in the checkpoint block, `policies.py`, exports, and README — both blocks are purely additive, so the conflict is mechanical.
- `vidbyte/agents/fallback/settings.py` (branch) validates policies generically; `AgentFallbackSettings.__init__` accepts `policies: Sequence[object] = ()` and `to_fallback()` passes it through. No changes needed.
- `vidbyte/agents/__init__.py` and `vidbyte/agents/fallback/__init__.py` (branch) export `LatencyPolicy`/`CostBudgetPolicy` alphabetically in `__all__`; `ErrorRatePolicy` slots in between `DEFAULT_FALLBACK_ERRORS` and `FallbackTransform`.
- `vidbyte/agents/README.md` (branch) has a "Fallback Policies" section (added in commit 5ffb860) with one bullet per policy and a combined example; the "Key Modules" entry for `policies.py` names both classes.
- Field guide (`field-guide/vidbyte-sdk/`): `runtime-boundaries.md` requires model usage accounting to stay agent-owned via the `UsageTracker` — this policy adds no second usage-recording path (the tally is failure accounting, not usage accounting, and reads no usage fields), and `local-ci-verification.md` governs how CI is run from a worktree (Section 14).

### Baseline

The branch tip `dcc4dbf` (PR #339 head) is the base this change is verified against: existing suite green on `main` at `08e71ef` (**1555 passed, 1 skipped**), plus the #339 branch's own CI run. This change must keep that result exactly, plus green `scripts/run_ci.py`.

---

## 4. Requirements

### Functional Requirements

1. `ErrorRatePolicy(max_error_ratio_by_hop: Sequence[float], *, min_attempts: int = 3)` stores one ratio ceiling per transition plus a global warm-up floor, exactly like `LatencyPolicy`/`CostBudgetPolicy` store their per-hop values.
2. `ErrorRatePolicy.hop_values()` returns the raw per-hop values for `AgentFallbackSettings`' existing length/value validation — no new validation code in `settings.py`.
3. `ErrorRatePolicy.error_ratio_for(index)` returns the ceiling in effect at that chain index, or `None` past the configured array.
4. `ErrorRatePolicy.__init__` raises `ConfigurationError` eagerly for a non-positive or out-of-range ratio (must be in `(0, 1]`) and for `min_attempts < 1` — the ratio domain is policy-specific and the generic settings validation cannot know it.
5. `AgentFallback.advance_after_error_rate(index, *, attempts, failures)` returns the next chain index when `failures > 0`, the current index is not the last in the chain, `attempts >= min_attempts` for the first policy exposing `error_ratio_for` at that index, and `failures / attempts >= ceiling`; otherwise `None`.
6. `AgentRuntime` records every invoke attempt against the current chain index in a per-run tally: success on a returned call, failure when the call raised and `self.fallback.is_model_error(exc)`. Recording is skipped entirely when no chain policy exposes `error_ratio_for` (precomputed `_error_rate_active` flag).
7. `AgentRuntime._error_rate_fallback_transition(...)` checks the tally once per outer-loop iteration, after the first model call (`iteration_count > 0` guard, same as cost), reading the current index's `(attempts, failures)` and advancing through `advance_after_error_rate` when the ceiling has been crossed.
8. A run whose current model's ratio has crossed its ceiling advances to the next model on the *next* iteration boundary — not mid-call — exactly like `CostBudgetPolicy` (a high ratio is not a call failure; the in-flight call is allowed to finish).
9. The switch is recorded through the existing `AgentResult.metadata["fallback"]` shape, with `error_type: "error_rate_exceeded"`, and an `agent.fallback` span.
10. An agent with no `ErrorRatePolicy` configured (the overwhelming majority) sees zero behavior change — no tally recording (flag-off), and `advance_after_error_rate` returns `None` over an empty/irrelevant policy tuple.

### Non-Functional Requirements

- **Performance:** One dict get/set per invoke attempt when the policy is configured; zero when it isn't (`_error_rate_active` precomputed in `__init__`). One fold and one division per iteration at the checkpoint. No new I/O, no new provider calls.
- **Concurrency:** The tally lives on `AgentRuntime`, constructed fresh per run by `BaseAgent._runtime()`; concurrent `arun_sequentially`/`asyncio.gather` on a shared agent each get their own instance, and the shared `AgentFallback` chain stays immutable. No new shared mutable state.
- **Observability:** Reuses the existing `agent.fallback` span and `AgentResult.metadata["fallback"]` shape — an error-rate switch is visible in exactly the same place a cost- or error-triggered one is, distinguished only by `error_type`.
- **Reliability:** Never raises on its own — `advance_after_error_rate` degrades to `None` when `failures == 0`, when the chain has nowhere left to go, or when no policy exposes a ceiling at the current index. A `failures > 0` precondition guarantees `attempts >= 1`, so the ratio division can never divide by zero.
- **Backward compatibility:** Purely additive. No existing public signature changes; the one new constructor parameter path this touches (`policies=[ErrorRatePolicy(...)]`) already exists as of PR #339 and already accepts an arbitrary sequence.

---

## 5. High-Level Design

`ErrorRatePolicy` is data (an immutable per-hop ceiling array plus a warm-up floor); it does not itself watch anything. Watching happens at two places in `AgentRuntime`: **counting** at the model-call site inside `_invoke_with_middleware` (the only place every attempt, retried or not, is visible), and **checking** once per outer-loop iteration at the same checkpoint `CostBudgetPolicy` established. The count is a per-run tally keyed by chain index; the check asks the chain "given the attempts and failures on the current model so far, should we already be on a different model?" — and the chain answers by folding over its policies exactly as it does for `budget_for`.

```
[arun outer loop, iteration N]
        |
        v
  _invoke_with_middleware(handle, ..., fallback_index=i, timeout_seconds=deadline_for(i))
        |   every attempt recorded against index i:
        |     invoke returns          -> tally[i].attempts += 1
        |     invoke raises, is_model_error -> tally[i].attempts += 1, tally[i].failures += 1
        |   (retried failures are counted; the RETRY decision does not change the count)
        |
        v
  (top-of-next-iteration checkpoint, iteration_count > 0)
        |
        +--> _cost_fallback_transition(index=fallback_index)          [existing]
        |         reads usage_tracker.rollup().cost_usd
        |
        +--> _error_rate_fallback_transition(index=fallback_index)    <-- NEW
        |         reads tally[fallback_index] = (attempts, failures)
        |         -> AgentFallback.advance_after_error_rate -> maybe advance fallback_index
        |
        v
  next model call, at whichever fallback_index survived both checks
```

The two checks are independent and sequential, not merged: the error-rate check runs against whatever `fallback_index` the cost check left behind, so a single iteration that simultaneously blows a cost ceiling and an error-rate ceiling can cascade the chain forward by more than one hop in one iteration boundary — the same documented cascade semantics the token-budget doc establishes for a second proactive check. The error-rate advance uses the identical `transform` → reassign → `policy_attempt_record` → span → metadata sequence the error path and the cost path both use; the only genuinely new code is the tally recording (one method, two call sites) and the ratio decision (one chain method).

---

## 6. Detailed Design

### 6.1 `vidbyte/agents/fallback/policies.py`

**File(s):** `vidbyte/agents/fallback/policies.py`
**Type:** Modified (adds one class to the file PR #339 created)

#### What it does

Adds `ErrorRatePolicy`, the third per-hop trigger condition, alongside `LatencyPolicy` and `CostBudgetPolicy`.

#### Interface / API

```python
class ErrorRatePolicy:
    """Per-hop cumulative error-ratio ceiling; a model whose share of failed
    calls crosses hop i's ceiling is skipped on the next iteration.

    max_error_ratio_by_hop must have exactly one entry per transition the chain can
    take -- len(models) as declared on AgentFallbackSettings, not len(models) + 1.
    Index i is the ceiling in effect while chain index i is in flight. The last
    model in the chain never gets one: there's nowhere else to go.

    The ratio counts every invoke attempt on the model since the run reached it,
    including attempts a retry recovered -- those recovered failures are exactly
    the "retry tax" this policy exists to detect. A provider failing one call in
    five with one retry each shows 2 failures in 4 attempts (0.5), not 0.2: read
    the ceiling as "how much retry tax am I willing to pay", not the provider's
    raw error rate. min_attempts is the number of attempts required before the
    ratio is trusted at all.
    """

    def __init__(self, max_error_ratio_by_hop: Sequence[float], *, min_attempts: int = 3) -> None:
        # Stores one ratio ceiling per transition plus a global warm-up floor, validated eagerly.
        ...

    def hop_values(self) -> tuple[float, ...]:
        # Returns the raw per-hop values for AgentFallbackSettings' length/value validation.
        return self.max_error_ratio_by_hop

    def error_ratio_for(self, index: int) -> float | None:
        # Returns the ceiling in effect while chain index `index` is in flight, or None past the array.
        return self.max_error_ratio_by_hop[index] if index < len(self.max_error_ratio_by_hop) else None

    def __repr__(self) -> str:
        # Returns a compact developer-readable string of the configured ceilings.
        return f"ErrorRatePolicy({list(self.max_error_ratio_by_hop)!r}, min_attempts={self.min_attempts})"
```

Also update the module docstring (Context Protocol Header) to list all three policies, and add `"ErrorRatePolicy"` to the file's `__all__` (alphabetical: `CostBudgetPolicy`, `ErrorRatePolicy`, `LatencyPolicy`).

#### Logic / Algorithm

`__init__` validates before storing: `min_attempts < 1` raises `ConfigurationError`; each ratio that is a `bool`, a non-number, or outside `(0, 1]` raises `ConfigurationError` naming the position and value. `hop_values()` and `error_ratio_for` are identical shapes to the sibling policies. No chain-length validation here — it cannot know the chain yet; `AgentFallbackSettings` does that via `hop_values()`.

#### Edge Cases & Error Handling

- Ratio `1.0` is accepted (meaningful: fire only at 100% failure) but anything above `1.0` is rejected — it could never fire and would silently do nothing, the exact config-bug class this codebase validates eagerly elsewhere.
- This is the first policy that validates in its own constructor (siblings defer everything to `AgentFallbackSettings`). Deliberate, documented deviation: the ratio domain is policy-specific knowledge the generic settings validation cannot have, and unlike chain length (unknowable at policy construction), the ratio domain is knowable.
- `min_attempts` participates in `hop_values()`-based validation only indirectly — it is validated here, since `_validate_policy_hop_values` only sees `hop_values()`.

---

### 6.2 `vidbyte/agents/fallback/chain.py`

**File(s):** `vidbyte/agents/fallback/chain.py`
**Type:** Modified

#### What it does

Adds the error-rate analogue of `advance_after_success`.

#### Interface / API

```python
class AgentFallback:
    # existing (from PR #339), unchanged:
    def deadline_for(self, index: int) -> float | None: ...
    def budget_for(self, index: int) -> float | None: ...
    def advance_after_success(self, index: int, *, cost_usd: float | None) -> int | None: ...

    # new:
    def advance_after_error_rate(self, index: int, *, attempts: int, failures: int) -> int | None: ...
```

#### Logic / Algorithm

1. Guard shape mirrors `advance_after_success`: return `None` immediately when `index + 1 >= len(self.models)` (nowhere left to go) or `failures <= 0` (nothing bad has happened — also guarantees `attempts >= 1`, so no division by zero).
2. Fold over `self.policies` with `getattr(policy, "error_ratio_for", None)`; skip policies that don't expose it; skip a hop where the getter returns `None`; the **first policy exposing a non-`None` ceiling at this index decides** — if `attempts >= getattr(policy, "min_attempts", 0)` and `failures / attempts >= ceiling`, return `index + 1`, else return `None`. This mirrors `_first_policy_value`'s first-non-`None`-wins semantics.
3. This is a bespoke loop, not the shared `_first_policy_value` fold, because the decision needs two values from one policy (ceiling + floor) — the first check in the file that does. No changes to any existing method.

#### Edge Cases & Error Handling

- Called on the last chain index: returns `None` — a high ratio on the terminal model is not actionable; the run continues on that model rather than raising, matching `advance_after_success`'s "a successful call is never itself a failure worth aborting a run over".
- Two policies both exposing `error_ratio_for` for the same hop (e.g., two stacked `ErrorRatePolicy` instances): first in declaration order decides, exactly like duplicate `LatencyPolicy`/`CostBudgetPolicy` instances — not validated as an error, same reasoning as PR #339.
- No policy exposes `error_ratio_for`: loop never matches, returns `None` — zero behavior change for unconfigured runs.
- `attempts=0` cannot reach the ratio computation (`failures <= 0` guard fires first, since `failures <= attempts` by construction).

---

### 6.3 `vidbyte/agents/runtime.py`

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does (changes only)

Adds the per-run attempt tally, records it at the model-call site, and adds the second proactive check to the existing top-of-iteration checkpoint.

#### Interface / API

```python
# in AgentRuntime.__init__ (after self.fallback = fallback):
self._error_rate_tally: dict[int, tuple[int, int]] = {}
self._error_rate_active = bool(fallback) and any(callable(getattr(policy, "error_ratio_for", None)) for policy in fallback.policies)

def _record_error_rate_attempt(self, index: int, failed: bool) -> None:
    # Counts one invoke attempt on the chain index, so the ratio is cumulative per model since the run reached it.
    ...

async def _invoke_with_middleware(self, handle: RunnerHandle, message: str, call_options: Mapping[str, Any], *, context: BaseAgentContext, iteration_count: int, model_call_count: int, call_contexts: Sequence[ToolCallContext], tokens_used: int | None, started_at: float, metadata: Mapping[str, Any], run_state: dict[type, Any] | None = None, trace_context: SpanContext | None = None, compaction_count: int = 0, timeout_seconds: float | None = None, fallback_index: int = 0) -> tuple[object | AgentResult, int, int]: ...

def _error_rate_fallback_transition(self, *, index: int, handle: RunnerHandle, provider: str, messages: list[dict[str, Any]], attempts: list[dict[str, str]], parent_span: SpanContext | None) -> "FallbackTransform | None": ...
```

#### Logic / Algorithm

1. `__init__` gains the two lines above. `_error_rate_active` is precomputed so unconfigured runs pay one boolean check per attempt, not a policy fold.
2. In `_invoke_with_middleware`, the recording sites (lines 736-782 on the branch):
   - Success — immediately after the invoke returns (inside the existing `try`, before `extract_text`): `if self._error_rate_active: self._record_error_rate_attempt(fallback_index, failed=False)`.
   - Failure — at the top of the existing `except Exception as exc:` block (before `on_model_error`, so the middleware RETRY decision cannot skip the count): `if self._error_rate_active and self.fallback is not None and self.fallback.is_model_error(exc): self._record_error_rate_attempt(fallback_index, failed=True)`.
   - `except BaseException` (cancellation path) is untouched — `CancelledError` never enters the counting block.
3. The call site in `arun` (line 360) gains `fallback_index=fallback_index` next to the existing `timeout_seconds=self.fallback.deadline_for(fallback_index) ...`.
4. In `arun`'s checkpoint block (lines 270-286), after the cost-transition block, a second sequential block:
   ```python
   error_rate_transition = self._error_rate_fallback_transition(
       index=fallback_index,
       handle=handle,
       provider=provider,
       messages=messages,
       attempts=fallback_attempts,
       parent_span=trace_context,
   )
   if error_rate_transition is not None:
       handle, provider = error_rate_transition.handle, error_rate_transition.provider
       tool_schemas, messages = error_rate_transition.tool_schemas, error_rate_transition.messages
       fallback_index = error_rate_transition.index
       self._publish_fallback_metadata(
           run_state,
           self.fallback.result_metadata(fallback_attempts, context_reset=error_rate_transition.context_reset),
       )
   ```
   The block deliberately reads `fallback_index` after the cost block may have reassigned it — cascade semantics, see Section 5.
5. `_error_rate_fallback_transition` mirrors `_cost_fallback_transition`'s body exactly:
   ```python
   def _error_rate_fallback_transition(self, *, index: int, handle: RunnerHandle, provider: str, messages: list[dict[str, Any]], attempts: list[dict[str, str]], parent_span: SpanContext | None) -> "FallbackTransform | None":
       # Returns rebuilt state when an error-rate policy elects to skip the current model, or None to keep it.
       counted_attempts, failures = self._error_rate_tally.get(index, (0, 0))
       next_index = self.fallback.advance_after_error_rate(index, attempts=counted_attempts, failures=failures)
       if next_index is None:
           return None
       record = self.fallback.policy_attempt_record(index, next_index, "error_rate_exceeded")
       attempts.append(record)
       transition = self.fallback.transform(handle, provider, self.tools, messages, next_index)
       self._record_fallback_span(record, transition.context_reset, parent_span)
       return transition
   ```

#### Edge Cases & Error Handling

- `self.fallback is None`: `_error_rate_active` is `False`, so the recording sites skip and the checkpoint block is already inside `if self.fallback is not None` — zero behavior change, matching today.
- Both `_cost_fallback_transition` and `_error_rate_fallback_transition` return non-`None` in the same iteration: handled by sequential reassignment (Section 5) — a documented cascade, not a bug.
- Tally entries for an index the run left are never read again (the chain never returns to an index), so no reset is needed anywhere — the design decision that removes the entire "forgot to reset on transition" bug class.
- A `wait_for` timeout that a retry recovers: recorded as a failure (it is a `TimeoutError` model error) — intended; timeouts are part of the flaky profile this policy detects.
- Middleware aborts (`ABORT_RUN` decisions) and `before_model_call` non-CONTINUE decisions return without invoking the model — no attempt recorded, consistent with "attempts measure provider calls made".

---

### 6.4 `vidbyte/agents/fallback/__init__.py`, `vidbyte/agents/__init__.py`

**File(s):** both
**Type:** Modified

#### What it does

Exports `ErrorRatePolicy` from the same two places the existing policies are exported from.

#### Logic / Algorithm

- `vidbyte/agents/fallback/__init__.py`: add `ErrorRatePolicy` to the `from vidbyte.agents.fallback.policies import ...` line and to `__all__` (between `DEFAULT_FALLBACK_ERRORS` and `FallbackTransform`, alphabetical); update the module docstring's Architecture bullet to name all three policies.
- `vidbyte/agents/__init__.py`: add `ErrorRatePolicy` to the `from vidbyte.agents.fallback import ...` line and to `__all__` (between `CostBudgetPolicy` and `FallbackModel`, alphabetical); update the Context Protocol Header's Architecture bullet naming the policy classes.

---

### 6.5 `vidbyte/agents/README.md`

**File(s):** `vidbyte/agents/README.md`
**Type:** Modified

#### What it does

Extends the "Fallback Policies" section PR #339 added, with a third bullet and an updated example.

#### Logic / Algorithm

- Add `ErrorRatePolicy` to the example's `policies=[...]` list and import line.
- Add one bullet explaining the cumulative attempts/failures ratio, the retry-tax reading of the ceiling (2/4 = 0.5 for one-in-five flaky with one retry, not 0.2), the `min_attempts` warm-up floor, and the same checkpoint as `CostBudgetPolicy`.
- Update the "Key Modules" list entry for `policies.py` to name all three classes.

---

## 7. Data Model Changes

N/A — no database, no persisted schema. `AgentFallbackSettings` and `AgentFallback` are in-process Python objects; the new tally is a per-run `dict[int, tuple[int, int]]` on `AgentRuntime` that lives and dies with the run. `RunState`/`export_state`/`restore` do not serialize the fallback chain today (a pre-existing, unrelated non-goal from the original fallback design), and this change does not alter that.

---

## 8. API Changes

N/A — no HTTP endpoints. The only new public names are `ErrorRatePolicy` and its two methods (`hop_values`, `error_ratio_for`), fully specified in Section 6.1. `AgentFallback.advance_after_error_rate` is public in the sense of the class's other methods but internal to the SDK's runtime use.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/agents/fallback/policies.py` | Add `ErrorRatePolicy`; update module docstring and `__all__` |
| MODIFY | `vidbyte/agents/fallback/chain.py` | Add `advance_after_error_rate` |
| MODIFY | `vidbyte/agents/runtime.py` | Add tally + `_error_rate_active` to `__init__`; `_record_error_rate_attempt`; recording at the invoke site; `_error_rate_fallback_transition`; checkpoint block; `fallback_index` param on `_invoke_with_middleware` |
| MODIFY | `vidbyte/agents/fallback/__init__.py` | Export `ErrorRatePolicy`; update docstring |
| MODIFY | `vidbyte/agents/__init__.py` | Export `ErrorRatePolicy`; update docstring |
| MODIFY | `vidbyte/agents/README.md` | Document `ErrorRatePolicy` |

No files under `tests/` are created or modified, per the `/design-doc-no-tests` workflow. `AgentFallbackSettings` (`vidbyte/agents/fallback/settings.py`) is deliberately **not** in this manifest — its validation is already fully generic (Section 3, Section 6.1).

---

## 10. Dependencies & External Services

N/A — no new dependencies. Reuses the existing `AgentFallback`/`AgentFallbackSettings` machinery and `DEFAULT_FALLBACK_ERRORS` semantics already in the fallback package.

---

## 11. Rollout & Deployment

- No feature flag: `ErrorRatePolicy` is opt-in by construction, same as `LatencyPolicy`/`CostBudgetPolicy` — an agent that doesn't declare it sees zero behavior change (Section 6.3's `_error_rate_active` flag-off).
- **Base branch is `feat/agent-fallback-policies` (PR #339), not `main`.** This PR is a stack: it cannot merge before #339 does, and its diff will only show the error-rate-specific changes as long as #339 remains unmerged. If #339 merges first, this branch should be rebased onto `main` before this PR is finalized.
- **Interaction with the token-budget design doc** (`docs/design/token-budget-fallback-policy.md`, on `main`, not yet implemented): both add a sequential check to the same checkpoint block and both touch `policies.py`, exports, and README. Recommended stack order: #339 → token-budget → error-rate, or error-rate → token-budget; either order works because each block is purely additive, but the order should be settled before the second one is implemented so the rebase is mechanical.
- Not a breaking change. Purely additive exports and one new optional constructor argument path (`policies=[ErrorRatePolicy(...)]`), which already exists as an accepted shape.
- Single-repo change (`vidbyte-sdk`). No coordinated deployment.
- Rollback: revert this PR (or, if stacked and unmerged, simply close it) — nothing persisted, nothing migrated.

---

## 12. Open Questions

- [ ] Should the ratio use **attempts** (this doc's recommendation — every retry counts, so the number measures the retry tax directly) or **iterations** (one success + one failure per iteration counts as 1 attempt, so the ratio tracks "bad iterations per iteration")? The user's original framing — "track attempts/failures per model across the whole run" — names attempts; this doc follows it.
- [ ] Inherited from PR #339, not resolved here: should `"error_rate_exceeded"`/`"cost_budget_exceeded"`/`"token_budget_exceeded"` (strings reusing the `error_type` field) eventually become a structured `trigger_kind: "error" | "policy"` field? This PR adds one more string value to the existing pattern rather than resolving the question.
- [ ] Should `min_attempts` be a hardcoded constant instead of a constructor kwarg? Kept as a kwarg defaulting to 3 for now — it is a user-facing behavior knob with a defensible default, and a constant would be harder to discover than a documented constructor parameter.

---

## 13. Alternatives Considered

### Alternative 1: Count only errors that escape the retry loop

- What: Reuse the existing `fallback_errors`/`_fallback_transition` path as the failure signal — no new counting code.
- Why rejected: failures a retry recovers never reach that path, and those recovered failures are *exactly* the retry tax this policy exists to detect. A 1-in-5-flaky provider whose retries usually succeed would show a ratio of zero and the policy would never fire — it would be a policy that does nothing in the scenario it exists for. The counting must happen inside `_invoke_with_middleware`.

### Alternative 2: Mutable counters on `AgentFallback`

- What: Store `{index: (attempts, failures)}` on the chain object.
- Why rejected: `AgentFallback` is agent-owned and immutable by design (PR #339's concurrency guarantee — the chain is shared across concurrent runs, with only loop-local mutable state). Counters there would leak across runs (violating the within-run requirement) and break the concurrency claim. `AgentRuntime` is constructed fresh per run and is already the home of per-run fallback state (`fallback_attempts`, `fallback_errors` loop locals live in its `arun`).

### Alternative 3: Per-hop compound values `(min_attempts, max_ratio)` tuples

- What: Each hop configures its own warm-up floor and ceiling as a pair.
- Why rejected: breaks `AgentFallbackSettings._validate_policy_hop_values`, which requires `hop_values()` to return plain positive non-bool numbers; and no stated need exists for per-hop floors. One global `min_attempts` scalar is the minimal complete shape.

### Alternative 4: Count per iteration instead of per attempt

- What: Record one attempt per outer-loop iteration regardless of how many retries happened inside.
- Why rejected: per-iteration counting hides the retry tax — the exact thing the policy detects. If a flaky iteration pays 3 retries and one success, per-attempt accounting shows 3/4 = 0.75 (fires), per-iteration shows 1/1 = 1.0 (also fires, but insensitive to the retry depth that makes the tax visible). The user's framing says "attempts/failures per model."

### Alternative 5: A merged "proactive budget check" abstraction

- What: One generic check loop taking `(observed, ceiling_getter, reason)` triples for cost, tokens, and error rate.
- Why rejected: the same premature-abstraction reasoning the token-budget doc records for its Alternative 3 — `deadline_for`/`budget_for` are separate one-line methods sharing one fold, not a parameterized mega-method, and two/three occurrences of the same shape are not yet the threshold at which this codebase reaches for a shared abstraction. Keeping the error-rate block sequential and separate matches the established grain and keeps the stacked diff reviewable against #339.

### Alternative 6: A new file (`error_rate.py`) instead of extending `policies.py`

- What: Give `ErrorRatePolicy` its own module.
- Why rejected: `policies.py`'s stated purpose is the per-hop policy classes; a third policy of the same shape belongs with its siblings, exactly as `TokenBudgetPolicy` does in the token-budget doc.

---

## 14. CI Gate

Per the repo's field guide (`field-guide/vidbyte-sdk/local-ci-verification.md`), from inside the implementation worktree:

```bash
PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source
python scripts/run_ci.py --stage package
python scripts/run_ci.py
```

The `PYTHONPATH` prefix on the source stage only is required — without it, the editable install resolves `vidbyte` to the canonical checkout and silently tests old code; leaking it into the package stage breaks that stage's fresh-venv install check instead. The SDK gate installs dev deps first (`python -m pip install -e ".[dev]"`). All stages, then the full run, must pass before this PR is opened. This change is verified against the #339 branch tip (`dcc4dbf`) with the existing suite green (**1555 passed, 1 skipped** on `main` at `08e71ef`, plus #339's own additions).