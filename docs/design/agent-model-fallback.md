# Design Doc: Agent Model Fallback

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-22
**Last Updated:** 2026-07-22

---

## 1. Overview

Agents today bind to exactly one model. When that model's provider returns an error — rate limit, overload, outage, deprecated model ID — the run dies and the caller gets an `AgentExecutionError`. This change adds a `fallback` parameter to `BaseAgent` accepting an **ordered array of backup models**, where array index sets precedence. When a model call fails with a provider-level error, the agent runtime advances to the next model in the chain, rebuilds the provider-derived call state, and continues the same agentic loop from the next iteration. A new `AgentFallback` class owns the chain and every transformation needed to route to the next model, and a matching `AgentFallbackSettings` object makes the chain configurable through the SDK's existing `vidbyte.agents.settings` surface alongside `AgentLoopSettings`.

---

## 2. Goals & Non-Goals

### Goals

- Add `fallback=` to `BaseAgent.__init__`, accepting an ordered sequence where index 0 is tried first.
- Introduce `AgentFallback` as a first-class class holding the model chain and the transform helpers that enforce routing.
- Introduce `AgentFallbackSettings` in `vidbyte/agents/settings/`, mirroring `AgentLoopSettings`, so the chain can be passed as a settings object rather than only as a raw list.
- Fall back **without losing completed work** when the next model shares the primary's wire format (the common case: OpenAI → DeepSeek → xAI → OpenRouter, or Claude Opus → Claude Sonnet).
- Support cross-wire-format fallback (e.g. `anthropic` → `deepseek`) by resetting the transcript rather than sending malformed payloads.
- Fall back only on model/provider-level errors, never on tool or permission errors.
- Compose correctly with the existing retry middleware: retries exhaust on the current model first, then the chain advances.
- Make every switch visible in result metadata and in the trace.
- Raise a single error carrying the whole failure chain when every model is exhausted.

### Non-Goals

- **Cross-provider transcript translation.** Re-rendering an in-flight Anthropic tool-call transcript into OpenAI wire format requires a neutral transcript IR and an inverse of `ToolsFormatter.format_assistant_tool_calls`, which does not exist. Explicitly deferred; Section 13 records the seam it will plug into.
- **Fallback for non-linear runtimes.** MCTS search and the actor-model runtimes invoke through `runtimes/actor/broker.py`, not `_arun_once`. Construction raises `ConfigurationError`, following the existing precedent at `base.py:97-119`.
- **Fallback inside `AggregateAgent` proposers.** Aggregation is a separate agent class with its own multi-model semantics. Unchanged.
- **Session serialization of the chain.** `RunState` (`export_state` / `restore`, `base.py:364-390`) is a versioned schema; adding a field is a separate migration concern. A restored agent does not carry its fallback chain. Recorded in Section 12.
- **New test files.** Per the `/design-doc-no-tests` workflow. The existing suite must stay green.
- **Automatic chain construction.** No implicit "always fall back to a cheaper sibling" defaults. The chain is whatever the developer writes.

---

## 3. Background & Context

### Why now

Every `BaseAgent` funnels its model calls through a single `RunnerHandle` created once per run (`base.py:792-798`). A `ProviderRequestError` from a 429 or 529 propagates out of `_invoke_with_middleware` (`runtime.py:634`), unwinds `_arun_once`, and is re-wrapped by `generate_reply` into a failed run. Retry middleware (`middleware/builtins/retry.py`, `exponential_backoff_retry.py`) can retry the *same* model but cannot route to a different one. For long agentic loops that have already executed expensive tools, losing an entire run to a transient provider outage is the most expensive failure mode the SDK has.

### Current state

The mechanism to swap models mid-run already exists and is already exercised in production code:

- `RunnerHandle.with_runner(runner, provider)` (`lib/dataclasses/runner.py:30`) returns a new handle preserving invoke and extraction logic.
- `Runner.from_model(provider=..., model_name=..., api_key=..., temperature=...)` (`lib/runners/utility.py:33`) resolves a provider/model pair into an executable runner via `.build()`.
- `BaseAgent._runner_for_model()` (`base.py:1053`) is the existing single-model application of exactly that pair.

What does not exist is the policy layer deciding *when* to swap and the rebuild of provider-derived call state after a swap.

### The constraint that shapes the design

`_arun_once` captures `provider = handle.provider` **once**, at `runtime.py:158`, and that local drives four things that go stale on a swap:

| `runtime.py` | derived value | consequence if not rebuilt |
|---|---|---|
| 169 | `tool_schemas = self._resolve_tool_schemas(provider)` | new provider receives the old provider's tool schema shape |
| 1248 | `_build_iteration_call_options(..., provider)` → `response_format` | structured output silently mis-shaped |
| — | `ToolsFormatter.parse_tool_calls(raw_result, provider)` | tool calls parse to `()` — loop exits early and **looks like success** |
| 170 | the accumulated `messages` list | assistant/tool-result blocks remain in the previous provider's wire format |

Row 3 is the dangerous one: it degrades to a plausible wrong answer rather than an error. Therefore the fallback catch must live in `_arun_once`, where those locals are owned — **not** in `_invoke_with_middleware`, whose inner `while True` only re-invokes with identical `call_options`.

Conveniently, `_arun_once` already wraps the `_invoke_with_middleware` call in a `try/except BaseException` for iteration-span bookkeeping (`runtime.py:315-333`). The fallback branch extends that existing handler rather than introducing a new one.

### Wire format is not the same as provider

`ToolsFormatter.provider_from_model` (`lib/tools/formatter.py:29`) returns four family strings — `anthropic`, `gemini`, `xai`, `openai` — but every downstream branch (`format_tools:43`, `parse_tool_calls:106`, `format_tool_result:175`) only distinguishes **three** wire formats, treating `xai` as OpenAI-shaped. `ModelProvider` additionally defines `DEEPSEEK`, `GLM`, `MINIMAX`, `OPENROUTER`, all of which fall through to `openai`. Compatibility must therefore be decided on *wire format*, not on the family string, or `openai` → `xai` would be wrongly rejected as incompatible.

### Constraints discovered in the audit that shaped specific decisions

1. **`model_name` is already guarded.** `base.py:121-126` rejects any non-`str` `model_name` with a `ConfigurationError` pointing at `AggregateAgent`. The multi-model aggregation collision is therefore already impossible; no new guard is needed.
2. **`_runner_cache` is keyed by runner *type*, not by model** (`base.py:1062`). Caching fallback runners there would collide with the primary's cached text runner. `AgentFallback` owns a private cache keyed by chain index instead.
3. **`Runner` will not let a prefixed model override a conflicting explicit provider** (`lib/runners/utility.py:121`): the prefix is applied only when the explicit provider is `None` or already equal. Since a fallback entry's whole purpose may be to switch providers, `AgentFallbackSettings` parses the `provider/model` prefix itself and passes explicit values to `Runner`.
4. **Result metadata has a generic publication channel.** `_with_run_state_metadata` (`runtime.py:772`) lifts `run_state["__result_metadata__"]` into `AgentResult.metadata`, described in-code as a "generic, feature-agnostic lift". Publishing fallback metadata there requires **no signature change** to `_finish_result` or any of its ten call sites.

### Baseline

`python -m pytest tests/ -q` on `origin/main` (`ff6dfd6`): **1436 passed, 1 skipped, 0 failed.** This feature must keep that result exactly.

---

## 4. Requirements

### Functional Requirements

1. `BaseAgent.__init__` accepts `fallback: Sequence[str | FallbackModel] | AgentFallbackSettings | None = None`.
2. A bare string entry (`"gpt-5.2"`) inherits the agent's `provider`, `api_key`, and `temperature`.
3. A provider-prefixed string entry (`"anthropic/claude-sonnet-5"`) sets provider and model explicitly, overriding the agent's provider.
4. A `FallbackModel` entry may override `provider`, `model`, `api_key`, and `temperature` independently.
5. The effective chain is `[primary, *fallback]`, where `primary` is built from the agent's own `runner_config`.
6. On a model-call error the runtime advances to the next chain index and re-enters the loop with that model.
7. Fallback triggers only for provider/model-level exceptions (`ProviderRequestError`, `ProviderResponseError`, `ProviderConfigurationError`, `ProviderSelectionError`, `UnsupportedProviderError`, `TimeoutError`). `ToolExecutionError`, `PermissionDeniedError`, and `ConfigurationError` never trigger it, and `BaseException` subclasses such as `CancelledError` never trigger it.
8. Fallback triggers only *after* retry middleware has declined to retry further, i.e. on the re-raise path from `_invoke_with_middleware`.
9. When the next model shares the current model's wire format, `messages` is preserved verbatim; only the runner, provider, and tool schemas are rebuilt.
10. When wire formats differ, `messages` is reset to empty and the new model restarts from the original prompt with correctly shaped tool schemas.
11. When the chain is exhausted, raise `AllModelsFailedError` carrying every attempted model and every error, chained from the first failure.
12. `AgentResult.metadata["fallback"]` records `used`, `attempts`, `final_provider`, `final_model`, `context_reset`, and the error types encountered. It is absent when no fallback occurred.
13. Each switch emits an `agent.fallback` semantic span so the degradation is visible without diffing model names across `llm.call` spans.
14. Fallback state is **per-run**: a fallback on one `generate_reply` call must not pin subsequent calls to the backup model.
15. `fork()` propagates the fallback chain to the child agent, and `AgentForkSettings.fallback` can override it.
16. Non-text runner types (image, audio, video, embedding), which bypass the runtime at `base.py:784`, also honor the chain.
17. Constructing an agent with `fallback` and a non-linear runtime raises `ConfigurationError`.
18. Constructing an agent with `fallback` but no resolvable primary provider/model raises `ConfigurationError`.
19. `AgentFallbackSettings` is importable from `vidbyte.agents.settings` and exposes `to_fallback()`, mirroring `AgentLoopSettings.to_runtime_config()`.
20. An empty chain is rejected; `fallback=None` is the only way to disable the feature by omission, and `AgentFallbackSettings(enabled=False)` the only way to disable a defined chain.

### Non-Functional Requirements

- **Performance:** zero added latency and zero added allocations on the success path. Fallback runners are constructed lazily, only at the moment a switch occurs, so an unused chain costs nothing at agent construction beyond parsing strings.
- **Concurrency:** `AgentFallback` holds no per-run mutable state. The chain cursor is an integer local in `_arun_once`, so one agent instance remains safe under `arun_sequentially`, concurrent `AgentTool` invocation, and `asyncio.gather`.
- **Observability:** every switch is recorded in both result metadata (FR12) and the tracer (FR13). Silent degradation is treated as a defect.
- **Security:** `FallbackModel.api_key` must never reach a trace or metadata payload. Fallback records carry provider and model strings only. `__repr__` on both `FallbackModel` and `AgentFallbackSettings` must omit credentials.
- **Reliability:** worst-case model calls per run is bounded at `retry_attempts × len(chain)`; the chain does not reset the retry budget.
- **Backward compatibility:** `fallback` defaults to `None`. With it unset, every code path and every emitted metadata key is identical to today.

---

## 5. High-Level Design

The design adds one policy class, one settings class, one dataclass, one error type, and one branch in the runtime loop's existing exception handler. Nothing existing changes shape.

`AgentFallback` is an **immutable** object owned by the agent. It holds the ordered chain and the set of error types that count as model failures. It exposes two methods the runtime calls: `advance(error, index)` decides whether to move on and returns the next index, and `transform(handle, provider, tools, messages, index)` rebuilds every piece of provider-derived state for the model at that index. Because the cursor is passed in rather than stored, the class is safe to share across concurrent runs and cannot leak degradation between runs (FR14).

`BaseAgent.__init__` normalizes whatever the developer passed — raw strings, `FallbackModel` objects, or an `AgentFallbackSettings` — into a single `AgentFallback` whose index 0 is the agent's own primary model derived from `runner_config`. It validates incompatible combinations at construction time, so misuse fails fast rather than at first error. The object is handed to the linear runtime through `_runtime()` (`base.py:874`), which already forwards conditional keyword arguments.

`AgentRuntime._arun_once` keeps a `fallback_index` local initialized to 0. The existing `try/except BaseException` around `_invoke_with_middleware` (`runtime.py:315-333`) gains a fallback branch before its `raise`. Because `_invoke_with_middleware` already re-raises when middleware declines to retry (`runtime.py:634+`), the "retries first, then fallback" ordering (FR8) falls out for free. On a qualifying error the runtime asks `AgentFallback` for the rebuilt state, reassigns the `handle`, `provider`, `tool_schemas`, and `messages` locals, and `continue`s. The loop's next pass calls `_build_iteration_call_options` with the refreshed values, so the new model receives correctly shaped tools, response format, and history.

```
BaseAgent(fallback=[...])
   │  normalize + validate at construction
   ▼
AgentFallback(models=(primary, fb1, fb2), fallback_on=(...))
   │  passed to _runtime() for LINEAR only
   ▼
AgentRuntime._arun_once            fallback_index = 0
   │
   └─ while True:
        call_options = _build_iteration_call_options(..., tool_schemas, messages, provider)
        try:
            raw = await _invoke_with_middleware(handle, ...)   ← retries happen inside
        except BaseException as exc:
            _end_semantic_span(iteration_span, error=exc)
            transition = _fallback_transition(exc, index=fallback_index, ...)
            if transition is None:
                raise                                          ← unchanged behavior
            handle, provider, tool_schemas, messages = transition...
            fallback_index = transition.index
            continue                                           ← next model, same loop
        ... tool calls, tool results, next iteration
```

The key decision is **where the catch lives**. Putting it in `_arun_once` rather than `_invoke_with_middleware` means no new signal type is needed to carry a swap outward, and the four stale locals identified in Section 3 are all in scope at the catch site. This is both simpler and the only correct placement.

The second key decision is **what `transform` does to `messages`**. Rather than building a translator, `transform` compares wire formats via a new `ToolsFormatter.wire_format()` helper. Same format is a no-op on `messages` — the overwhelmingly common case, since fallback chains are usually siblings on one provider or OpenAI-compatible peers. Different format resets `messages`, which is lossy but safe. That single branch is exactly where the future translator will be substituted, with no caller changes.

---

## 6. Detailed Design

### 6.1 FallbackModel

**File:** `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified (new dataclass appended)

#### What it does

Describes one entry in the chain: which provider and model to call, and optional credential/temperature overrides. Lives beside `AgentRunnerConfig`, matching the repo convention that primitive config dataclasses live in `vidbyte/lib/dataclasses/`.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class FallbackModel:
    """One model in an ordered agent fallback chain."""

    provider: str
    model: str
    api_key: str | None = None
    temperature: float | None = None

    def __post_init__(self) -> None: ...
    def identity(self) -> str: ...
    def __repr__(self) -> str: ...
```

#### Logic / Algorithm

Pure data. Frozen and slotted, matching `AgentRunnerConfig` (`lib/dataclasses/agents.py`). `identity()` returns `"provider/model"` for metadata and error records. `__repr__` prints provider, model, and `api_key=***` when a key is set, never the key itself.

#### Edge Cases & Error Handling

- Empty or whitespace-only `provider` or `model` raises `ValueError` in `__post_init__`, matching the `ToolCall.__post_init__` precedent in `lib/dataclasses/tools.py`.

---

### 6.2 AgentFallback

**File:** `vidbyte/agents/fallback.py`
**Type:** New file

#### What it does

Owns the ordered model chain and every helper needed to enforce a routing decision. Immutable and run-agnostic: the caller supplies the current chain position and receives rebuilt state back.

#### Interface / API

```python
DEFAULT_FALLBACK_ERRORS: tuple[type[BaseException], ...] = (
    ProviderRequestError,
    ProviderResponseError,
    ProviderConfigurationError,
    ProviderSelectionError,
    UnsupportedProviderError,
    TimeoutError,
)


@dataclass(frozen=True, slots=True)
class FallbackTransform:
    """Rebuilt provider-derived state for the model a run is switching to."""

    index: int
    handle: RunnerHandle
    provider: str
    tool_schemas: tuple[dict[str, Any], ...]
    messages: list[dict[str, Any]]
    context_reset: bool


class AgentFallback:
    """Ordered model chain plus the transforms that route an in-flight run to the next model."""

    def __init__(self, models: Sequence[FallbackModel], *, fallback_on: tuple[type[BaseException], ...] = DEFAULT_FALLBACK_ERRORS) -> None: ...

    def advance(self, error: BaseException, index: int) -> int | None: ...
    def transform(self, handle: RunnerHandle, provider: str, tools: Tools, messages: list[dict[str, Any]], index: int) -> FallbackTransform: ...
    def build_runner(self, index: int) -> object: ...
    def is_wire_compatible(self, source: str, target: str) -> bool: ...
    def model_at(self, index: int) -> FallbackModel: ...
    def __len__(self) -> int: ...
    def __repr__(self) -> str: ...
```

#### Logic / Algorithm

`advance(error, index)`:
1. Return `None` when `error` is not an instance of `self.fallback_on` — not a model failure, caller re-raises.
2. Return `None` when `index + 1 >= len(self.models)` — chain exhausted, caller raises `AllModelsFailedError`.
3. Return `index + 1`.

`transform(handle, provider, tools, messages, index)`:
1. Read `target = self.model_at(index)`.
2. Build a concrete runner via `build_runner(index)`, which calls `Runner.from_model(provider=target.provider, model_name=target.model, api_key=target.api_key, temperature=target.temperature).build()` and memoizes the result in a private `dict[int, object]` cache. Constructed here and only here, so unused chain entries cost nothing.
3. Produce the new handle with `handle.with_runner(runner, target.provider)` — reuses the existing primitive, preserving invoke and extraction logic.
4. Re-render tool declarations with `ToolsFormatter.format_tools(tools, target.provider)`.
5. Decide the transcript: if `is_wire_compatible(provider, target.provider)`, carry `messages` through unchanged and set `context_reset=False`. Otherwise return an empty list and `context_reset=True`.
6. Return the `FallbackTransform`.

`is_wire_compatible(source, target)` compares `ToolsFormatter.wire_format(source) == ToolsFormatter.wire_format(target)`.

`build_runner`, `model_at`, and `is_wire_compatible` are separate named methods rather than inlined, per the class-first style requirement: `transform` composes them and reads as prose.

#### Edge Cases & Error Handling

- An empty `models` sequence raises `ConfigurationError` in `__init__`. A chain must always contain at least the primary.
- `build_runner` may itself raise `ConfigurationError` (unmappable provider/model, missing key). That exception propagates out of `transform` rather than being swallowed — a misconfigured fallback is a configuration bug and must be loud, not silently skipped as another failed attempt.
- `advance` is total: it never raises, so the runtime's error path has exactly one decision point.
- The private runner cache is keyed by chain index and lives on the `AgentFallback` instance, deliberately **not** in `BaseAgent._runner_cache`, which is keyed by runner type and would collide with the primary runner (`base.py:1062`).
- On Python ≥3.11 (`requires-python = ">=3.11"`) `asyncio.TimeoutError` is an alias of `TimeoutError`, so listing `TimeoutError` alone covers both.

---

### 6.3 ToolsFormatter.wire_format

**File:** `vidbyte/lib/tools/formatter.py`
**Type:** Modified

#### What it does

Collapses a provider name to the three wire formats the SDK actually emits, so compatibility is decided on payload shape rather than on the four-valued family string `provider_from_model` returns.

#### Interface / API

```python
@staticmethod
def wire_format(provider_or_model: str | None) -> str: ...
```

#### Logic / Algorithm

1. Call `ToolsFormatter.provider_from_model(provider_or_model)`.
2. Return `"anthropic"` and `"gemini"` unchanged; map everything else — including `"xai"` — to `"openai"`.

This mirrors exactly how `format_tools:43`, `parse_tool_calls:106`, and `format_tool_result:175` already branch, making the implicit three-way split explicit and reusable.

#### Edge Cases & Error Handling

- `None` or empty input yields `"openai"`, matching `provider_from_model`'s existing default.
- Adding a genuinely new wire format later requires editing this one method plus the three existing branch sites — the same blast radius as today.

---

### 6.4 AgentFallbackSettings

**File:** `vidbyte/agents/settings/fallback.py`
**Type:** New file

#### What it does

The developer-facing settings object for fallback, sitting beside `AgentLoopSettings` in `vidbyte/agents/settings/`. This is the "pass it through agent settings" surface: a validated plain class that converts into the internal `AgentFallback`, exactly as `AgentLoopSettings.to_runtime_config()` converts into `AgentRuntimeConfig`.

#### Interface / API

```python
class AgentFallbackSettings:
    """Validated configuration object for an agent's ordered model fallback chain."""

    def __init__(self, *, models: Sequence[str | FallbackModel], fallback_on: tuple[type[BaseException], ...] | None = None, enabled: bool = True) -> None: ...

    def to_fallback(self, *, primary: FallbackModel) -> AgentFallback | None: ...
    def resolved_models(self, *, primary: FallbackModel) -> tuple[FallbackModel, ...]: ...
    def __repr__(self) -> str: ...
```

#### Logic / Algorithm

`__init__` stores fields then calls `_validate()`, matching `AgentLoopSettings.__init__`. `_validate` decomposes into small named checks in the same style as `_validate_positive_int_fields` / `_validate_timeout_seconds`:

- `_validate_models_not_empty` — at least one entry.
- `_validate_entry_types` — every entry is a non-empty `str` or a `FallbackModel`.
- `_validate_error_types` — every `fallback_on` entry is a `BaseException` subclass.

`resolved_models(primary)` normalizes each entry against the primary:
1. A `FallbackModel` passes through unchanged.
2. A string containing `/` splits once. If the left side names a valid `ModelProvider`, it becomes the provider and the right side the model. If not, the whole string is treated as a bare model name (so OpenRouter-style `vendor/model` identifiers still work).
3. A bare string becomes `FallbackModel(provider=primary.provider, model=entry, api_key=primary.api_key, temperature=primary.temperature)`.
4. Returns `(primary, *normalized)`.

The prefix is parsed here rather than delegated to `Runner`, because `Runner._normalize_provider_and_model` only applies a model prefix when the explicit provider is `None` or already matches (`lib/runners/utility.py:121`) — which would silently ignore a cross-provider fallback entry.

`to_fallback(primary)` returns `AgentFallback(self.resolved_models(primary=primary), fallback_on=...)`, or `None` when `enabled` is `False`.

#### Edge Cases & Error Handling

- A bare string entry when the agent has no `provider` configured raises `ConfigurationError` naming the entry, because there is nothing to inherit from.
- `"openai/"` raises `ConfigurationError` — a provider prefix with an empty model is a typo, not a valid inherit.
- `enabled=False` yields `to_fallback() -> None`, letting a chain stay defined in config while disabled.
- Duplicate entries are permitted and not deduplicated: retrying the same model on a different key is legitimate.
- `__repr__` shows entry identities only, never `api_key`.

---

### 6.5 BaseAgent — construction, validation, propagation

**File:** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Accepts the new parameter, validates incompatible combinations, normalizes to an `AgentFallback`, forwards it to the linear runtime, and applies it on the non-text runner path.

#### Interface / API

```python
def __init__(self, *, ..., fallback: Sequence[str | FallbackModel] | AgentFallbackSettings | None = None) -> None: ...

def _resolve_fallback(self, fallback: object, agent_name: str) -> AgentFallback | None: ...
def _primary_fallback_model(self, agent_name: str) -> FallbackModel: ...
def _fallback_runner_for(self, index: int) -> tuple[object, str]: ...
```

#### Logic / Algorithm

1. A guard beside the existing non-linear checks (`base.py:97-119`) raises `ConfigurationError` when `fallback` is set on a non-linear runtime, reusing the established message wording.
2. `_primary_fallback_model` builds index 0 from `self.runner_config`: `FallbackModel(provider=..., model=..., api_key=..., temperature=...)`. Raises `ConfigurationError` when the agent has no `provider` or `model_name`, since there is no primary to fall back *from* (FR18).
3. `_resolve_fallback` coerces a raw sequence into `AgentFallbackSettings(models=...)` and then calls `to_fallback(primary=...)`. A single code path handles both input shapes, so validation cannot diverge between them. Returns `None` immediately when `fallback is None`, guaranteeing the untouched default path.
4. `self.fallback` and `self._fallback_spec` (the developer's original argument, retained for forking) are assigned in `__init__`.
5. `_runtime()` passes `fallback=self.fallback` inside the existing `if self.runtime_type is AgentRuntimeType.LINEAR:` block (`base.py:871-872`), so non-linear runtimes never receive the argument.
6. The non-text branch of `_run_direct` (`base.py:784-790`) wraps `_call_runner_once` in an advance/rebuild loop. That path has no `messages` and no tool schemas, so its transform reduces to building the next runner via `_fallback_runner_for` — a small loop, not a duplicate of the runtime logic.

#### Edge Cases & Error Handling

- `fallback=[]` raises `ConfigurationError` via `AgentFallbackSettings._validate_models_not_empty` rather than silently behaving as `None`. An empty chain is a mistake.
- `fallback=None` short-circuits before any validation, guaranteeing the no-op path (NFR: backward compatibility).
- No new guard is added for list-valued `model_name`; `base.py:121-126` already rejects it.

---

### 6.6 AgentForker / AgentForkSettings — fork propagation

**Files:** `vidbyte/agents/fork.py`, `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified

#### What it does

Carries the fallback chain from parent to child, with an optional per-fork override, matching how every other inheritable field is handled.

#### Interface / API

```python
@dataclass
class AgentForkSettings:
    ...
    fallback: Sequence[str | FallbackModel] | AgentFallbackSettings | None = None
```

#### Logic / Algorithm

`AgentForker.fork` (`fork.py:38-62`) gains one line in the `BaseAgent(...)` construction, following the exact inherit-or-override idiom already used for `provider`, `model_name`, and `handoff`:

```python
fallback=agent._fallback_spec if settings.fallback is None else settings.fallback,
```

The child re-normalizes the spec against its *own* primary model, which is correct: a fork that overrides `provider` or `model_name` should have bare-string fallback entries inherit the child's provider, not the parent's.

#### Edge Cases & Error Handling

- A child forked onto a non-linear runtime while the parent carries a fallback chain raises `ConfigurationError` from `BaseAgent.__init__`, consistent with how the other non-linear incompatibilities already surface through forking.
- `AgentForkSettings.__post_init__` needs no new validation; all fallback validation happens in `AgentFallbackSettings`.

---

### 6.7 AgentRuntime — the fallback loop

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Accepts the chain, catches qualifying model errors at the loop level, rebuilds provider-derived state, and continues.

#### Interface / API

```python
def __init__(self, *, ..., fallback: AgentFallback | None = None) -> None: ...

def _fallback_transition(self, error: BaseException, *, index: int, handle: RunnerHandle, provider: str, messages: list[dict[str, Any]], attempts: list[dict[str, str]], errors: list[BaseException], parent_span: SpanContext | None) -> FallbackTransform | None: ...
def _publish_fallback_metadata(self, run_state: dict[type, Any], attempts: Sequence[Mapping[str, str]], context_reset: bool) -> None: ...
```

#### Logic / Algorithm

In `_arun_once`, three locals join the existing set at `runtime.py:171-182`: `fallback_index = 0`, `fallback_attempts: list[dict[str, str]] = []`, `fallback_errors: list[BaseException] = []`.

The existing handler at `runtime.py:331-333` is extended:

1. `except BaseException as exc:` — end the iteration span with the error, exactly as today.
2. Call `self._fallback_transition(exc, index=fallback_index, ...)`.
3. `_fallback_transition` returns `None` when `self.fallback is None`, or when `AgentFallback.advance` returns `None` and no attempt has yet been recorded. The caller then executes the original `raise`, preserving today's behavior byte-for-byte for every existing agent.
4. When `advance` returns `None` but attempts *were* recorded, `_fallback_transition` raises `AllModelsFailedError` directly, chained from `fallback_errors[0]`.
5. Otherwise it records the attempt, opens and closes an `agent.fallback` semantic span via `_start_semantic_span` / `_end_semantic_span` (mirroring `_record_parser_span`, `runtime.py:1766`), calls `AgentFallback.transform`, and returns the result.
6. Back in `_arun_once`, `handle`, `provider`, `tool_schemas`, `messages`, and `fallback_index` are reassigned from the transform, `_publish_fallback_metadata` writes the record into `run_state["__result_metadata__"]`, and the loop `continue`s.

`_publish_fallback_metadata` merges into any existing `__result_metadata__` mapping rather than replacing it, since middleware also publishes through that channel. `_with_run_state_metadata` (`runtime.py:772`) then lifts it into `AgentResult.metadata["fallback"]` with no change to `_finish_result` or its call sites (FR12).

`CancelledError` and other non-`Exception` `BaseException` subclasses are excluded because they are not instances of any type in `DEFAULT_FALLBACK_ERRORS`, so `advance` returns `None` and the original `raise` runs.

#### Edge Cases & Error Handling

- A `transform` that itself raises (unbuildable runner) propagates immediately. It is a configuration defect, not a transient failure, and hiding it behind "try the next one" would make bad chains undiagnosable.
- Errors are appended in order so `AllModelsFailedError` reports the full chain, and `raise ... from fallback_errors[0]` makes the *first* failure the `__cause__`, since the last error is usually the least informative.
- The retry budget is not reset per model (NFR reliability), so worst case stays bounded.
- `context_reset=True` discards `messages` but **not** `call_contexts`, so `AgentResult.calls` and `tokens_used` still report everything the run actually did.

---

### 6.8 AllModelsFailedError

**Files:** `vidbyte/lib/errors/base.py`, `vidbyte/lib/errors/__init__.py`
**Type:** Modified

#### What it does

Signals that every model in the chain failed, carrying the per-model attempt record and error list.

#### Interface / API

```python
class AllModelsFailedError(AgentExecutionError):
    """Raised when every model in an agent's fallback chain has failed."""

    def __init__(self, message: str, *, attempts: Sequence[Mapping[str, str]], errors: Sequence[BaseException]) -> None: ...
```

#### Logic / Algorithm

Subclasses `AgentExecutionError` so existing `except AgentExecutionError` handlers keep working. Stores `attempts` and `errors` as instance attributes and passes a structured `details` dict to `super().__init__`, matching the `ProviderRequestError` constructor pattern in `lib/errors/base.py`.

#### Edge Cases & Error Handling

- `details` records provider, model, and `error_type` strings only — never `api_key`, keeping it safe for the trace-scrubbing rules already applied to agent metadata.
- `generate_reply`'s existing wrapper re-wraps it in an `AgentExecutionError`; the original remains reachable via `__cause__`, unchanged from how every other agent error behaves today.

---

### 6.9 Exports and documentation

**Files:** `vidbyte/agents/settings/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/agents/README.md`
**Type:** Modified

`AgentFallbackSettings` joins `AgentLoopSettings` in the settings sub-package exports. `AgentFallback`, `AgentFallbackSettings`, and `FallbackModel` are added to `vidbyte.agents.__all__`. Following the `AgentLoopSettings` precedent, they are **not** added to the top-level `vidbyte/__init__.py`, keeping settings objects consistently one import deep.

`vidbyte/agents/README.md` gains a "Model Fallback" section covering the chain, the wire-format rule and its transcript-reset consequence, the error-type filter, and the interaction with retry middleware. Each new or modified module's Context Protocol Header follows the existing convention.

---

## 7. Data Model Changes

N/A — no database, ORM, or persisted schema exists in this SDK. The only new type is the in-memory `FallbackModel` dataclass, fully specified in Section 6.1. `RunState`, the one versioned serialization schema, is deliberately untouched (Section 2, Non-Goals; Section 12).

---

## 8. API Changes

N/A for HTTP endpoints — this is a library, and no route or server contract changes. The public **Python** API changes are additive and fully specified in Section 6:

| Surface | Change | Breaking |
|---|---|---|
| `BaseAgent.__init__(fallback=...)` | New optional keyword, defaults `None` | No |
| `AgentForkSettings.fallback` | New optional field, defaults `None` | No |
| `AgentRuntime.__init__(fallback=...)` | New optional keyword-only, defaults `None` | No |
| `vidbyte.agents.settings.AgentFallbackSettings` | New export | No |
| `vidbyte.agents.{AgentFallback, FallbackModel}` | New exports | No |
| `vidbyte.lib.errors.AllModelsFailedError` | New export, subclass of `AgentExecutionError` | No |
| `ToolsFormatter.wire_format()` | New static method | No |
| `AgentResult.metadata["fallback"]` | New key, present only when a fallback occurred | No |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agent-model-fallback.md` | This design doc; first commit on the branch |
| CREATE | `vidbyte/agents/fallback.py` | `AgentFallback`, `FallbackTransform`, `DEFAULT_FALLBACK_ERRORS` |
| CREATE | `vidbyte/agents/settings/fallback.py` | `AgentFallbackSettings`, the agent-settings surface |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add `FallbackModel`; add `fallback` field to `AgentForkSettings` |
| MODIFY | `vidbyte/lib/tools/formatter.py` | Add `wire_format()` |
| MODIFY | `vidbyte/lib/errors/base.py` | Add `AllModelsFailedError` |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Export `AllModelsFailedError` |
| MODIFY | `vidbyte/agents/base.py` | `fallback=` kwarg, guards, normalization, `_runtime()` passthrough, non-text runner path |
| MODIFY | `vidbyte/agents/fork.py` | Propagate the chain to forked children |
| MODIFY | `vidbyte/agents/runtime.py` | `fallback=` kwarg, `_fallback_transition`, metadata publication |
| MODIFY | `vidbyte/agents/settings/__init__.py` | Export `AgentFallbackSettings` |
| MODIFY | `vidbyte/agents/__init__.py` | Export `AgentFallback`, `AgentFallbackSettings`, `FallbackModel` |
| MODIFY | `vidbyte/agents/README.md` | Document the fallback surface and its rules |

**Totals:** 3 created (1 doc, 2 source), 10 modified, 0 deleted.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| — | — | No new runtime dependencies | None |

The feature is built entirely from existing internals: `RunnerHandle.with_runner` (`lib/dataclasses/runner.py:30`), `Runner.from_model` (`lib/runners/utility.py:33`), `ToolsFormatter` (`lib/tools/formatter.py`), and the error hierarchy in `lib/errors/base.py`. `pyproject.toml` is unchanged.

**Indirect risk:** a fallback to a different provider requires that provider's credentials to be resolvable — either via `FallbackModel.api_key` or the provider adapter's environment lookup. A chain whose backup key is missing surfaces as a `ConfigurationError` from `transform` at switch time, not at construction. Section 12 records this.

---

## 11. Rollout & Deployment

- **Feature flags:** none. The feature is inert unless `fallback=` is passed.
- **Breaking change:** no. Every new parameter is optional and keyword-only; every new export is additive; result metadata gains a key only on runs that actually fell back.
- **Migration path:** none required. Existing agents are unaffected.
- **Deployment order:** single package, no service coordination.
- **Rollback:** revert the PR. No persisted state, no migration, no config to unwind.

---

## 12. Open Questions

- [ ] **Cross-wire-format fallback resets the transcript**, so tools already executed are not represented in the new model's context and may be called again. Acceptable for read-only tools; potentially harmful for tools that write. Current design chooses reset plus `context_reset: True` in metadata rather than refusing the switch.
- [ ] **A missing credential for a fallback entry fails at switch time, not construction.** Eager validation would need to resolve every provider's key up front, conflicting with lazy runner construction and failing agent builds over models that may never be called.
- [ ] **`RunState` does not carry the fallback chain**, so `BaseAgent.restore()` produces an agent without fallback. Adding it is a versioned-schema change; deferred to a follow-up.

---

## 13. Alternatives Considered

### Alternative 1: Add `fallback` to `AgentLoopSettings`

- **What:** put the chain on the existing settings object instead of creating a sibling.
- **Why rejected:** `AgentLoopSettings` is scoped to loop behavior — iteration, token, and tool-call limits plus tool policies — and `to_runtime_config()` maps them onto `AgentRuntimeConfig`. A model chain is runner identity, not loop configuration, and would be the only field not flowing through that conversion. `vidbyte/agents/settings/` is already a package rather than a single module, which is the shape that anticipates sibling settings classes.

### Alternative 2: Swap the handle inside `_invoke_with_middleware`

- **What:** catch and swap at `runtime.py:634+`, where model errors are already handled.
- **Why rejected:** the four provider-derived values in Section 3 are locals of the *outer* `_arun_once`. Continuing the inner loop re-sends identical `call_options`, so the new model would receive the previous provider's tool schemas — and `parse_tool_calls` would silently return `()`, ending the loop with a wrong-but-plausible answer. Carrying the swap outward would require a new signal type, which is strictly more machinery than extending the `try/except` that `_arun_once` already has.

### Alternative 3: Implement fallback as middleware

- **What:** a `FallbackModelMiddleware` hooking `on_model_error`.
- **Why rejected:** `MiddlewareDecision` has no "replace the runner" action, and `MiddlewareTransform` only transforms provider messages and system prompt. Adding a runner-swap action would widen the middleware contract for every implementer. It also would not satisfy the request for a constructor parameter, and middleware cannot reach the `_arun_once` locals that must be rebuilt.

### Alternative 4: Full cross-provider transcript translation in v1

- **What:** a neutral transcript IR plus an inverse of `format_assistant_tool_calls`, letting an in-flight Anthropic run continue on OpenAI with tool history intact.
- **Why rejected:** it is the larger half of the work and independent of the fallback mechanism itself. `ToolsFormatter` already provides provider→neutral (`parse_tool_calls`) and neutral→provider for tool *results* and *specs*; only the assistant tool-call turn lacks an inverse. Deferred to a follow-up PR, which substitutes step 5 of `AgentFallback.transform` (Section 6.2) with a translation call and changes no callers.

### Alternative 5: Mutable chain cursor stored on `AgentFallback`

- **What:** keep `self.index` on the object and mutate it, as originally sketched.
- **Why rejected:** `_runtime()` builds a fresh runtime per run but `AgentFallback` lives on the agent, so a transient outage in one run would permanently pin every later run to the backup model, violating FR14. It would also make one agent unsafe under `arun_sequentially` and concurrent `AgentTool` use. An integer local in `_arun_once` is both simpler and correct.

### Alternative 6: Reuse `BaseAgent._runner_cache` for fallback runners

- **What:** memoize fallback runners in the agent's existing runner cache.
- **Why rejected:** that cache is keyed by runner *type* (`base.py:1062`), not by model identity, so a fallback text runner would evict and impersonate the primary text runner for every subsequent run. `AgentFallback` keeps a private cache keyed by chain index.

---

## 14. CI Command Of Record

```bash
python -m pip install -e .
python -m pytest tests/ -q
```

There is no `scripts/run_ci.py` in this repository, and `.github/workflows/` contains only `publish.yml` (tag-triggered PyPI release, no pull-request checks), so pytest is the canonical gate. Because packaging is the only automated workflow, a clean editable install plus an import smoke check of the new exports is run alongside the suite — a broken export surface would otherwise go undetected until release.

**Baseline on `origin/main` (`ff6dfd6`): 1436 passed, 1 skipped, 0 failed.** This feature must keep that result exactly.
