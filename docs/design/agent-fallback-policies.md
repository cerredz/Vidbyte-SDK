# Design Doc: Agent Fallback Policies

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-17
**Last Updated:** 2026-08-17

---

## 1. Overview

The fallback chain a `BaseAgent` can declare (`fallback=`) today advances to the next model for exactly one reason: the current model raised a provider-level exception. This change does two things. First, it relocates all fallback code — currently split across `vidbyte/agents/fallback.py` and `vidbyte/agents/settings/fallback.py` — into a single `vidbyte/agents/fallback/` package, matching the existing `vidbyte/agents/pricing/` package convention for a multi-file subsystem. Second, it adds two new trigger conditions alongside the existing error-based one: a **Latency Policy** (advance when a single call exceeds a per-hop deadline, whether or not the provider ever raises) and a **Cost/Budget Policy** (advance when cumulative run cost crosses a per-hop ceiling — a trigger with no error at all). Both are **per-hop** configurations: because the chain can grow past two models ("fallbacks of fallbacks"), each policy takes one value per transition the chain can actually take, never one value per model — the last model in the chain has nowhere left to escalate to, so it never gets one. This invariant (`len(policy values) == len(fallback models) == number of transitions`) is enforced once, eagerly, at `AgentFallbackSettings` construction, with an error message that states the arithmetic in plain English.

---

## 2. Goals & Non-Goals

### Goals

- Move `vidbyte/agents/fallback.py` and `vidbyte/agents/settings/fallback.py` into a new `vidbyte/agents/fallback/` package (`chain.py`, `settings.py`, `policies.py`, `__init__.py`), with every existing public import path continuing to resolve unchanged.
- Add `LatencyPolicy`: a per-hop deadline that, when exceeded, advances the chain — implemented by wrapping the model invocation in `asyncio.wait_for`, reusing the existing `TimeoutError`-triggers-fallback path with zero new decision logic.
- Add `CostBudgetPolicy`: a per-hop cumulative-cost ceiling that, when crossed, advances the chain proactively — a genuinely new trigger point, since nothing failed.
- Introduce `AgentFallbackSettings(policies=...)`, validated so that every per-hop policy supplies exactly one value per transition (`len(models)` values, not `len(models) + 1`), with every gap, wrong-length array, and non-positive value rejected at construction time.
- Keep the existing exception-based trigger (`fallback_on`) exactly as it behaves today — chain-wide, not per-hop, untouched.
- Brainstorm 3–4 additional fallback policies as a documented catalog for future work (Section 13), not implemented in this change.

### Non-Goals

- **Converting `fallback_on` into a per-hop policy.** Exception applicability ("does `TimeoutError` justify a switch") isn't a case anyone has asked to vary hop-by-hop the way a dollar ceiling or a deadline legitimately does. Recorded as an open question in Section 12 rather than assumed.
- **Wiring Latency/Cost policies into `BaseAgent._run_non_text_runner`** (image/audio/video/embedding runners). That path calls the model once with no per-iteration checkpoint loop — the seam this design hangs Cost off of (`runtime.py`'s top-of-iteration check) doesn't exist there. A single-call latency wrap is plausible as a smaller follow-up; cost-triggered downgrade is not, since there is no "next iteration" to protect. Both are deferred.
- **Implementing** the Output-Quality, Tool-Call-Reliability, Rate-Limit-Circuit-Breaker, or Confidence-Escalation policies brainstormed in Section 13. Cataloged only.
- **New test files**, per the `/design-doc-no-tests` workflow. The existing suite (1555 passed, 1 skipped at `08e71ef`) must stay green.
- **Session serialization of policies.** `RunState`/`export_state`/`restore` already don't carry the fallback chain at all (an existing, pre-dated non-goal from the original fallback design); policies inherit that same gap, not a new one.

---

## 3. Background & Context

### Why now

This is a direct continuation of a design conversation about `vidbyte/agents/fallback.py` (originally built in `docs/design/agent-model-fallback.md`, merged and in production). That conversation converged on two concrete policies and one hard product constraint: as the chain grows past a single fallback ("fallbacks of fallbacks"), a flat scalar config (`timeout_seconds=8.0`) can't express "give the primary 8s, but the second fallback only needs 5s before we give up entirely" — it has to be an array shaped to the chain. Alongside that, the user asked to physically relocate the fallback subsystem into its own folder before adding the new policies, since it is about to grow from two files to four.

### Current state (verified in this repo, this session)

- `vidbyte/agents/fallback.py` defines `AgentFallback` (the chain: `models`, `fallback_on`, `advance()`, `transform()`, `attempt_record()`, a private runner cache) and `DEFAULT_FALLBACK_ERRORS`.
- `vidbyte/agents/settings/fallback.py` defines `AgentFallbackSettings` (developer-facing config: `models`, `fallback_on`, `enabled`), which normalizes bare/prefixed model strings against the primary and produces an `AgentFallback` via `to_fallback()`.
- `FallbackModel` and `FallbackTransform` are dataclasses in `vidbyte/lib/dataclasses/agents.py`, alongside `AgentRunnerConfig`, `AgentRuntimeConfig`, `AgentCard`, and other agent-wide contracts. They are **not** moving — `lib/dataclasses/` is the SDK's shared, dependency-free data-contract layer that `vidbyte/agents/*` (a higher layer) imports from; colocating them with `agents/fallback/` would invert that layering for two of many peer dataclasses in that file.
- The chain is walked at two call sites: `AgentRuntime._fallback_transition` (`runtime.py:762-774`), reached from the `except BaseException` handler in the main tool-using loop (`runtime.py:343-365`), and `BaseAgent._run_non_text_runner` (`base.py:866-901`), which duplicates the same `is_model_error → advance → attempt_record → transform` sequence by hand for runner types that skip the loop entirely.
- Every model call's usage is already recorded once, centrally: `self.usage_tracker.record_call(raw_result)` at `runtime.py:388`, inside `_invoke_with_middleware`, on every iteration. `self.usage_tracker.rollup().cost_usd` (`agents/pricing/records.py:58`, `UsageRollup.cost_usd`) is therefore always current by the time control returns to the outer loop. This is the exact hook Cost policy needs, and it requires no new accounting — confirmed against the project field guide's own rule (`field-guide/vidbyte-sdk/runtime-boundaries.md`): *"Keep model usage accounting agent-owned... Propagate and use the agent's `UsageTracker`, recording each raw model response once."* Cost policy reads that tracker; it does not add a second recording path.
- The actual model call is `raw_result = await handle.invoke(message, **current_call_options)` at `runtime.py:718`, inside `_invoke_with_middleware`'s own retry loop (`runtime.py:671-760`). `asyncio` is already imported in `runtime.py` (line 22). The SDK's `requires-python = ">=3.11"` (`pyproject.toml:10`), confirmed against `.github/workflows/ci.yml`'s 3.11/3.12 matrix — meaning `asyncio.TimeoutError` is guaranteed to be the exact same class as the builtin `TimeoutError` (aliased since 3.11), which is already in `DEFAULT_FALLBACK_ERRORS`. A latency-triggered timeout therefore flows through the *existing* retry-then-reraise-then-fallback pipeline with no new exception handling.
- `AgentFallback.model_at(index)` already raises `ConfigurationError` on out-of-range access (`fallback.py:169-173`) — the existing precedent for "validate the boundary once, trust it everywhere after," which this change extends to per-hop policy arrays.
- `fork()` (`agents/fork.py:62`) re-passes `agent._fallback_spec` — the original constructor input, not the built `AgentFallback` — to the child's constructor. Since `AgentFallbackSettings.policies` is just a field on that spec object, fork inherits it for free; no change to `fork.py` is required.
- No test file references `AgentFallback`, `AgentFallbackSettings`, `FallbackModel`, or `FallbackTransform` by name (checked via repo-wide grep of `tests/`), so the "no new tests" constraint carries no hidden regression risk from an existing suite that pins the old file layout.
- `typing.Protocol` is an established pattern in this codebase (15 files, e.g. `vidbyte/agents/multi/orchestrator.py:37`, `class MultiAgentOrchestrator(Protocol):`), but the specific idiom used for *optional* capability methods elsewhere in `agents/base.py` (`_bind_session_tool`: `binder = getattr(tool, "bind_session", None); if not callable(binder): return`) is plain `getattr`/`callable()` duck typing, not a `Protocol`. This design follows that second idiom for `deadline_for`/`budget_for` (optional, policy-kind-specific) and reserves an explicit contract only for `hop_values()` (required of every per-hop policy), matching how the codebase already draws that line.

### Baseline

`python -m pytest tests/ -q` on `origin/main` (`08e71ef`): **1555 passed, 1 skipped, 0 failed.** This change must keep that result exactly, plus green `scripts/run_ci.py`.

---

## 4. Requirements

### Functional Requirements

**Relocation**

1. `vidbyte/agents/fallback/` is a package with `chain.py` (the `AgentFallback` class + `DEFAULT_FALLBACK_ERRORS`, moved verbatim from `agents/fallback.py` plus the additions in Requirements 6–11 below), `settings.py` (`AgentFallbackSettings`, moved verbatim from `agents/settings/fallback.py` plus the additions in Requirement 5), `policies.py` (new), and `__init__.py` re-exporting `AgentFallback`, `FallbackTransform`, `DEFAULT_FALLBACK_ERRORS`, `AgentFallbackSettings`, `LatencyPolicy`, `CostBudgetPolicy`.
2. `vidbyte/agents/settings/__init__.py` re-exports `AgentFallbackSettings` from its new location (`from vidbyte.agents.fallback.settings import AgentFallbackSettings`) so `from vidbyte.agents.settings import AgentFallbackSettings` — the path shown in `agents/README.md` and used by `vidbyte/agents/__init__.py` — continues to resolve unchanged.
3. `vidbyte/agents/__init__.py`'s `from vidbyte.agents.fallback import AgentFallback, FallbackTransform` requires no edit (a package `__init__.py` satisfies the same import). Its policy re-export line and `__all__` gain `LatencyPolicy`, `CostBudgetPolicy`.
4. Every internal importer of the old module paths (`agents/base.py`, `agents/runtime.py`, `agents/fallback.py`'s own `settings.fallback` import, `agents/settings/fallback.py`'s own `agents.fallback` import, `lib/dataclasses/agents.py`'s `TYPE_CHECKING` import) is updated to the new paths. No external/public import path changes.

**Policy configuration**

5. `AgentFallbackSettings.__init__` accepts a new keyword-only `policies: Sequence[object] = ()`. Each entry that exposes a callable `hop_values() -> Sequence[float]` is validated: `len(hop_values()) == len(self.models)` exactly (the developer's declared fallback list, which already equals the resolved chain's transition count once the primary is prepended), and every value in it is a positive `int`/`float` (not `bool`, not `None`). Both violations raise `ConfigurationError` at settings-construction time, before any agent exists, with a message that states the arithmetic ("this chain has N fallback model(s) ... which means N possible transitions ... one for the primary and one for each fallback except the last").
6. `AgentFallbackSettings.to_fallback()` passes `policies=self.policies` through to `AgentFallback`.

**Latency Policy**

7. `LatencyPolicy(timeout_seconds_by_hop: Sequence[float])` exposes `hop_values()` and `deadline_for(index: int) -> float | None`.
8. `AgentFallback.deadline_for(index) -> float | None` folds over `self.policies`, returning the first non-`None` result of any policy exposing `deadline_for`.
9. `AgentRuntime._invoke_with_middleware` accepts a new `timeout_seconds: float | None = None` parameter; when set, it wraps `handle.invoke(...)` (only, not the surrounding retry loop) in `asyncio.wait_for(..., timeout=timeout_seconds)`. The caller (`arun`'s main loop) passes `self.fallback.deadline_for(fallback_index)` when `self.fallback is not None`, else `None`.
10. A timeout re-raises exactly like any other provider error: retry middleware sees it first (`on_model_error`), and only once retries are exhausted does it propagate to the existing `except BaseException` fallback handler at `runtime.py:343`. No changes to `_fallback_transition`, `is_model_error`, or `advance`.

**Cost/Budget Policy**

11. `CostBudgetPolicy(cost_ceiling_usd_by_hop: Sequence[float])` exposes `hop_values()` and `budget_for(index: int) -> float | None`.
12. `AgentFallback.budget_for(index) -> float | None` folds over `self.policies` the same way `deadline_for` does.
13. `AgentFallback.advance_after_success(index: int, *, cost_usd: float | None) -> int | None` returns `index + 1` when `cost_usd` is known, a budget is configured for `index`, `cost_usd` has reached or crossed it, and `index + 1 < len(models)`; otherwise `None`.
14. `AgentFallback.policy_attempt_record(index, next_index, reason: str) -> dict[str, str]` produces the same `{"from", "to", "error_type"}` shape as the existing `attempt_record`, sharing a private `_build_attempt_record` helper, with `error_type` set to the given reason string (e.g. `"cost_budget_exceeded"`) instead of an exception's class name. The existing `attempt_record(index, next_index, error)` signature and both its call sites (`runtime.py`, `base.py`) are unchanged.
15. `AgentRuntime.arun`'s main loop checks the cost policy once per iteration, after `iteration_count > 0` (so the very first model call, before any usage exists, is never checked) and after the existing `_budget_stop` check, using a new private `_cost_fallback_transition` helper mirroring `_fallback_transition`'s shape. On a hit, it performs the same `transform` → swap `handle`/`provider`/`tool_schemas`/`messages`/`fallback_index` → publish fallback metadata sequence the error path uses, then proceeds into that iteration with the new model.
16. The cost check never fires on the iteration that is about to return a final `AgentResult` — it is checked before the next model call is attempted, not after the run has already produced its answer, so a policy hit is never silently wasted on a run that was already finishing.

### Non-Functional Requirements

- **Performance:** zero added latency/allocations on a run with no `policies=` configured — both `deadline_for`/`budget_for` short-circuit to `None` over an empty tuple, and `_invoke_with_middleware`'s `wait_for` wrap is skipped entirely when `timeout_seconds is None`.
- **Concurrency:** `AgentFallback.policies` is immutable after construction, matching the existing `models`/`fallback_on` immutability; the chain remains safe under concurrent `arun_sequentially`/`asyncio.gather` use, since the only mutable state (`fallback_index`) stays a loop-local integer as it already is today.
- **Observability:** every policy-triggered switch is recorded identically to an error-triggered one — same `AgentResult.metadata["fallback"]` shape, same `agent.fallback` trace span — distinguished only by `error_type` carrying a reason string instead of an exception class name.
- **Security:** no change to the existing rule that `FallbackModel.api_key` never reaches trace or metadata payloads; policy values (deadlines, dollar ceilings) carry no credential material by construction.
- **Correctness:** the per-hop array invariant is enforced exactly once, at `AgentFallbackSettings` construction — never re-validated per call — matching the existing `model_at()` boundary-check precedent.

---

## 5. High-Level Design

The relocation is mechanical: three existing classes move into a new package with no behavior change, and every import site is updated in place. The new capability rides two hook points that already exist in shape, if not in function, in `AgentRuntime.arun`: the `except BaseException` branch that already knows how to ask `AgentFallback` for a transition (extended for Latency, via a plain timeout wrap that turns into that same exception path), and the top of each loop iteration, which already runs a budget check (`_budget_stop`) and a middleware hook (`before_iteration`) before making the next model call — exactly where a *new* proactive check belongs, since it must run before a call is made, not in response to one failing.

```
AgentFallbackSettings(models=[...], policies=[LatencyPolicy([...]), CostBudgetPolicy([...])])
        |  to_fallback(primary=...)
        v
AgentFallback(models=[primary, fb1, fb2, ...], fallback_on=..., policies=(...))
        |
        +-- deadline_for(index) --> AgentRuntime._invoke_with_middleware wraps handle.invoke in wait_for
        |                            (fires -> TimeoutError -> existing except/retry/fallback path)
        |
        +-- budget_for(index) + advance_after_success(index, cost_usd) --> AgentRuntime.arun,
        |    checked once per loop iteration using self.usage_tracker.rollup().cost_usd
        |
        +-- advance(error, index)  [unchanged]      --> existing except-branch path
```

Both new triggers ultimately call the same `AgentFallback.transform()` the error path already uses to rebuild `handle`, `provider`, `tool_schemas`, and `messages` — the wire-format-compatibility logic, the runner cache, and the metadata/tracing shape are all reused verbatim. The only genuinely new piece of runtime logic is the top-of-iteration cost check and the `timeout_seconds` plumbing through `_invoke_with_middleware`; everything else is either a data-shape addition (`policies` field, two new small classes) or a straight file move.

---

## 6. Detailed Design

### 6.1 `vidbyte/agents/fallback/__init__.py`

**File(s):** `vidbyte/agents/fallback/__init__.py`
**Type:** New file (replaces `vidbyte/agents/fallback.py`)

#### What it does
Public surface for the package. Re-exports exactly what `agents/fallback.py` exported today, plus the two new policy classes.

#### Interface / API
```python
from vidbyte.agents.fallback.chain import AgentFallback, DEFAULT_FALLBACK_ERRORS
from vidbyte.agents.fallback.policies import CostBudgetPolicy, LatencyPolicy
from vidbyte.agents.fallback.settings import AgentFallbackSettings
from vidbyte.lib.dataclasses.agents import FallbackTransform

__all__ = ["AgentFallback", "AgentFallbackSettings", "CostBudgetPolicy", "DEFAULT_FALLBACK_ERRORS", "FallbackTransform", "LatencyPolicy"]
```

#### Edge Cases & Error Handling
N/A — pure re-export module.

---

### 6.2 `vidbyte/agents/fallback/chain.py`

**File(s):** `vidbyte/agents/fallback/chain.py`
**Type:** New file (moved from `vidbyte/agents/fallback.py`, extended)

#### What it does
Everything `AgentFallback` does today (`models`, `fallback_on`, `is_model_error`, `advance`, `transform`, runner cache, `model_at`, `result_metadata`), plus the policy-driven additions.

#### Interface / API
```python
class AgentFallback:
    def __init__(self, models: Sequence[FallbackModel], *, fallback_on: tuple[type[BaseException], ...] = DEFAULT_FALLBACK_ERRORS, policies: Sequence[object] = ()) -> None: ...

    def deadline_for(self, index: int) -> float | None: ...
    def budget_for(self, index: int) -> float | None: ...
    def advance_after_success(self, index: int, *, cost_usd: float | None) -> int | None: ...
    def policy_attempt_record(self, index: int, next_index: int, reason: str) -> dict[str, str]: ...

    # existing, unchanged:
    def is_model_error(self, error: BaseException) -> bool: ...
    def advance(self, error: BaseException, index: int) -> int | None: ...
    def attempt_record(self, index: int, next_index: int, error: BaseException) -> dict[str, str]: ...
    def transform(self, handle, provider, tools, messages, index) -> FallbackTransform: ...
```

#### Logic / Algorithm
1. `__init__` stores `self.policies = tuple(policies)` alongside the existing `models`/`fallback_on` assignment. No validation here — the array-length invariant is validated once, upstream, in `AgentFallbackSettings`, which is the only production path that builds an `AgentFallback` with policies attached.
2. `deadline_for`/`budget_for` share a private fold: `_first_policy_value(self, index: int, attr: str) -> float | None` iterates `self.policies`, and for each policy exposing a callable attribute named `attr`, calls it with `index` and returns the first non-`None` result; returns `None` if no policy answers.
3. `advance_after_success` returns `None` immediately if `cost_usd is None` or `index + 1 >= len(self.models)` (nowhere left to go — same guard shape as `advance`), otherwise compares `cost_usd` against `self.budget_for(index)`.
4. `attempt_record` and `policy_attempt_record` both delegate to a private `_build_attempt_record(index, next_index, trigger: str) -> dict[str, str]`, so the two public methods differ only in what they pass as `trigger` (an exception's class name vs. a policy reason string) — the dict shape stays defined in exactly one place.

#### Edge Cases & Error Handling
- Two policies both configuring a value for the same hop (e.g., two `CostBudgetPolicy` instances): `_first_policy_value` takes the first match in declaration order. Not validated as an error — a developer stacking two cost policies is unusual but not incoherent, and rejecting it outright would be an assumption this design doesn't need to make.
- `advance_after_success` called on the last chain index: returns `None` by the same guard `advance()` already uses, so a cost overrun on the terminal model is simply not actionable — the run continues on that model, exactly as an error there would raise rather than fall back.

---

### 6.3 `vidbyte/agents/fallback/settings.py`

**File(s):** `vidbyte/agents/fallback/settings.py`
**Type:** New file (moved from `vidbyte/agents/settings/fallback.py`, extended)

#### What it does
Everything `AgentFallbackSettings` does today, plus `policies` validation.

#### Interface / API
```python
class AgentFallbackSettings:
    def __init__(self, *, models: Sequence[str | FallbackModel], fallback_on: tuple[type[BaseException], ...] | None = None, policies: Sequence[object] = (), enabled: bool = True) -> None: ...
```

#### Logic / Algorithm
1. `_validate()` gains a fourth call: `self._validate_policy_hop_values()`, run after the existing three (`_validate_models_not_empty`, `_validate_entry_types`, `_validate_error_types`).
2. `_validate_policy_hop_values`: `expected = len(self.models)`. For each policy in `self.policies`, duck-type `hop_values = getattr(policy, "hop_values", None)`; skip policies that don't expose it (e.g., a future chain-wide policy). For ones that do: raise `ConfigurationError` if `len(hop_values()) != expected`, naming the policy's class, the actual count, the expected count, and the chain math in the message text (Requirement 5). Then validate every element is a positive, non-bool `int`/`float`, raising `ConfigurationError` naming the exact offending position and value.
3. `to_fallback()` gains `policies=self.policies` in its `AgentFallback(...)` construction call.

#### Edge Cases & Error Handling
- `policies=()` (default): loop body never executes, zero overhead, identical behavior to today.
- A policy with `hop_values()` returning the right length but containing `0` or a negative number: rejected — "positive" is enforced literally, since a zero-second deadline or zero-dollar budget can never be satisfied and is certainly not what a developer meant.
- A policy with `hop_values()` returning a `bool` entry (`True`/`False` are technically `int` subclasses in Python): explicitly excluded via `isinstance(value, bool)` check before the numeric check, so `policies=[LatencyPolicy([True, 5.0])]` is rejected rather than silently treated as `1.0` second.

---

### 6.4 `vidbyte/agents/fallback/policies.py`

**File(s):** `vidbyte/agents/fallback/policies.py`
**Type:** New file

#### What it does
Defines the two new per-hop policy classes.

#### Interface / API
```python
class LatencyPolicy:
    """Per-hop call deadline; exceeding hop i's timeout advances the chain past model i."""

    def __init__(self, timeout_seconds_by_hop: Sequence[float]) -> None:
        # Stores one deadline per transition, indexed the same as the resolved model chain.
        self.timeout_seconds_by_hop = tuple(timeout_seconds_by_hop)

    def hop_values(self) -> tuple[float, ...]:
        # Returns the raw per-hop values for AgentFallbackSettings' length/value validation.
        return self.timeout_seconds_by_hop

    def deadline_for(self, index: int) -> float | None:
        # Returns the deadline enforced while chain index `index` is in flight, or None past the array.
        return self.timeout_seconds_by_hop[index] if index < len(self.timeout_seconds_by_hop) else None


class CostBudgetPolicy:
    """Per-hop cumulative-cost ceiling; crossing hop i's ceiling advances the chain past model i."""

    def __init__(self, cost_ceiling_usd_by_hop: Sequence[float]) -> None:
        # Stores one USD ceiling per transition, indexed the same as the resolved model chain.
        self.cost_ceiling_usd_by_hop = tuple(cost_ceiling_usd_by_hop)

    def hop_values(self) -> tuple[float, ...]:
        # Returns the raw per-hop values for AgentFallbackSettings' length/value validation.
        return self.cost_ceiling_usd_by_hop

    def budget_for(self, index: int) -> float | None:
        # Returns the ceiling in effect while chain index `index` is in flight, or None past the array.
        return self.cost_ceiling_usd_by_hop[index] if index < len(self.cost_ceiling_usd_by_hop) else None
```

#### Edge Cases & Error Handling
Neither class validates its own array length against a chain — it cannot, since it is constructed before it knows how many models it will end up attached to. All validation is centralized in `AgentFallbackSettings` (Section 6.3), consistent with today's pattern where `AgentFallbackSettings`, not `FallbackModel`, owns cross-field validation.

---

### 6.5 `vidbyte/agents/runtime.py`

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does (changes only)
Adds the latency wrap to the single model-invocation call site, and adds the once-per-iteration cost check.

#### Interface / API
```python
async def _invoke_with_middleware(self, handle: RunnerHandle, message: str, call_options: Mapping[str, Any], *, ..., timeout_seconds: float | None = None) -> tuple[object | AgentResult, int, int]: ...

def _cost_fallback_transition(self, *, index: int, handle: RunnerHandle, provider: str, messages: list[dict[str, Any]], attempts: list[dict[str, str]], parent_span: SpanContext | None) -> "FallbackTransform | None": ...
```

#### Logic / Algorithm
1. In `_invoke_with_middleware`, the call at (current) line 718 becomes conditional:
   ```python
   if timeout_seconds is not None:
       raw_result = await asyncio.wait_for(handle.invoke(message, **current_call_options), timeout=timeout_seconds)
   else:
       raw_result = await handle.invoke(message, **current_call_options)
   ```
   This sits inside the existing retry `while True` loop, so a retried attempt gets a fresh full deadline rather than sharing a budget across retries — consistent with the existing rule that "retries happen first" on the current model before the chain advances.
2. In `arun`'s main loop, the call site (current line 328) passes `timeout_seconds=self.fallback.deadline_for(fallback_index) if self.fallback is not None else None`.
3. Immediately after the existing `_budget_stop` check (current lines 250-268) and guarded by `iteration_count > 0` (no usage exists yet on the first call), a new block calls `self._cost_fallback_transition(...)`. On a non-`None` result, it applies the same `handle, provider = transition.handle, transition.provider`; `tool_schemas, messages = transition.tool_schemas, transition.messages`; `fallback_index = transition.index`; `self._publish_fallback_metadata(...)` sequence the error branch already performs — no new sequence is invented, the existing one is reused.
4. `_cost_fallback_transition` mirrors `_fallback_transition`'s shape exactly: ask `self.fallback.advance_after_success(index, cost_usd=self.usage_tracker.rollup().cost_usd)`; if `None`, return `None`; otherwise build the record via `self.fallback.policy_attempt_record(index, next_index, "cost_budget_exceeded")`, append it to `attempts`, call `self.fallback.transform(...)`, record the span via the existing `_record_fallback_span`, and return the transition.

#### Edge Cases & Error Handling
- `self.fallback is None` (no chain configured): both new checks are no-ops — `timeout_seconds` stays `None`, and the cost check's guard (`if self.fallback is not None`) skips entirely.
- Cost policy fires on the last usable transition (`fallback_index` is already the last index): `advance_after_success` returns `None` via its own bounds guard — the run continues on the current (expensive) model rather than raising, matching how a *successful* call is never itself a failure worth aborting a run over.
- A `wait_for` timeout on a call whose provider request already partially completed (e.g., partial stream) is not specially handled — `asyncio.wait_for` cancels the underlying coroutine, and any partial-completion behavior is exactly what cancellation of that provider call already does today for any other cancellation source (`CancelledError` handling at `runtime.py:756-760` and `base.py:632-638` is unchanged and already exercises this path).

---

## 7. Data Model Changes

N/A — no database, no persisted schema. `AgentFallbackSettings` and `AgentFallback` are in-process Python objects; `RunState` does not serialize the fallback chain today (a pre-existing, unrelated non-goal) and this change does not alter that.

---

## 8. API Changes

N/A — no HTTP endpoints. The SDK-facing (Python constructor/class) surface changes are fully specified in Section 6; the only new public names are `LatencyPolicy`, `CostBudgetPolicy`, and the `policies=` keyword on `AgentFallbackSettings`.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/agents/fallback/__init__.py` | Package surface; re-exports existing + new names |
| CREATE | `vidbyte/agents/fallback/chain.py` | `AgentFallback` moved here, extended with policy folds |
| CREATE | `vidbyte/agents/fallback/settings.py` | `AgentFallbackSettings` moved here, extended with `policies` validation |
| CREATE | `vidbyte/agents/fallback/policies.py` | New `LatencyPolicy`, `CostBudgetPolicy` |
| DELETE | `vidbyte/agents/fallback.py` | Replaced by `vidbyte/agents/fallback/chain.py` + `__init__.py` |
| DELETE | `vidbyte/agents/settings/fallback.py` | Replaced by `vidbyte/agents/fallback/settings.py` |
| MODIFY | `vidbyte/agents/settings/__init__.py` | Re-export `AgentFallbackSettings` from its new location |
| MODIFY | `vidbyte/agents/__init__.py` | Add `LatencyPolicy`, `CostBudgetPolicy` to imports + `__all__` |
| MODIFY | `vidbyte/agents/base.py` | Update `from vidbyte.agents.fallback import AgentFallback` (path unchanged, same line — package satisfies it; listed for completeness/verification) |
| MODIFY | `vidbyte/agents/runtime.py` | `_invoke_with_middleware` gets `timeout_seconds`; new `_cost_fallback_transition`; top-of-iteration cost check; `TYPE_CHECKING` import path update |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Update `TYPE_CHECKING` import of `AgentFallbackSettings` to the new path |
| MODIFY | `vidbyte/agents/README.md` | Document `policies=`, `LatencyPolicy`, `CostBudgetPolicy`; update "Key Modules" file list to the new package layout |

No files under `tests/` are created or modified, per the `/design-doc-no-tests` workflow.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `asyncio` (stdlib) | Already imported in `runtime.py` | `wait_for`-based per-hop deadline enforcement | None — stdlib, already a transitive dependency of the whole async runtime |

No new third-party dependencies.

---

## 11. Rollout & Deployment

- No feature flag: both policies are opt-in by construction — an agent with no `policies=` argument (the overwhelming majority of existing callers) sees zero behavior change, verified by the fold logic returning `None` over an empty tuple.
- Not a breaking change for any documented public API. The one internal file-path change (`vidbyte.agents.settings.fallback` module → `vidbyte.agents.fallback.settings` module) is invisible to any caller using the documented `from vidbyte.agents.settings import AgentFallbackSettings` or `from vidbyte.agents import AgentFallbackSettings` paths; only a caller reaching into the private module path directly would break, and no such caller exists in this repo (verified by grep) or is part of the documented public API surface (`agents/README.md`).
- Single-repo change (`vidbyte-sdk`); no coordinated deployment with `vidbyte`, `vidbyte-cli`, or `vidbyte-harnesses` required for this PR. Those repos pin specific SDK commits/versions (see the various `.sdk-pin-*` directories observed in this workspace) and adopt this change whenever they next bump that pin.
- Rollback: revert the PR. Nothing persisted, nothing migrated.

---

## 12. Open Questions

- [ ] Should `fallback_on` eventually become per-hop too (`fallback_on_by_hop: Sequence[tuple[type[BaseException], ...]]`), for full consistency with "every policy is per-hop"? Deliberately not built here — no concrete use case has been named for varying exception applicability by hop, unlike deadlines and dollar ceilings, which obviously should vary ("give the primary more patience than a fallback you're already unhappy to be on").
- [ ] Should Latency (at least) be extended to `BaseAgent._run_non_text_runner` as a smaller follow-up, given it needs only a single-call `wait_for` wrap and no new checkpoint loop? Cost policy's exclusion from that path is firmer (no iteration to protect), but Latency's exclusion is purely scope discipline for this PR, not a structural blocker.
- [ ] Is `"cost_budget_exceeded"` (a plain string in the existing `error_type` metadata field) the right long-term shape, or should policy-triggered attempts eventually get a distinct metadata field from exception-triggered ones (e.g. `trigger_kind: "error" | "policy"`)? Kept as a string reusing the existing field for this PR, to avoid a metadata-shape change nothing has asked for yet.

---

## 13. Alternatives Considered

### Alternative 1: Flat scalar config instead of per-hop arrays
- What: `LatencyPolicy(timeout_seconds=8.0)` / `CostBudgetPolicy(max_cost_usd=0.50)`, applied uniformly to every hop.
- Why rejected: explicitly rejected by the user mid-design. It cannot express "the primary gets more patience than a fallback you're already unhappy to be running on," and every policy after the 2nd forces the same flattening. The per-hop array is barely more code and is required once the chain can have more than one fallback ("fallbacks of fallbacks").

### Alternative 2: Validate hop-array length inside each policy's own `__init__`
- What: `LatencyPolicy(timeout_seconds_by_hop=..., chain_length=...)`, validating internally.
- Why rejected: a policy is constructed standalone, before it's attached to any `AgentFallbackSettings`, so it cannot know the chain length without the caller supplying it redundantly — and a caller who gets that redundant number wrong defeats the entire point of validating it. Centralizing validation in `AgentFallbackSettings`, which already owns cross-field validation for `models`/`fallback_on`, needs no redundant input and matches the existing architecture.

### Alternative 3: A `typing.Protocol` requiring `deadline_for` and `budget_for` on every policy
- What: One formal `FallbackPolicy(Protocol)` with both methods; `LatencyPolicy` implements `budget_for` as a permanent `return None`, and vice versa for `CostBudgetPolicy`.
- Why rejected: forces boilerplate no-op methods on every policy for capabilities it doesn't have, and doesn't match how this codebase already draws this exact line — `agents/base.py`'s own `_bind_session_tool` treats "does this object support this optional capability" as a `getattr`/`callable()` check, not a Protocol requirement. `hop_values()`, which *every* per-hop policy must have, stays a real, required contract point (duck-typed, since even that doesn't need a formal `Protocol` class given the codebase's own precedent for this exact shape of check).

### Alternative 4: Apply the cost check inside `_invoke_with_middleware`'s retry loop, next to the latency wrap
- What: Check the budget immediately after each successful `handle.invoke()`, inside `_invoke_with_middleware`, rather than once per outer-loop iteration in `arun`.
- Why rejected: `_invoke_with_middleware` doesn't have `fallback_index` in scope, and threading it through would spread fallback-chain awareness into a function whose current job is "invoke one model call, handle retries" — a function `_fallback_transition` deliberately does *not* touch today (per the original fallback design's own stated constraint: the fallback catch lives in the outer loop, where `provider`/`tool_schemas`/`messages` locals are owned, not in the inner retry loop). Checking once per outer iteration keeps the cost policy at the same architectural altitude as the error policy.

---

## 14. Future Fallback Policy Catalog (Not Implemented)

Four additional trigger conditions, brainstormed as a follow-up catalog per the request driving this design doc. None are built in this PR.

1. **Output-Quality / Contract-Repair Policy.** Trigger: the current model fails `SchemaConformance`/output-contract repair (`agents/contracts/`, `_output_contract_with_schema` in `base.py`) some configured number of consecutive times. Advancing the chain here means "stop asking this model to fix its own malformed output, ask a different one instead." Strongest fit with existing infrastructure of the four, since the repair loop and its failure signal already exist — the only new part is deciding when repeated repair failure should stop being a repair problem and become a model problem.

2. **Tool-Call Reliability / Stagnation Policy.** Trigger: `ToolsFormatter.parse_tool_calls` (`runtime.py:428`) returns zero tool calls for several consecutive iterations on a model the agent expects to be calling tools, with no shrinking distance to a final answer — i.e., the model has stopped making progress in a way that looks like it forgot how to call tools rather than like it's genuinely done. Distinct from Output-Quality: this is about tool-calling competence mid-loop, not the shape of a final structured answer.

3. **Rate-Limit Circuit-Breaker Policy.** Trigger: `ProviderRequestError.status_code == 429` specifically (already a field on that error, `lib/errors/base.py`), tracked across runs rather than within one — after K rate-limits on a given provider/model within a cooldown window, skip straight past it for that window instead of paying the latency of trying-then-failing on every new run. The most architecturally different of the four: it needs state that outlives a single `AgentFallback` instance (a small shared registry keyed by provider/model), which is exactly the classic circuit-breaker pattern, applied here instead of the simpler "retry-then-advance" this design otherwise uses throughout.

4. **Confidence / Self-Reported-Uncertainty Policy.** Trigger: the model's own output carries a low self-rated confidence signal (a structured field the system prompt asks it to emit) → escalate to a stronger model for a second pass. The most speculative of the four — unlike the other three, nothing in the current codebase already computes this signal, so it depends on the calling agent's system prompt cooperating, and "stronger" isn't a property `FallbackModel` currently encodes (chain order today means "preferred," not "more capable"). Worth naming because it's the one pattern here that isn't just "route around a failure," it's "route toward more capability when the model itself signals doubt" — a genuinely different product story from the other three.
