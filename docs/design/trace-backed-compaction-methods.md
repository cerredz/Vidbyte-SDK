# Design Doc: Trace-Backed Compaction Methods

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-05
**Last Updated:** 2026-06-05

---

## 1. Overview

This feature adds a family of **context-compaction methods that fold a structured "continual trace" artifact back into the agent's provider-message history**. When an agent run accumulates a trace artifact (a typed `{field: value}` dict summarizing goal, actions, mistakes, status), these methods let the SDK replace some region of the conversation — everything after the system prompt, the oldest N iterations, the bloated middle, etc. — with a rendered version of that trace, optionally keeping a verbatim recent tail and protected messages. It is delivered as one pure compaction strategy (`ReplaceWithTraceCompaction`), one pure renderer (`TraceArtifactRenderer`), and one new middleware (`TraceReplacementCompactionMiddleware`) exposing the individual methods as named classmethod constructors, mirroring the existing `MessageHistoryCompactionMiddleware` pattern.

It is deliberately decoupled from the continual-trace *producer*: the middleware reads the artifact from a documented `run_state` key (or an injected artifact/callback), so it ships and tests on `main` today and "lights up" automatically once the continual-trace agent branch merges and begins publishing.

---

## 2. Goals & Non-Goals

### Goals
- Add every trace-backed compaction method from Families **A, B, C, E, F, G** of the prior design conversation (Family D — triggers — is explicitly excluded).
- Implement them as **parameters/presets on one strategy + one renderer + one middleware**, not as 25 separate `CompactionMode` enum values.
- Keep the strategy and renderer **pure and deterministic** (no `run_state`, no model calls), consistent with the other ~24 strategies in `strategies.py`.
- Make the middleware the **only** impure seam: it reads the trace artifact from `run_state`, renders it, and feeds it down as plain text via the existing engine.
- **Decouple** from the continual-trace producer via a documented `run_state` contract + an injectable artifact/callback, so the feature is shippable and testable on `main` without the trace-agent branch.
- Guarantee **safety on an empty/initial artifact** (cold start): never replace real history with an empty trace; fall back or no-op.
- Preserve **provider message correctness**: never split a `tool_call`/`tool_result` pair when keeping a tail.
- Follow the SDK compaction conventions: register through `engine._build_strategy`, re-export through `vidbyte.middleware.builtins` and `vidbyte.context.compaction`, add Context Protocol Headers, add tests-first.

### Non-Goals
- **Family D (triggers)** — no window-fill threshold, no "every N iterations" firing, no token-budget gating. When/whether to apply is left to composition (which middleware the developer attaches and in what order), exactly like today's `MessageHistoryCompactionMiddleware`, which also has no trigger.
- **Building or modifying the continual-trace agent/middleware.** That work lives on `feat/ct-agent-v2` and is out of scope here. This PR consumes its artifact through a contract, it does not produce it.
- No new third-party dependencies.
- No model/provider network calls from the strategy or renderer. The one method that needs a model (`trace_then_summarize_tail`) uses the existing injected-`Summarizer` protocol; the one that needs a fresh trace (`with_refresh`) uses an injected async callback. Neither performs hidden provider calls.
- No changes to non-linear runtimes (middleware is already forbidden there).
- No persistence or cross-run trace memory.

---

## 3. Background & Context

The SDK already has a mature compaction layer:

- `vidbyte/middleware/compaction/base.py` — `CompactionMode` enum, `BaseCompaction` ABC, `Summarizer` protocol, `TokenCounter`, `CompactionStats`.
- `vidbyte/middleware/compaction/strategies.py` — ~24 pure `BaseCompaction` subclasses, each `async def compact(messages) -> tuple[ContextMessage, ...]`. They take **only** a message sequence; they cannot see `run_state`.
- `vidbyte/middleware/compaction/engine.py` — `ContextCompactionEngine` converts provider dicts ⇄ `ContextMessage`, dispatches a `CompactionMode` to a strategy in `_build_strategy(mode, options)`, returns `(messages, CompactionStats)`.
- `vidbyte/middleware/compaction/context_compaction.py` — `MessageHistoryCompactionMiddleware` (and `SummaryCompactionMiddleware`, `ToolResultCompactionMiddleware`). `before_model_call` calls `engine.compact_provider_messages(...)` and returns `continue_(transform=MiddlewareTransform(provider_messages=...))`.
- Re-exports: `vidbyte/middleware/builtins/context_compaction.py`, `vidbyte/middleware/builtins/__init__.py`, `vidbyte/middleware/__init__.py`, `vidbyte/context/compaction.py`.

The skill `skills/vidbyte-sdk/middleware.md` §5.1 is explicit: *"Context compaction belongs in middleware for new agent code… Compaction middleware returns `MiddlewareDecision.continue_(transform=...)`."* The pattern for `ClearExceptSystemAndLogCompaction` is the direct precedent for this feature: it keeps system messages and injects **one synthesized `kind="summary"` message** built from external state (`progress_log`) passed in through `options`. Trace-backed compaction is the same move with a trace artifact as the payload.

**The producer dependency.** On a parallel branch (`feat/ct-agent-v2`), `ContinualTraceMiddleware` runs a `ContinualTraceAgent` every N iterations and at run end, accumulating a typed artifact and publishing it to `run_state["__result_metadata__"]["trace"]` — while *never* writing it into the main context window (an explicit invariant of that design). This feature is the sanctioned, opt-in exception: it moves that artifact across the wall, but only when a developer attaches this middleware. On `main` today, that producer does **not** exist; nothing publishes the artifact. Therefore this design treats the artifact source as a **contract** (`run_state` key + dict shape), supports an **injected artifact / async callback** as alternative sources, and degrades safely to no-op/fallback when no artifact is present.

`MiddlewareContext` on `main` already carries `run_state: dict[type, Any]`, `provider_messages`, `agent_context`, and `tokens_used`, and `run_state` is the same dict threaded into every hook of every middleware for a run — so reading a key another middleware wrote is a supported pattern (used by `loop_detection`, `confused_deputy`, `rate_limit`).

---

## 4. Requirements

### Functional Requirements

**Strategy + mode**
1. Add exactly one new `CompactionMode` value: `REPLACE_WITH_TRACE = "replace_with_trace"`.
2. Add a pure strategy `ReplaceWithTraceCompaction(BaseCompaction)` constructed from a rendered `trace_text` plus scope/retention/placement options; `compact(messages)` returns a new message tuple with the selected region replaced by one trace message.
3. The strategy **always preserves `role == "system"` messages** (placement `system_suffix` may additionally append the trace to the system block).
4. **Scope** selects which non-system, non-protected region is replaced; supported scopes:
   - `all_non_system` — replace every non-system, non-protected message.
   - `oldest_n_groups` — replace the oldest `n` logical groups.
   - `oldest_percentage` — replace the oldest `ceil(percentage * groups)` groups.
   - `middle_keep_bookends` — keep the first user message and the recent tail, replace the middle.
5. **Retention** protects messages from replacement (combinable):
   - `keep_last_groups: int` — keep the newest K tool-call/result groups verbatim (group-aware).
   - `keep_last_user: bool` — always keep the most recent `user` message.
   - `keep_pinned: bool` — keep messages with `metadata["pinned"]` truthy.
   - `keep_errors: bool` — keep `tool_result` messages with `metadata["status"] == "error"`.
   - `keep_active_branch: str | None` — keep messages on the active snapshot branch (and unbranched messages).
6. **Group-awareness:** the strategy must never keep a `tool_result` without its preceding `tool_call`, nor drop one half of a pair (reuse the `_groups()` pairing logic already in `strategies.py`).
7. **Placement** controls where the trace lands (one message):
   - `summary` (default) — an `assistant` message with `kind="summary"`, inserted at the start of the replaced region's position (right after the system block).
   - `system_suffix` — appended as an additional `system` message at the end of the system block.
   - `synthetic_user` — a `user` message ("Continual trace (state so far): …").
8. The injected trace message carries `metadata["compaction"] == "replace_with_trace"` and a stable `metadata["trace_marker"]` used for **idempotency**: if a prior trace message with that marker is present in the replaced region, it is dropped and re-created (never stacked).
9. If `trace_text` is empty/whitespace, the strategy returns the input **unchanged** (no empty trace injection).

**Renderer (Family C)**
10. Add a pure `TraceArtifactRenderer` that renders a `Mapping[str, Any]` artifact to Markdown (heading per field; scalars inline; arrays as bullet lists; nested objects as `key: value`), matching the style of `ProgressLog.to_markdown`.
11. `fields: Sequence[str] | None` — render only the selected schema fields, in the given order (field subset).
12. `max_chars: int | None` — truncate the rendered text to the first N chars with an explicit `…[trace truncated {count} chars]` marker (accounting for marker length).
13. `array_head: int | None`, `array_tail: int | None` — for long array fields, keep first/last entries with an `…[N omitted]…` elision.
14. `max_tokens: int | None` + `token_counter` — trim the rendered text to a token budget by dropping **oldest array entries first**, then truncating, deterministically.
15. `is_empty(artifact)` — returns `True` when the artifact is `None`, empty, or every value is `None`/empty-collection/empty-string (the cold-start check).

**Engine wiring**
16. `engine._build_strategy` constructs `ReplaceWithTraceCompaction` for `REPLACE_WITH_TRACE`, reading `trace_text`, `scope`, `n`, `percentage`, `keep_last_groups`, `keep_last_user`, `keep_pinned`, `keep_errors`, `keep_active_branch`, `placement` from `options`.

**Middleware (the bridge; Families A/B/C/E/F/G surface)**
17. Add `TraceReplacementCompactionMiddleware(AgentMiddleware)` whose `before_model_call`:
    a. resolves the artifact from one of: injected `artifact`, async `artifact_provider` callback, or `run_state[run_state_key][trace_key]` (default `("__result_metadata__", "trace")`);
    b. if the artifact `is_empty`, applies the configured `fallback` (a `CompactionMode` + options, default no-op) and returns — **never** replaces real history with an empty trace;
    c. renders the artifact with the configured Family-C render params;
    d. calls `engine.compact_provider_messages(provider_messages, mode=REPLACE_WITH_TRACE, options={trace_text, scope, retention, placement})`;
    e. optionally applies a `compose_after` `CompactionMode` to the result (Family F composition, e.g. strip kept tool results);
    f. returns `continue_(transform=MiddlewareTransform(provider_messages=..., metadata={...}))`.
18. The middleware is **fail-open** (`fail_closed = False`): any failure records metadata and leaves history untouched.
19. The middleware exposes named classmethod constructors, one per method:
    - Family A: `replace_all_with_trace`, `keep_recent_tail`, `replace_oldest_n_iterations`, `replace_oldest_percentage`, `replace_middle_keep_bookends`, `replace_keep_last_user`.
    - Family B: `trace_as_summary` (default), `trace_as_system_suffix`, `trace_as_synthetic_user`.
    - Family C: `trace_truncated_chars`, `trace_field_subset` (render params also accepted on every constructor via kwargs).
    - Family E: `stale_ok` (default), `with_refresh(refresh_callback=…)`.
    - Family F: `trace_fallback_to_mechanical(fallback_mode=…)`, `trace_plus_strip_tool_results`.
    - Family G: `replace_keep_pinned`, `replace_keep_errors`, `replace_keep_active_branch`.
20. Add `TraceSummaryTailCompactionMiddleware(TraceReplacementCompactionMiddleware)` for Family F `trace_then_summarize_tail`: replaces the old region with the trace and summarizes the kept tail using an **injected `Summarizer`** (no hidden provider calls).
21. `with_refresh`: when a `refresh_callback: Callable[[MiddlewareContext], Awaitable[Mapping]]` is configured, the middleware awaits it to obtain a fresh artifact before rendering; otherwise it uses the stale `run_state` artifact.
22. All new constructors validate their numeric/string options eagerly (`__init__`), raising `ValueError`/`ConfigurationError` before runtime (matching existing `_validate_options`).

**Public surface**
23. Re-export the new middleware through `vidbyte/middleware/builtins/context_compaction.py`, `vidbyte/middleware/builtins/__init__.py`, and `vidbyte/middleware/__init__.py`.
24. Export `REPLACE_WITH_TRACE` (via `CompactionMode`) and `TraceArtifactRenderer` through `vidbyte/middleware/compaction/__init__.py`; surface the renderer on `vidbyte.context.compaction` if user-facing.

### Non-Functional Requirements
- **Determinism:** strategy + renderer produce identical output for identical input; no clocks, no RNG, no I/O.
- **Backward compatible:** no behavior change for agents that do not attach the new middleware; existing modes untouched.
- **Fail-open:** trace-compaction failures never abort or corrupt a run.
- **Provider-safe:** output never contains an orphaned tool message.
- **Bounded:** rendered trace is bounded by char/token/field limits; the injected message count is exactly one (plus optional summarized tail).
- **No new dependencies.**
- **Observability:** every application emits `CompactionStats` + transform metadata (`mode`, `scope`, `before_count`, `after_count`, `trace_chars`, `fallback_used`).

---

## 5. High-Level Design

Three layers, strict boundaries:

```
                       run_state["__result_metadata__"]["trace"]   (produced elsewhere, on ct-agent branch)
                                          │  (or injected artifact / async refresh_callback)
                                          ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ TraceReplacementCompactionMiddleware.before_model_call  (IMPURE seam) │
   │   1. resolve artifact   2. is_empty? → fallback   3. render            │
   │   4. engine.compact_provider_messages(REPLACE_WITH_TRACE, options)     │
   │   5. compose_after (optional)   6. continue_(transform=...)            │
   └───────────────┬───────────────────────────────────┬───────────────────┘
                   │ trace_text (str)                    │ uses
                   ▼                                     ▼
   ┌───────────────────────────┐        ┌───────────────────────────────────┐
   │ TraceArtifactRenderer     │        │ ContextCompactionEngine            │
   │ (PURE: artifact → text)   │        │ _build_strategy(REPLACE_WITH_TRACE)│
   │ fields/max_chars/array/   │        └───────────────┬───────────────────┘
   │ max_tokens/is_empty       │                        │ constructs
   └───────────────────────────┘                        ▼
                                        ┌───────────────────────────────────┐
                                        │ ReplaceWithTraceCompaction         │
                                        │ (PURE: messages + trace_text →     │
                                        │  messages) scope/retention/placement│
                                        └───────────────────────────────────┘
```

**Key decisions:**

1. **One mode, many params.** A single `REPLACE_WITH_TRACE` mode with scope/retention/placement options, surfaced as classmethod presets — per the skill's "low-level behavior belongs on the config object; the preset is the obvious default, not a catalog of every combination." Minting 25 enum values would be the wrong factoring.
2. **Renderer separate from strategy.** Family C (how much trace) is orthogonal to Families A/B/G (where it goes). Splitting keeps each pure and independently testable; the middleware composes them.
3. **Middleware owns all impurity.** Only the middleware touches `run_state`, the optional `Summarizer`, and the optional `refresh_callback`. The strategy receives a finished string. This preserves the determinism contract that all other strategies rely on and keeps the engine's provider round-trip intact.
4. **Decoupled producer.** The artifact is a contract (`run_state` key + JSON-like dict). This is the same "generic, feature-agnostic lift of `run_state['__result_metadata__']`" pattern the runtime itself uses, so consuming it the same way is consistent — and it unblocks shipping on `main`.
5. **Group-aware retention.** Reuse the existing `_groups()` pairing so tails never orphan tool results.

---

## 6. Detailed Design

### 6.1 `CompactionMode.REPLACE_WITH_TRACE`

**File:** `vidbyte/middleware/compaction/base.py`
**Type:** Modified

#### What it does
Adds one enum member identifying the trace-replacement strategy.

#### Interface / API
```python
class CompactionMode(str, Enum):
    ...
    REPLACE_WITH_TRACE = "replace_with_trace"
```

#### Edge Cases & Error Handling
- Unknown string modes still raise via `CompactionMode(str(mode))` in `engine._coerce_mode`.

---

### 6.2 `TraceArtifactRenderer`

**File:** `vidbyte/middleware/compaction/trace_render.py`
**Type:** New file

#### What it does
Pure renderer: turns a trace artifact dict into bounded Markdown text, and detects empty artifacts.

#### Interface / API
```python
class TraceArtifactRenderer:
    def __init__(self, *, fields: Sequence[str] | None = None, max_chars: int | None = None, array_head: int | None = None, array_tail: int | None = None, max_tokens: int | None = None, token_counter: TokenCounter | None = None, title: str = "Continual Trace") -> None: ...
    def render(self, artifact: Mapping[str, Any]) -> str: ...
    @staticmethod
    def is_empty(artifact: Mapping[str, Any] | None) -> bool: ...
```

#### Logic / Algorithm
`render`:
1. `_select_fields` — keep only `fields` (in order) when provided, else all keys in artifact order.
2. `_render_field` — heading `## {name}`; scalar → one line; array → bullet list with `array_head`/`array_tail` elision; mapping → `- key: value` lines.
3. `_apply_token_budget` — if `max_tokens` set, drop oldest array entries (front of each list) until under budget, re-rendering deterministically.
4. `_apply_char_limit` — if `max_chars` set and exceeded, cut to `max_chars - len(marker)` and append `…[trace truncated {count} chars]`.

`is_empty`: `True` if artifact falsy, or every value is `None`/empty-collection/empty/whitespace string.

#### Edge Cases & Error Handling
- Non-string/`non-listed` values → `str(value)`.
- `fields` naming a key absent from the artifact → skipped (no crash); `[Silent Failure]` test guards this.
- `max_chars` smaller than the marker length → returns just a bounded marker (no negative slice).
- Mixed-type arrays render each element via `str`.

---

### 6.3 `ReplaceWithTraceCompaction`

**File:** `vidbyte/middleware/compaction/strategies.py`
**Type:** Modified (append class + register in `__all__`)

#### What it does
Pure strategy that replaces a selected region of non-system history with one trace message, preserving system messages, protected messages, and provider tool-group boundaries.

#### Interface / API
```python
class ReplaceWithTraceCompaction(BaseCompaction):
    def __init__(self, trace_text: str, *, scope: str = "all_non_system", n: int = 0, percentage: float = 0.0, keep_last_groups: int = 0, keep_last_user: bool = False, keep_pinned: bool = False, keep_errors: bool = False, keep_active_branch: str | None = None, placement: str = "summary", trace_marker: str = "continual_trace") -> None: ...
    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]: ...
```

#### Logic / Algorithm
1. `_short_circuit` — if `trace_text.strip()` is empty, return `tuple(messages)` unchanged.
2. `_partition_system` — split into `system` and `non_system` (preserving order/index).
3. `_protected_indices` — compute the set of `non_system` indices protected by retention flags: last-K groups (group-aware), last user message, pinned, error tool-results, active branch.
4. `_replaced_indices` — among `non_system` indices **not** protected, select the region per `scope` (all / oldest-n-groups / oldest-percentage / middle-keep-bookends). Existing trace messages bearing `trace_marker` are always added to the replaced set (idempotency).
5. `_build_trace_message` — one `ContextMessage` per `placement` with `kind`/`role` set and `metadata={"compaction": "replace_with_trace", "trace_marker": marker, "original_count": k}`.
6. `_assemble` — rebuild: system block (+ trace if `system_suffix`), then non-system messages in original order with the replaced region collapsed to the single trace message at the position of the first replaced index (for `summary`/`synthetic_user`).

#### Edge Cases & Error Handling
- No non-system messages → returns system (+ trace via configured placement) so an empty conversation still yields a valid window. `[Edge Case]`
- `scope="oldest_n_groups"` with `n` ≥ group count → replaces all non-protected. `[Edge Case]`
- Retention covering the entire region → nothing to replace → no trace injected, input returned (avoids a pointless trace message). `[Silent Failure]` test guards this.
- Tool pair on the protection boundary → group logic keeps/drops both halves together. `[Hidden Failure]`
- Invalid `scope`/`placement`/`percentage` → `ValueError` at construction.

---

### 6.4 Engine wiring

**File:** `vidbyte/middleware/compaction/engine.py`
**Type:** Modified

#### Interface / API
```python
if mode is CompactionMode.REPLACE_WITH_TRACE:
    return ReplaceWithTraceCompaction(
        str(options.get("trace_text", "")),
        scope=str(options.get("scope", "all_non_system")),
        n=int(options.get("n", 0)),
        percentage=float(options.get("percentage", 0.0)),
        keep_last_groups=int(options.get("keep_last_groups", 0)),
        keep_last_user=bool(options.get("keep_last_user", False)),
        keep_pinned=bool(options.get("keep_pinned", False)),
        keep_errors=bool(options.get("keep_errors", False)),
        keep_active_branch=options.get("keep_active_branch"),
        placement=str(options.get("placement", "summary")),
    )
```

#### Edge Cases & Error Handling
- Missing `trace_text` → empty string → strategy short-circuits (no-op). Safe by construction.

---

### 6.5 `TraceReplacementCompactionMiddleware`

**File:** `vidbyte/middleware/compaction/context_compaction.py`
**Type:** Modified (append classes)

#### What it does
The impure bridge: resolves the trace artifact, guards the empty case, renders it, and applies the replacement to provider messages on `before_model_call`. Exposes every method (Families A/B/C/E/F/G) as classmethod constructors.

#### Interface / API
```python
class TraceReplacementCompactionMiddleware(AgentMiddleware):
    name = "TraceReplacementCompactionMiddleware"
    fail_closed = False

    def __init__(self, *, scope: str = "all_non_system", placement: str = "summary", run_state_key: str = "__result_metadata__", trace_key: str = "trace", artifact: Mapping[str, Any] | None = None, artifact_provider: Callable[[MiddlewareContext], Mapping[str, Any]] | None = None, refresh_callback: Callable[[MiddlewareContext], Awaitable[Mapping[str, Any]]] | None = None, fallback_mode: CompactionMode | str | None = None, fallback_options: Mapping[str, Any] | None = None, compose_after: CompactionMode | str | None = None, compose_after_options: Mapping[str, Any] | None = None, render: Mapping[str, Any] | None = None, **options: Any) -> None: ...

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...

    # Family A
    @classmethod
    def replace_all_with_trace(cls, **kw) -> "TraceReplacementCompactionMiddleware": ...
    @classmethod
    def keep_recent_tail(cls, keep_last_groups: int = 2, **kw) -> "...": ...
    @classmethod
    def replace_oldest_n_iterations(cls, n: int, **kw) -> "...": ...
    @classmethod
    def replace_oldest_percentage(cls, percentage: float, **kw) -> "...": ...
    @classmethod
    def replace_middle_keep_bookends(cls, keep_last_groups: int = 2, **kw) -> "...": ...
    @classmethod
    def replace_keep_last_user(cls, **kw) -> "...": ...
    # Family B
    @classmethod
    def trace_as_summary(cls, **kw) -> "...": ...
    @classmethod
    def trace_as_system_suffix(cls, **kw) -> "...": ...
    @classmethod
    def trace_as_synthetic_user(cls, **kw) -> "...": ...
    # Family C
    @classmethod
    def trace_truncated_chars(cls, max_chars: int, **kw) -> "...": ...
    @classmethod
    def trace_field_subset(cls, fields: Sequence[str], **kw) -> "...": ...
    # Family E
    @classmethod
    def stale_ok(cls, **kw) -> "...": ...
    @classmethod
    def with_refresh(cls, refresh_callback, **kw) -> "...": ...
    # Family F
    @classmethod
    def trace_fallback_to_mechanical(cls, fallback_mode=CompactionMode.KEEP_LAST_N_MESSAGES, **kw) -> "...": ...
    @classmethod
    def trace_plus_strip_tool_results(cls, **kw) -> "...": ...
    # Family G
    @classmethod
    def replace_keep_pinned(cls, **kw) -> "...": ...
    @classmethod
    def replace_keep_errors(cls, **kw) -> "...": ...
    @classmethod
    def replace_keep_active_branch(cls, branch: str, **kw) -> "...": ...


class TraceSummaryTailCompactionMiddleware(TraceReplacementCompactionMiddleware):
    name = "TraceSummaryTailCompactionMiddleware"
    def __init__(self, *, summarizer: Summarizer, keep_last_groups: int = 2, **kw) -> None: ...
    @classmethod
    def trace_then_summarize_tail(cls, summarizer: Summarizer, keep_last_groups: int = 2, **kw) -> "...": ...
```

#### Logic / Algorithm (`before_model_call`)
1. `_resolve_artifact(ctx)` — precedence: `artifact` → `await refresh_callback(ctx)` (if set) → `artifact_provider(ctx)` → `ctx.run_state.get(run_state_key, {}).get(trace_key)`.
2. `_guard_empty` — if `TraceArtifactRenderer.is_empty(artifact)`: if `fallback_mode` set, apply it via the engine and return that transform; else return `continue_()` unchanged.
3. `_render(artifact)` — build `TraceArtifactRenderer(**render)` and render.
4. `_apply(ctx, trace_text)` — `engine.compact_provider_messages(ctx.provider_messages, mode=REPLACE_WITH_TRACE, options={trace_text, **strategy_options})`.
5. `_compose_after` — if set, run a second `compact_provider_messages` over the result.
6. Return `continue_(transform=MiddlewareTransform(provider_messages=messages, metadata={...}))`.

#### Edge Cases & Error Handling
- No `provider_messages` → `continue_()` (matches existing middleware). `[Edge Case]`
- Artifact present but empty/initial → fallback or no-op, **never** an empty-trace replacement. `[Hidden Assumption]`
- `refresh_callback` raises → fail-open: record metadata, fall back to stale `run_state` artifact. `[Hidden Failure]`
- `artifact_provider` returns non-Mapping → treated as empty → guard path. `[Silent Failure]`
- Two trace-compaction middleware in one pipeline → idempotency marker prevents stacked trace messages. `[Hidden Failure]`

---

### 6.6 Public re-exports

**Files:** `vidbyte/middleware/compaction/__init__.py`, `vidbyte/middleware/builtins/context_compaction.py`, `vidbyte/middleware/builtins/__init__.py`, `vidbyte/middleware/__init__.py`, `vidbyte/context/compaction.py`
**Type:** Modified

Add `TraceReplacementCompactionMiddleware`, `TraceSummaryTailCompactionMiddleware`, and `TraceArtifactRenderer` to imports/`__all__`/Context Protocol Headers.

---

## 7. Data Model Changes

N/A — no database or persisted schema. The only "model" change is the in-process `CompactionMode` enum (§6.1) and the documented **trace artifact contract**: a JSON-like `Mapping[str, Any]` published at `run_state["__result_metadata__"]["trace"]`, where array fields are lists and scalars are JSON scalars. This contract is consumed read-only; this PR does not define or own it.

---

## 8. API Changes

N/A — no HTTP/network API. The public Python API additions are the middleware classmethods and the renderer in §6, all additive and backward compatible.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/trace-backed-compaction-methods.md` | This design doc (first commit) |
| CREATE | `vidbyte/middleware/compaction/trace_render.py` | `TraceArtifactRenderer` (Family C, pure) |
| MODIFY | `vidbyte/middleware/compaction/base.py` | Add `REPLACE_WITH_TRACE` mode |
| MODIFY | `vidbyte/middleware/compaction/strategies.py` | Add `ReplaceWithTraceCompaction` + `__all__` |
| MODIFY | `vidbyte/middleware/compaction/engine.py` | Wire `REPLACE_WITH_TRACE` in `_build_strategy` + import |
| MODIFY | `vidbyte/middleware/compaction/context_compaction.py` | Add `TraceReplacementCompactionMiddleware` + `TraceSummaryTailCompactionMiddleware` |
| MODIFY | `vidbyte/middleware/compaction/__init__.py` | Export renderer + new middleware |
| MODIFY | `vidbyte/middleware/builtins/context_compaction.py` | Re-export new middleware |
| MODIFY | `vidbyte/middleware/builtins/__init__.py` | Register + `__all__` + header |
| MODIFY | `vidbyte/middleware/__init__.py` | Register + `__all__` |
| MODIFY | `vidbyte/context/compaction.py` | Surface renderer if user-facing |
| CREATE | `tests/test_trace_replacement_compaction.py` | Unit + integration tests (§10) |
| CREATE | `scripts/test-trace-backed-compaction-methods.py` | Phase-5 verification script |
| MODIFY | `skills/vidbyte-sdk/middleware.md` | Document the new methods in §5.1 |
| MODIFY | `README.md` | Short usage example (if compaction is documented there) |

Estimated: **3 created**, **~10 modified** (excluding the design doc and script).

---

## 10. Testing Plan

All tests use in-memory `ContextMessage`/provider dicts and fakes — no live providers. Categories labeled per case.

### Unit Tests — `TraceArtifactRenderer`
- `renders each field as a markdown heading with scalar inline` — [Edge Case]
- `renders array field as bullet list` — [Edge Case]
- `field subset keeps only requested fields in order` — [Silent Failure] (wrong field order/extra fields)
- `field subset naming an absent key does not crash` — [Hidden Assumption]
- `max_chars truncates with marker and never exceeds bound including marker` — [Silent Failure] (off-by-marker-length)
- `max_chars smaller than marker returns bounded marker, no negative slice` — [Edge Case]
- `array_head/array_tail elide middle with omitted count` — [Edge Case]
- `max_tokens drops oldest array entries first` — [Silent Failure] (drops newest by mistake)
- `is_empty true for None / {} / all-None / empty strings / empty lists` — [Hidden Assumption]
- `is_empty false when any field has content` — [Edge Case]

### Unit Tests — `ReplaceWithTraceCompaction`
- `empty trace_text returns messages unchanged` — [Hidden Assumption]
- `all_non_system keeps system, injects one trace summary` — [Edge Case]
- `system_suffix appends trace as system message` — [Edge Case]
- `synthetic_user injects trace as user role` — [Edge Case]
- `keep_last_groups keeps newest K groups verbatim` — [Edge Case]
- `keep_last_groups never orphans a tool_result from its tool_call` — [Hidden Failure]
- `oldest_n_groups with n >= group count replaces all non-protected` — [Edge Case]
- `oldest_percentage replaces ceil(percentage*groups)` — [Silent Failure] (floor vs ceil)
- `middle_keep_bookends keeps first user + recent tail` — [Edge Case]
- `keep_pinned protects pinned messages` — [Edge Case]
- `keep_errors protects error tool_results` — [Edge Case]
- `keep_active_branch keeps active branch + unbranched, drops siblings` — [Edge Case]
- `retention covering entire region injects no trace (returns input)` — [Silent Failure]
- `existing trace_marker message is replaced not stacked (idempotency)` — [Hidden Failure]
- `no non-system messages still yields valid system+trace window` — [Edge Case]
- `invalid scope/placement/percentage raise at construction` — [Hidden Assumption]

### Unit Tests — `TraceReplacementCompactionMiddleware`
- `reads artifact from run_state default key and replaces history` — [Edge Case]
- `injected artifact overrides run_state` — [Hidden Assumption]
- `empty/initial artifact triggers fallback_mode, not empty replacement` — [Hidden Assumption]
- `empty artifact with no fallback is a no-op` — [Silent Failure]
- `no provider_messages is a no-op` — [Edge Case]
- `refresh_callback supplies fresh artifact when set` — [Edge Case]
- `refresh_callback raising falls back to stale run_state artifact (fail-open)` — [Hidden Failure]
- `artifact_provider returning non-Mapping is treated as empty` — [Silent Failure]
- `compose_after strips kept tool results after replacement` — [Edge Case]
- `each Family A/B/C/G classmethod constructs the expected options` — [Edge Case]
- `middleware never raises out of before_model_call (fail_closed False)` — [Hidden Failure]
- `transform metadata reports scope, before/after counts, fallback_used` — [Silent Failure]

### Unit Tests — `TraceSummaryTailCompactionMiddleware`
- `trace_then_summarize_tail replaces old region and summarizes tail via injected summarizer` — [Edge Case]
- `raises if summarizer is None` — [Hidden Assumption]
- `does not perform any provider call itself (uses injected summarizer only)` — [Hidden Assumption]

### Integration Tests
- Full `AgentRuntime` run with a `FakeRunner` + a middleware that writes a trace dict to `run_state["__result_metadata__"]["trace"]` on `after_iteration`, then `TraceReplacementCompactionMiddleware` on `before_model_call`; assert the second model call's `provider_messages` are `[system, trace_summary]`. Mock: runner + the producer middleware (stand-in for the real `ContinualTraceMiddleware`). Surfaces the **silent failure** where two middleware do not share `run_state` (they must — same dict). [Hidden Failure]
- Pipeline ordering: producer (`after_iteration`) writes before consumer (`before_model_call`) reads on the next iteration; assert staleness-by-one is the observed behavior, not a crash. [Hidden Assumption]
- Cold start: run where the producer has not yet written → consumer no-ops/falls back; real history preserved. [Hidden Assumption]

### Manual / QA Test Cases
1. Given an agent with a populated trace artifact and `replace_all_with_trace`, when a model call occurs, then the window is `[system, trace summary]` and no tool pair is orphaned. — [Edge Case]
2. Given `keep_recent_tail(keep_last_groups=2)` with a trailing `tool_call`+`tool_result`, when compaction runs, then both halves of the last pair survive verbatim. — [Hidden Failure]
3. Given an empty/initial artifact and `trace_fallback_to_mechanical(KEEP_LAST_N_MESSAGES, n=6)`, when a model call occurs, then the last 6 messages are kept and **no** empty trace is injected. — [Hidden Assumption]
4. Given `trace_truncated_chars(max_chars=200)` over a large artifact, when rendered, then the injected message is ≤ 200 chars including the truncation marker. — [Silent Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `vidbyte.middleware.compaction` (engine/strategies/base) | in-repo | host layer for the new strategy/mode | Low |
| Continual-trace producer (`ContinualTraceMiddleware`) | `feat/ct-agent-v2` (not on `main`) | publishes the artifact this consumes | **High — not present on `main`**; mitigated by the decoupled contract + injected artifact path |
| `Summarizer` protocol | in-repo | `trace_then_summarize_tail` tail summary | Low (injected, optional) |

No third-party or network dependencies added.

---

## 12. Rollout & Deployment

- **Feature flag:** none needed — inert unless a developer attaches the middleware.
- **Breaking change:** no. Purely additive.
- **Producer coupling:** until `feat/ct-agent-v2` merges, the `run_state` source is unpopulated; the middleware no-ops/falls back, so attaching it is safe but inactive. With an injected `artifact`/`artifact_provider`, it is fully usable today (and that is how tests exercise it).
- **Deployment order:** ship independently; it activates automatically once the producer publishes the artifact. Recommend a follow-up note in the producer PR to confirm the `run_state` key/shape match this consumer's contract.
- **Rollback:** remove the middleware from agent construction; revert the additive files. No data migration.

---

## 13. Open Questions

- [ ] **Producer dependency (highest priority).** Confirm we ship this **decoupled** on `main` now (consuming the `run_state` contract + supporting injected artifacts), rather than waiting to build it on `feat/ct-agent-v2`. Recommended: ship decoupled. If instead you want it built directly on the ct-agent branch so it is wired end-to-end immediately, the worktree/branch base changes.
- [ ] **`run_state` key/shape.** Confirm the contract `run_state["__result_metadata__"]["trace"]` (dict; arrays as lists) matches what the producer publishes. If the producer key changes, only the middleware defaults change.
- [ ] **"First N chars of the trace" interpretation.** Implemented as `trace_truncated_chars` = truncate the rendered trace payload to N chars (not "replace the first N messages"). Confirm this reading.
- [ ] **Full-replace safety without a trigger.** With Family D excluded, `replace_all_with_trace` applied every `before_model_call` will also drop the newest user turn before the model sees it. Recommended default: `replace_all_with_trace` sets `keep_last_user=True` so the live ask always survives. Confirm, or accept that callers must compose retention themselves.
- [ ] **`with_refresh` on `main`.** Implemented as an injected async `refresh_callback` seam (testable with a fake). The real wiring (calling the trace agent synchronously) is only possible once the producer exists — acceptable as a deferred wiring, or should `with_refresh` be omitted until then?

---

## 14. Alternatives Considered

### Alternative 1: A separate `CompactionMode` per method (25 enum values)
- What: `REPLACE_ALL_WITH_TRACE`, `KEEP_RECENT_TAIL_TRACE`, `TRACE_AS_SYSTEM_SUFFIX`, …
- Why rejected: Enum sprawl; the skill explicitly says low-level behavior belongs on the config object and the preset is the obvious default, "not a catalog of every possible parameter combination." One mode + params + classmethod presets is the idiomatic factoring.

### Alternative 2: Let the strategy read `run_state` directly
- What: `ReplaceWithTraceCompaction` reaches into the trace artifact itself.
- Why rejected: Breaks the purity/determinism contract every other strategy upholds and the engine's provider round-trip; makes the strategy untestable without a runtime. The middleware is the correct impure seam.

### Alternative 3: Fold the behavior into `ContinualTraceMiddleware`
- What: Have the trace producer also inject itself into the window.
- Why rejected: Violates the producer's explicit "never write the trace into the context window" invariant for everyone; couples consumer to producer. A separate, opt-in consumer middleware keeps the default invariant intact.

### Alternative 4: Build on `feat/ct-agent-v2` instead of `main`
- What: Implement where the producer already exists, wired end-to-end.
- Why rejected (tentatively — see Open Questions): The user asked for `vidbyte-sdk` (`main`). The decoupled contract delivers the same end state and ships sooner; it auto-activates on merge. Revisit if end-to-end wiring is required in this PR.

---

END OF DESIGN DOC.

---

## Summary

**Files:** 3 created (`trace_render.py`, the test, the verification script) + this design doc; ~10 modified (base/strategies/engine/context_compaction + 5 re-export points + skill/README).

**Key risks / open questions:**
1. **The trace producer does not exist on `main`** — mitigated by the decoupled `run_state` contract + injected-artifact path (Open Question #1, recommended: ship decoupled).
2. Full-replace without a trigger (Family D excluded) can starve the model of the live user turn — recommended mitigation: `keep_last_user=True` by default on full-replace.
3. `run_state` key/shape must match the producer's contract.

**No implementation has begun.** Please review and explicitly approve (or adjust the open questions) before I proceed to Phase 3 (worktree branch `feat/trace-backed-compaction-methods`) and Phase 4 (implementation).
