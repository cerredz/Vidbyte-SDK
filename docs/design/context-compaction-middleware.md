# Design Doc: Context Compaction Middleware

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-04
**Last Updated:** 2026-06-04

---

## 1. Overview

Move Vidbyte SDK context compaction from a model-visible tool and agent `algorithm=` option into deterministic middleware built-ins. The refactor will expose prebuilt middleware for all current `ContextCompactionTool` modes, preserve existing `ContextWindow.preset.compact_tool_outputs` and `ContextWindow.preset.no_raw_tool_outputs` behavior through compatibility middleware, and keep `ContextCompactionTool` as a legacy wrapper over shared compaction logic instead of a separate implementation path.

---

## 2. Goals & Non-Goals

### Goals

- Move all 11 current `ContextCompactionTool` modes into middleware-level behavior:
  - `clear_except_system_and_log`
  - `remove_all_tool_calls`
  - `remove_last_n_tool_calls`
  - `remove_tool_call_percentage`
  - `summarize_range`
  - `keep_last_n_messages`
  - `summarize_oldest_n`
  - `strip_tool_result_bodies`
  - `deduplicate_tool_calls`
  - `summarize_by_topic_blocks`
  - `truncate_tool_results`
- Add public prebuilt middleware classes under `vidbyte.middleware.builtins`.
- Add a narrow middleware transform contract so middleware can rewrite model-visible tool results, provider messages, and system text at explicit runtime hook points.
- Preserve raw tool results in final runtime metadata even when middleware hides, strips, truncates, or otherwise compacts model-visible output.
- Preserve existing `ContextWindow.preset.compact_tool_outputs` and `ContextWindow.preset.no_raw_tool_outputs` behavior by translating those presets into compatibility middleware inside the direct text runtime.
- Refactor `ContextCompactionTool` to delegate to shared compaction logic, keeping its import path and tool schema available for backward compatibility.
- Update README and SDK skill docs so new examples recommend `middleware=[...]` for compaction.
- Add focused unit tests, integration tests, and an executable script that covers every behavior in this design.

### Non-Goals

- Do not remove `ContextCompactionTool` in this PR.
- Do not add middleware support to non-linear runtimes; current `BaseAgent` already rejects middleware and non-default context-window algorithms for non-linear runtimes.
- Do not implement implicit provider calls inside middleware for summarization. Summarization middleware must use an injected summarizer object/callable.
- Do not add third-party dependencies.
- Do not change provider tool-call parsing or provider tool schema formatting.
- Do not persist compacted context to a database or external memory service.
- Do not change agent history storage semantics outside the model-visible runtime message window.

---

## 3. Background & Context

- The README currently documents context-window presets with `algorithm=ContextWindow.preset.no_raw_tool_outputs`, then documents middleware as deterministic, non-model-visible runtime hooks.
- The README also lists `vidbyte.tools.builtins.context.ContextCompactionTool` under advanced built-ins, which makes compaction appear as a model-visible tool capability.
- Current direct text execution lives in `vidbyte/agents/runtime.py`. It keeps an internal `messages: list[dict[str, Any]]`, calls middleware hooks, executes tools, applies `self.algorithm.model_visible_tool_result(...)`, formats the visible tool result, and appends it to `messages`.
- Current middleware contracts live in `vidbyte/lib/dataclasses/middleware.py`. They allow control-flow actions only: continue, sleep, abort, deny tool, and retry. There is no explicit transform effect.
- Current middleware pipeline dispatch lives in `vidbyte/middleware/pipeline.py`. It records non-continue decisions and returns a final continue decision when all middleware continue. It does not currently preserve continue-decision metadata or transforms.
- Current compaction logic lives in `vidbyte/tools/builtins/context/compaction.py` and operates on `ContextState.messages()` / `replace_messages(...)`. Some modes are pure transforms; summarization modes require an injected summarizer.
- Current `ContextWindowAlgorithm` tool-result admission logic lives in `vidbyte/context/algorithms/tool_results.py` and overlaps with `truncate_tool_results`, `strip_tool_result_bodies`, and hide/no-raw behavior.
- The repo is Python 3.11+, uses stdlib `unittest`, has no external runtime dependencies for this change, and follows a class-first style with public exports in package `__init__.py` files.
- The current checkout is `main` and contains one unrelated untracked file, `docs/design/handoff-primitive-catalog.md`; this refactor must not modify or rely on that file.

---

## 4. Requirements

### Functional Requirements

1. `vidbyte.context.compaction` must define the shared compaction implementation used by both middleware and `ContextCompactionTool`.
2. `CompactionMode` must remain import-compatible from `vidbyte.tools.builtins.context`.
3. `ContextCompactionTool` must keep the existing `compact_context` tool name, parameter schema, and `execute(...)` behavior while delegating mode implementation to the shared engine.
4. `MiddlewareTransform` must allow middleware to return optional transformed `model_visible_tool_result`, `provider_messages`, and `system` values.
5. `MiddlewareDecision.continue_(...)` must accept an optional `transform`.
6. `MiddlewarePipeline` must preserve and combine transform values from continue decisions in middleware order.
7. Later middleware in the same hook must see the original `MiddlewareContext`, not a silently mutated context object.
8. When multiple middleware return the same transform field for a hook, the later middleware must win for that field.
9. `AgentRuntime._invoke_with_middleware(...)` must apply `before_model_call` transforms to a per-call copy of call options before invoking the runner.
10. `AgentRuntime._process_tool_call(...)` must apply `after_tool_call` transform `model_visible_tool_result` before formatting the tool result into provider messages.
11. Runtime metadata must preserve the original `ToolResult` in `ToolCallContext.result` even if the model-visible result is compacted.
12. `ToolResultCompactionMiddleware` must support tool-output admission modes equivalent to raw, truncate, strip, and hide.
13. `ToolResultCompactionMiddleware.truncate(max_chars=..., truncation_indicator=...)` must preserve current `truncate_tool_results` semantics for tool-result bodies.
14. `ToolResultCompactionMiddleware.strip(...)` must preserve current `strip_tool_result_bodies` placeholder and metadata semantics.
15. `ToolResultCompactionMiddleware.hide(...)` must preserve current `ContextWindow.preset.no_raw_tool_outputs` model-visible placeholder semantics.
16. `MessageHistoryCompactionMiddleware` must support `clear_except_system_and_log`, `remove_all_tool_calls`, `remove_last_n_tool_calls`, `remove_tool_call_percentage`, `keep_last_n_messages`, and `deduplicate_tool_calls` over provider messages.
17. `SummaryCompactionMiddleware` must support `summarize_range`, `summarize_oldest_n`, and `summarize_by_topic_blocks` with an injected summarizer.
18. Summary middleware construction must fail fast if a summarization mode is requested without a summarizer.
19. Provider message compaction must preserve provider message dictionaries where possible and only rewrite selected message content/order.
20. Provider message compaction must classify OpenAI, Anthropic, and Gemini formatted tool-result messages well enough to avoid dropping ordinary assistant/user messages accidentally.
21. `ContextWindow.preset.compact_tool_outputs` must be translated into `ToolResultCompactionMiddleware.truncate(max_chars=algorithm.max_tool_result_chars)`.
22. `ContextWindow.preset.no_raw_tool_outputs` and `hide_tool_outputs` must be translated into `ToolResultCompactionMiddleware.hide()`.
23. The runtime must stop calling `self.algorithm.model_visible_tool_result(...)` for ordinary tool-result admission after compatibility middleware is wired.
24. Runtime algorithms such as Reflexion and Multi-Provider Agentic Grader must continue to dispatch through `AgentRuntimeContextAlgorithms`.
25. Existing non-default context-window algorithm validation for non-linear runtimes must remain unchanged.
26. Public exports must make new middleware available from `vidbyte.middleware.builtins`, `vidbyte.middleware`, and root `vidbyte`.
27. README examples must recommend compaction middleware instead of `ContextCompactionTool` for new user-facing code.
28. Skill docs must describe compaction middleware as the preferred implementation path.
29. Existing tests for `ContextCompactionTool` must continue to pass.
30. New tests must prove middleware compaction affects model-visible follow-up calls, not just final metadata.

### Non-Functional Requirements

- **Compatibility:** Existing imports of `CompactionMode`, `ContextCompactionTool`, and `ContextWindow.preset.no_raw_tool_outputs` must keep working.
- **Security:** Middleware compaction must not expose raw tool outputs in model-visible messages when hide/strip modes are configured.
- **Reliability:** Middleware transform handling must fail closed through the existing middleware exception policy.
- **Observability:** Compacted outputs must carry metadata describing compaction mode, original size, truncated size, hidden status, or removed counts where applicable.
- **Performance:** Pure compactions must be O(n) over runtime messages or tool-result length and avoid schema regeneration.
- **Testability:** All compaction engines and middleware classes must be testable with fake messages, fake tools, fake runners, and fake summarizers.
- **Dependency control:** Use only the Python standard library and current SDK dependencies.
- **API clarity:** New public classes should be explicit and discoverable rather than a single kitchen-sink middleware constructor.

---

## 5. High-Level Design

The refactor adds a shared compaction engine under `vidbyte.context.compaction`, then exposes middleware wrappers around that engine. The engine owns `CompactionMode`, provider-message classification, `ContextMessage` transforms, `ToolResult` transforms, progress-log rendering, and summarization dispatch. The legacy `ContextCompactionTool` becomes a compatibility adapter that parses tool-call arguments, invokes the shared engine against its injected `ContextState`, and returns the same success/error `ToolResult` shape as today.

Middleware gains a narrow transform effect. Instead of letting middleware mutate runtime internals directly, middleware returns `MiddlewareDecision.continue_(transform=MiddlewareTransform(...))`. The runtime applies those transforms only at explicit hook boundaries. `after_tool_call` can replace the model-visible tool result before provider formatting. `before_model_call` can replace the model-visible provider messages and/or system string before the runner receives call options.

The existing context-window tool-result admission presets become compatibility conveniences. `AgentRuntime` will append admission middleware derived from the configured `ContextWindowAlgorithm` for `compact_tool_outputs`, `hide_tool_outputs`, and `no_raw_tool_outputs`. Runtime algorithms such as Reflexion and Multi-Provider Agentic Grader remain on the `ContextWindow` path because they control full runtime flow rather than simple compaction.

```text
Agent(...)
  -> BaseAgent._runtime()
  -> AgentRuntime(..., middleware=[user middleware], algorithm=ContextWindow.preset.no_raw_tool_outputs)
  -> AgentRuntime creates MiddlewarePipeline([user middleware, compatibility compaction middleware])
  -> tool executes and raw ToolResult is stored in ToolCallContext
  -> after_tool_call middleware returns transformed model-visible ToolResult
  -> ToolsFormatter formats transformed result into provider messages
  -> before_model_call middleware may compact provider messages/system
  -> runner receives compacted model-visible context
```

Key design decisions:

- Use middleware transforms instead of direct mutation so compaction remains deterministic and auditable.
- Keep raw `ToolCallContext.result` unchanged so safety/audit metadata is not lost.
- Keep `ContextCompactionTool` as a wrapper for compatibility, but move its behavior to shared code to prevent logic drift.
- Implement summarization compaction only with an injected summarizer so middleware does not perform hidden provider calls.

---

## 6. Detailed Design

### 6.1 Shared Context Compaction Engine

**File(s):** `vidbyte/context/compaction.py`
**Type:** New file

#### What it does

Defines the shared compaction contracts and pure implementation used by middleware and `ContextCompactionTool`.

#### Interface / API

```python
class CompactionMode(str, Enum): ...
class Summarizer(Protocol): ...
@dataclass(frozen=True, slots=True)
class CompactionStats: ...
class ContextCompactionEngine: ...
```

Representative methods:

```python
class ContextCompactionEngine:
    def __init__(self, *, summarizer: Summarizer | None = None) -> None: ...
    async def compact_messages(self, messages: Sequence[ContextMessage], *, mode: CompactionMode, options: Mapping[str, Any] | None = None) -> tuple[tuple[ContextMessage, ...], CompactionStats]: ...
    def compact_tool_result(self, call: ToolCall, result: ToolResult, *, mode: CompactionMode, options: Mapping[str, Any] | None = None) -> tuple[ToolResult, CompactionStats]: ...
    async def compact_provider_messages(self, messages: Sequence[Mapping[str, Any]], *, mode: CompactionMode, options: Mapping[str, Any] | None = None) -> tuple[tuple[dict[str, Any], ...], CompactionStats]: ...
```

#### Logic / Algorithm

1. Move `CompactionMode` from `tools/builtins/context/compaction.py` into this module.
2. Move the current private compaction helpers into `ContextCompactionEngine` methods:
   - `_clear_except_system_and_log`
   - `_remove_last_n`
   - `_remove_percentage`
   - `_keep_last_n_messages`
   - `_strip_tool_result_bodies`
   - `_truncate_tool_results`
   - `_deduplicate_tool_calls`
   - `_summarize_range`
   - `_summarize_oldest_n`
   - `_summarize_by_topic_blocks`
   - `_progress_log`
3. Add provider-message conversion helpers that convert provider dictionaries into `ContextMessage` records with metadata carrying the original message.
4. Compact converted messages through the same engine.
5. Convert compacted messages back to provider dictionaries. If a message has an original provider dictionary and only `content` changed, update only content-like fields. If a message is a summary, emit a standard assistant/user message appropriate to the provider-neutral runtime shape.
6. Return `CompactionStats` with counts and mode metadata for observability.

#### Edge Cases & Error Handling

- Unknown mode raises `ValueError` for middleware callers and is converted to `ToolResult.error(...)` by `ContextCompactionTool`.
- Negative `max_chars`, negative `n`, or invalid percentage values return errors through wrapper classes or raise `ValueError` at middleware construction.
- Summarization modes without a summarizer raise `ValueError` in middleware construction and return tool errors in `ContextCompactionTool`.
- Empty message lists return empty message lists and zero counts.
- Provider messages with unknown shapes are classified as ordinary messages and preserved.

---

### 6.2 Middleware Transform Dataclasses

**File(s):** `vidbyte/lib/dataclasses/middleware.py`, `vidbyte/lib/dataclasses/__init__.py`
**Type:** Modified

#### What it does

Adds an explicit transform payload to middleware decisions while preserving existing control-flow semantics.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class MiddlewareTransform:
    model_visible_tool_result: ToolResult | None = None
    provider_messages: Sequence[Mapping[str, Any]] | None = None
    system: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class MiddlewareDecision:
    action: MiddlewareAction = MiddlewareAction.CONTINUE
    reason: str | None = None
    sleep_seconds: float = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)
    transform: MiddlewareTransform | None = None
```

#### Logic / Algorithm

1. Add `MiddlewareTransform`.
2. Add an optional `transform` field to `MiddlewareDecision`.
3. Extend `MiddlewareDecision.continue_(metadata=None, transform=None)`.
4. Leave `sleep`, `abort`, `deny_tool`, and `retry` signatures compatible except for optional transform only where needed by design. Initial implementation should only permit transforms on continue decisions.
5. Extend `MiddlewareContext` with optional read-only fields:
   - `provider_messages: Sequence[Mapping[str, Any]] = ()`
   - `system: str | None = None`

#### Edge Cases & Error Handling

- Negative `sleep_seconds` validation remains unchanged.
- A transform on a non-continue decision is ignored or rejected. The implementation should reject it with `ValueError` to avoid ambiguous control flow.
- Metadata remains a mapping and should be copied before storage in pipeline events.

---

### 6.3 Middleware Pipeline Transform Aggregation

**File(s):** `vidbyte/middleware/pipeline.py`
**Type:** Modified

#### What it does

Combines transform-bearing continue decisions across middleware in order.

#### Interface / API

```python
class MiddlewarePipeline:
    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
```

Internal helper:

```python
def _merge_continue_decisions(self, current: MiddlewareDecision, next_decision: MiddlewareDecision) -> MiddlewareDecision: ...
```

#### Logic / Algorithm

1. Initialize an aggregate continue decision for each hook.
2. For each middleware:
   - Run the hook.
   - If the decision is `SLEEP`, sleep and continue.
   - If the decision is non-continue, record and return it immediately.
   - If the decision is continue with metadata or transform, merge it into the aggregate continue decision.
3. Merge transform fields with later non-`None` values overriding earlier values.
4. Merge transform metadata and continue metadata with later keys overriding earlier keys.
5. Return the aggregate continue decision after all middleware run.

#### Edge Cases & Error Handling

- Fail-closed exceptions still abort through existing `_exception_decision`.
- Fail-open exceptions still record metadata and continue.
- A middleware returning `None` is treated as `continue_()` as today.
- Transform aggregation must not record unbounded events for every continue decision unless configured later; final result metadata remains bounded.

---

### 6.4 Compaction Middleware Built-Ins

**File(s):** `vidbyte/middleware/builtins/context_compaction.py`
**Type:** New file

#### What it does

Adds public prebuilt middleware classes for tool-result, provider-message, and summary compaction.

#### Interface / API

```python
class ToolResultCompactionMiddleware(AgentMiddleware): ...
class MessageHistoryCompactionMiddleware(AgentMiddleware): ...
class SummaryCompactionMiddleware(AgentMiddleware): ...
```

Factory methods:

```python
ToolResultCompactionMiddleware.truncate(max_chars: int = 600, truncation_indicator: str = "\n...[tool output compacted]") -> ToolResultCompactionMiddleware
ToolResultCompactionMiddleware.strip(placeholder: str = "[tool result stripped by compaction]") -> ToolResultCompactionMiddleware
ToolResultCompactionMiddleware.hide() -> ToolResultCompactionMiddleware
MessageHistoryCompactionMiddleware.keep_last(n: int) -> MessageHistoryCompactionMiddleware
MessageHistoryCompactionMiddleware.remove_all_tool_calls() -> MessageHistoryCompactionMiddleware
MessageHistoryCompactionMiddleware.remove_last_n_tool_calls(n: int) -> MessageHistoryCompactionMiddleware
MessageHistoryCompactionMiddleware.remove_tool_call_percentage(percentage: float, order: str = "oldest") -> MessageHistoryCompactionMiddleware
MessageHistoryCompactionMiddleware.clear_except_system_and_log(progress_log: Mapping[str, object] | None = None) -> MessageHistoryCompactionMiddleware
MessageHistoryCompactionMiddleware.deduplicate_tool_calls() -> MessageHistoryCompactionMiddleware
SummaryCompactionMiddleware.summarize_range(summarizer: Summarizer, keep_last: int = 3) -> SummaryCompactionMiddleware
SummaryCompactionMiddleware.summarize_oldest_n(summarizer: Summarizer, n: int = 5) -> SummaryCompactionMiddleware
SummaryCompactionMiddleware.summarize_by_topic_blocks(summarizer: Summarizer, block_size: int = 10) -> SummaryCompactionMiddleware
```

#### Logic / Algorithm

1. `ToolResultCompactionMiddleware.after_tool_call(...)`:
   - Skip internal tools by default.
   - If `ctx.tool_result is None`, continue.
   - Use `ContextCompactionEngine.compact_tool_result(...)`.
   - Return `MiddlewareDecision.continue_(transform=MiddlewareTransform(model_visible_tool_result=...))`.
2. `MessageHistoryCompactionMiddleware.before_model_call(...)`:
   - If `ctx.provider_messages` is empty, continue.
   - Use `ContextCompactionEngine.compact_provider_messages(...)`.
   - Return `MiddlewareDecision.continue_(transform=MiddlewareTransform(provider_messages=...))`.
3. `SummaryCompactionMiddleware.before_model_call(...)`:
   - Same provider-message flow as message-history middleware.
   - Requires a summarizer at construction.
4. Each class validates numeric and enum-like constructor inputs.
5. Each class exposes `name` values that are stable in metadata.

#### Edge Cases & Error Handling

- `skip_internal_tools=True` prevents hiding/modifying `isDone` output.
- `max_chars=0` is valid for truncate and yields only the indicator.
- `percentage=0` removes nothing; `percentage=1` removes all matching tool messages.
- Invalid `order` raises `ValueError`.
- Summarizer exceptions follow middleware fail-closed behavior through `MiddlewarePipeline`.

---

### 6.5 AgentRuntime Integration

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Applies middleware transforms at explicit hook boundaries and translates legacy context-window tool-result admission into compatibility middleware.

#### Interface / API

No public constructor signature changes are required.

Internal helpers:

```python
def _context_window_admission_middleware(self) -> tuple[AgentMiddleware, ...]: ...
def _apply_before_model_call_transform(self, call_options: Mapping[str, Any], decision: MiddlewareDecision) -> dict[str, Any]: ...
def _model_visible_result_from_decision(self, call: ToolCall, result: ToolResult, decision: MiddlewareDecision) -> ToolResult: ...
```

#### Logic / Algorithm

1. Resolve `self.algorithm` as today.
2. Build `MiddlewarePipeline((*middleware, *self._context_window_admission_middleware()))`.
3. In `_invoke_with_middleware(...)`, pass current `system` and `provider_messages` from `call_options` into `MiddlewareContext`.
4. When `before_model_call` returns a continue decision with a transform, copy `call_options` and replace `system` and/or `messages` before invoking the runner.
5. In `_process_tool_call(...)`, run `after_tool_call` as today.
6. If `after_tool_call` returns a transform with `model_visible_tool_result`, use that visible result.
7. If no middleware supplies a visible result, use the raw `result`.
8. Apply primitive binding after tool-result compaction only when appropriate. The implementation should preserve current primitive-binding behavior by binding the raw successful tool result into the primitive and returning the primitive acknowledgment as the model-visible result unless a compaction transform intentionally overrides it.
9. Remove the direct call to `self.algorithm.model_visible_tool_result(...)` for normal tool admission.
10. Preserve output-schema `response_format` injection in `_build_iteration_call_options(...)`.

#### Edge Cases & Error Handling

- If `before_model_call` aborts, existing middleware abort result behavior remains unchanged.
- If transform application raises, it is a runtime error surfaced through existing agent execution error wrapping.
- Existing options `messages` tuples should not be mutated in place.
- Empty transformed message lists should remove or omit `messages` consistently; the design preference is to set `messages` to `tuple()` only when the provider can accept it, otherwise omit `messages`.

---

### 6.6 ContextWindow Compatibility

**File(s):** `vidbyte/context/algorithms/tool_results.py`, `vidbyte/context/presets.py`, `vidbyte/context/window.py`
**Type:** Modified

#### What it does

Keeps the existing `ContextWindow` public API stable while moving admission behavior to middleware.

#### Interface / API

Existing APIs remain:

```python
ContextWindow.preset.compact_tool_outputs
ContextWindow.preset.hide_tool_outputs
ContextWindow.preset.no_raw_tool_outputs
```

#### Logic / Algorithm

1. Keep `ToolResultAdmission` and `ContextWindowAlgorithm` fields for compatibility.
2. Mark `ContextWindowAlgorithm.model_visible_tool_result(...)` as a compatibility helper that delegates to `ContextCompactionEngine` or equivalent shared tool-result compaction logic.
3. `AgentRuntime` no longer calls this helper in the normal loop.
4. Presets keep their current names and values.

#### Edge Cases & Error Handling

- Unknown preset resolution continues to raise `ValueError`.
- Reflexion and Multi-Provider Agentic Grader remain mutually exclusive with each other in `ContextWindowAlgorithm.__post_init__`.
- Tool-result admission settings can coexist with Reflexion only if already allowed by the dataclass; this PR should not broaden that behavior without tests.

---

### 6.7 Legacy ContextCompactionTool Wrapper

**File(s):** `vidbyte/tools/builtins/context/compaction.py`, `vidbyte/tools/builtins/context/__init__.py`
**Type:** Modified

#### What it does

Preserves the model-visible compaction tool while removing duplicate compaction implementation.

#### Interface / API

```python
class ContextCompactionTool(BaseTool):
    def __init__(self, state: ContextState, *, summarizer: Summarizer | None = None) -> None: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
```

#### Logic / Algorithm

1. Import `CompactionMode`, `ContextCompactionEngine`, and `Summarizer` from `vidbyte.context.compaction`.
2. Keep `spec()` parameter schema compatible.
3. Parse mode and options from `ToolCall.arguments`.
4. Call `engine.compact_messages(...)`.
5. Replace state messages with the returned messages.
6. Return the same success metadata keys currently asserted by tests:
   - `before_count`
   - `after_count`
   - `removed_count`
   - `removed_tool_messages`
7. Convert engine validation errors into `ToolResult.error(...)`.

#### Edge Cases & Error Handling

- Invalid mode returns the current `"Unknown compaction mode."` style error.
- Missing summarizer returns a tool error rather than raising.
- State replacement happens only after compaction succeeds.

---

### 6.8 Public Exports

**File(s):** `vidbyte/middleware/builtins/__init__.py`, `vidbyte/middleware/__init__.py`, `vidbyte/context/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Makes compaction middleware and shared compaction types discoverable from the public SDK surfaces.

#### Interface / API

```python
from vidbyte.middleware.builtins import ToolResultCompactionMiddleware, MessageHistoryCompactionMiddleware, SummaryCompactionMiddleware
from vidbyte.middleware import MiddlewareTransform
from vidbyte.context import CompactionMode, ContextCompactionEngine
from vidbyte import ToolResultCompactionMiddleware
```

#### Logic / Algorithm

1. Export new middleware classes from `vidbyte.middleware.builtins`.
2. Re-export middleware classes and `MiddlewareTransform` from `vidbyte.middleware`.
3. Re-export stable compaction classes from `vidbyte.context`.
4. Re-export user-facing middleware classes from root `vidbyte`.
5. Avoid exposing internal conversion helper classes unless tests or docs require them.

#### Edge Cases & Error Handling

- Avoid import cycles by keeping shared compaction code independent of `AgentRuntime`.
- Root exports should stay limited to stable user-facing classes.

---

### 6.9 Documentation

**File(s):** `README.md`, `skills/vidbyte-sdk/middleware.md`, `skills/vidbyte-sdk/adding-context-window-algorithms.md`
**Type:** Modified

#### What it does

Documents middleware as the preferred compaction layer and demotes `ContextCompactionTool` to compatibility/manual use.

#### Interface / API

README example:

```python
from vidbyte.middleware.builtins import ToolResultCompactionMiddleware, MessageHistoryCompactionMiddleware

agent = Agent(
    name="repo-analyst",
    system_prompt="Use tools when useful.",
    runner=my_runner,
    tools=[lookup_metric],
    middleware=[
        ToolResultCompactionMiddleware.truncate(max_chars=600),
        MessageHistoryCompactionMiddleware.keep_last(n=20),
    ],
)
```

#### Logic / Algorithm

1. Update the Middleware section to mention compaction built-ins.
2. Update advanced built-ins list so `ContextCompactionTool` is described as legacy/manual.
3. Update `skills/vidbyte-sdk/middleware.md` with compaction middleware guidance and transform constraints.
4. Update `adding-context-window-algorithms.md` to state that simple tool-result and message compactions belong in middleware, while full runtime algorithms remain context-window algorithms.

#### Edge Cases & Error Handling

- Documentation must not claim middleware runs for non-linear runtimes.
- Documentation must not imply summarization middleware performs hidden provider calls.

---

### 6.10 Tests and Verification Script

**File(s):** `tests/test_context_compaction_middleware.py`, `tests/test_context_compaction_tools.py`, `tests/test_agent_runtime.py`, `tests/test_agent_middleware.py`, `scripts/test-context-compaction-middleware.py`
**Type:** New file, Modified

#### What it does

Adds direct tests for new middleware and keeps existing compaction tool behavior covered.

#### Interface / API

```python
python -m unittest tests.test_context_compaction_middleware tests.test_context_compaction_tools tests.test_agent_runtime tests.test_agent_middleware
python scripts/test-context-compaction-middleware.py
```

#### Logic / Algorithm

1. Unit-test shared engine behavior with simple `ContextMessage` lists.
2. Unit-test middleware transform decisions.
3. Integration-test `AgentRuntime` with fake runners and fake tools.
4. Keep existing `ContextCompactionTool` tests green.
5. Add a script that imports and exercises every behavior listed in Section 10.

#### Edge Cases & Error Handling

- All tests must use fake runners and avoid live provider calls.
- The script must exit non-zero if any behavior fails.
- The script must print `PASS` or `FAIL` per scenario and a final `X/Y tests passed` summary.

---

## 7. Data Model Changes

### 7.1 `MiddlewareTransform`

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class MiddlewareTransform:
    model_visible_tool_result: ToolResult | None = None
    provider_messages: Sequence[Mapping[str, Any]] | None = None
    system: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

**Migration strategy:** In-memory SDK dataclass only.

- Forward migration: Add the dataclass and export it from middleware surfaces.
- Rollback plan: Remove the dataclass and transform field from `MiddlewareDecision`, then restore direct context-window admission.

### 7.2 `MiddlewareDecision`

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class MiddlewareDecision:
    action: MiddlewareAction = MiddlewareAction.CONTINUE
    reason: str | None = None
    sleep_seconds: float = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)
    transform: MiddlewareTransform | None = None
```

**Migration strategy:** Backward-compatible field addition.

- Forward migration: Existing constructors continue to return continue/sleep/abort/deny/retry decisions.
- Rollback plan: Remove transform field and any transform-aware pipeline/runtime code.

### 7.3 `MiddlewareContext`

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class MiddlewareContext:
    provider_messages: Sequence[Mapping[str, Any]] = ()
    system: str | None = None
```

**Migration strategy:** Backward-compatible field addition.

- Forward migration: Existing middleware receives extra read-only fields.
- Rollback plan: Remove the fields and transform-aware runtime calls.

### 7.4 `CompactionMode` and `ContextCompactionEngine`

**Change type:** New public location, compatibility re-export

```python
class CompactionMode(str, Enum): ...
class ContextCompactionEngine: ...
```

**Migration strategy:** Move source of truth to `vidbyte.context.compaction`, re-export from old tool package.

- Forward migration: Existing imports keep working.
- Rollback plan: Move enum and implementation back to `vidbyte.tools.builtins.context.compaction`.

---

## 8. API Changes

### 8.1 Python SDK: Compaction Middleware

**Change type:** New

**Request:**

```python
agent = Agent(
    name="worker",
    system_prompt="Work.",
    runner=my_runner,
    tools=[lookup],
    middleware=[
        ToolResultCompactionMiddleware.truncate(max_chars=600),
        MessageHistoryCompactionMiddleware.keep_last(n=20),
    ],
)
```

**Response:**

```python
reply.metadata["tool_calls"][0].result.output  # raw output preserved
reply.metadata["middleware"]                   # middleware events/metadata
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Invalid middleware constructor values raise `ValueError`. |
| N/A | Summarizer exceptions follow middleware fail-closed or fail-open behavior. |
| N/A | Middleware aborts return `stop_reason=middleware_abort`. |

### 8.2 Python SDK: Middleware Transform Contract

**Change type:** Modified

**Request:**

```python
return MiddlewareDecision.continue_(
    transform=MiddlewareTransform(provider_messages=compacted_messages)
)
```

**Response:**

```python
# Runtime applies transformed provider messages to the next model call.
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Transform on non-continue decisions raises `ValueError` or is rejected before runtime use. |
| N/A | Invalid provider message shapes are preserved as ordinary messages. |

### 8.3 Python SDK: ContextWindow Admission Compatibility

**Change type:** Modified internally, public API unchanged

**Request:**

```python
agent = Agent(
    name="worker",
    system_prompt="Work.",
    runner=my_runner,
    tools=[lookup],
    algorithm=ContextWindow.preset.no_raw_tool_outputs,
)
```

**Response:**

```python
# Follow-up model call receives hidden/compacted tool result through compatibility middleware.
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Unknown algorithm preset still raises `ValueError`. |
| N/A | Non-linear runtime with non-default algorithm still raises `ConfigurationError`. |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/context-compaction-middleware.md` | Design doc for this refactor |
| CREATE | `vidbyte/context/compaction.py` | Shared compaction engine, enum, stats, and summarizer protocol |
| CREATE | `vidbyte/middleware/builtins/context_compaction.py` | Public compaction middleware built-ins |
| CREATE | `tests/test_context_compaction_middleware.py` | Unit and integration tests for middleware compaction |
| CREATE | `scripts/test-context-compaction-middleware.py` | Required script verification for all Section 10 cases |
| MODIFY | `vidbyte/lib/dataclasses/middleware.py` | Add `MiddlewareTransform`, transform field, and context fields |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Re-export `MiddlewareTransform` if middleware dataclasses are already exported there |
| MODIFY | `vidbyte/middleware/pipeline.py` | Aggregate transform-bearing continue decisions |
| MODIFY | `vidbyte/middleware/__init__.py` | Export `MiddlewareTransform` and compaction middleware classes |
| MODIFY | `vidbyte/middleware/builtins/__init__.py` | Export compaction middleware built-ins |
| MODIFY | `vidbyte/agents/runtime.py` | Apply middleware transforms and translate context-window admission presets |
| MODIFY | `vidbyte/context/algorithms/tool_results.py` | Delegate compatibility admission helper to shared compaction logic |
| MODIFY | `vidbyte/context/__init__.py` | Export shared compaction API |
| MODIFY | `vidbyte/tools/builtins/context/compaction.py` | Refactor legacy tool to delegate to shared engine |
| MODIFY | `vidbyte/tools/builtins/context/__init__.py` | Preserve/re-export `CompactionMode` and tool contracts |
| MODIFY | `vidbyte/__init__.py` | Root-export stable compaction middleware classes and `MiddlewareTransform` |
| MODIFY | `README.md` | Document compaction middleware and compatibility path |
| MODIFY | `skills/vidbyte-sdk/middleware.md` | Add compaction middleware guidance |
| MODIFY | `skills/vidbyte-sdk/adding-context-window-algorithms.md` | Clarify compaction belongs in middleware, not context-window algorithms |
| MODIFY | `tests/test_context_compaction_tools.py` | Keep legacy tool tests aligned with shared engine behavior |
| MODIFY | `tests/test_agent_runtime.py` | Add/adjust runtime compatibility tests for admission presets and transforms |
| MODIFY | `tests/test_agent_middleware.py` | Add transform aggregation/custom middleware coverage |

Summary: 5 files created, 17 files modified, 0 files deleted.

---

## 10. Testing Plan

### Unit Tests

Shared engine tests in `tests/test_context_compaction_middleware.py`:

- `[Edge Case] ContextCompactionEngine.compact_messages keeps an empty message list empty`.
- `[Edge Case] truncate_tool_results with max_chars=0 returns only the truncation indicator`.
- `[Edge Case] remove_tool_call_percentage with percentage=0 removes no tool messages`.
- `[Edge Case] remove_tool_call_percentage with percentage=1 removes all tool messages from the selected side`.
- `[Edge Case] keep_last_n_messages with n=0 keeps only system messages`.
- `[Edge Case] summarize_by_topic_blocks with block_size=1 creates one summary per non-system message`.
- `[Hidden Failure] invalid percentage below 0 or above 1 raises or returns a clean tool error without mutating state`.
- `[Hidden Failure] invalid truncate max_chars values do not partially replace state messages`.
- `[Hidden Failure] summarization mode without a summarizer returns a legacy tool error and raises for middleware construction`.
- `[Hidden Failure] provider messages with unknown dict shapes are preserved rather than dropped`.
- `[Silent Failure] truncate_tool_results at exact boundary does not add compaction metadata`.
- `[Silent Failure] remove_last_n_tool_calls removes newest matching tool messages, not oldest ones`.
- `[Silent Failure] deduplicate_tool_calls keeps the first pair and removes later duplicate pairs`.
- `[Silent Failure] clear_except_system_and_log preserves all system messages and includes progress-log content`.
- `[Hidden Assumption] non-tool messages longer than max_chars are not truncated by tool-result truncation`.
- `[Hidden Assumption] truncation indicators without {count} are appended verbatim`.
- `[Hidden Assumption] negative n values are normalized or rejected consistently by mode`.

Middleware dataclass/pipeline tests:

- `[Edge Case] MiddlewareDecision.continue_ accepts no transform and remains backward-compatible`.
- `[Edge Case] MiddlewareDecision with transform on abort raises ValueError`.
- `[Hidden Failure] MiddlewarePipeline aggregates two continue transforms and later fields override earlier fields`.
- `[Hidden Failure] MiddlewarePipeline preserves fail-closed exception behavior when a transform middleware raises`.
- `[Silent Failure] MiddlewarePipeline returns continue transform metadata instead of dropping it silently`.
- `[Hidden Assumption] MiddlewareContext provider_messages defaults to an empty tuple for existing middleware`.

Compaction middleware unit tests:

- `[Edge Case] ToolResultCompactionMiddleware skips internal tools by default`.
- `[Edge Case] ToolResultCompactionMiddleware continues when ctx.tool_result is None`.
- `[Hidden Failure] ToolResultCompactionMiddleware.hide returns a transformed model-visible result without changing raw result object`.
- `[Silent Failure] ToolResultCompactionMiddleware.truncate records original and truncated character counts`.
- `[Hidden Assumption] ToolResultCompactionMiddleware.strip uses the same placeholder as legacy tool compaction`.
- `[Edge Case] MessageHistoryCompactionMiddleware.keep_last does nothing when provider_messages is empty`.
- `[Hidden Failure] MessageHistoryCompactionMiddleware.remove_all_tool_calls does not remove ordinary assistant text messages`.
- `[Silent Failure] MessageHistoryCompactionMiddleware.remove_tool_call_percentage respects order='newest'`.
- `[Hidden Assumption] MessageHistoryCompactionMiddleware validates order and percentage at construction time`.
- `[Edge Case] SummaryCompactionMiddleware.summarize_oldest_n with n=0 leaves messages unchanged`.
- `[Hidden Failure] SummaryCompactionMiddleware propagates summarizer exceptions through middleware fail-closed behavior`.
- `[Silent Failure] SummaryCompactionMiddleware.summarize_range preserves the configured number of recent messages`.
- `[Hidden Assumption] SummaryCompactionMiddleware requires an injected summarizer and never calls a provider implicitly`.

Legacy `ContextCompactionTool` tests in `tests/test_context_compaction_tools.py`:

- `[Edge Case] Existing clear_except_system_and_log test still passes through shared engine`.
- `[Edge Case] Existing remove_all_tool_calls test still passes through shared engine`.
- `[Edge Case] Existing truncate zero max chars test still passes through shared engine`.
- `[Hidden Failure] Existing invalid bounds tests still return `ToolResult.error`.
- `[Silent Failure] Existing boundary-length truncate test still avoids metadata mutation`.
- `[Hidden Assumption] Existing missing-summarizer tests still return tool errors instead of raising`.

### Integration Tests

Runtime tests in `tests/test_agent_runtime.py` and `tests/test_context_compaction_middleware.py`:

- `[Edge Case] Runtime with no compaction middleware preserves raw tool output in follow-up provider messages`.
- `[Edge Case] Runtime with ToolResultCompactionMiddleware.truncate sends truncated output to the second model call`.
- `[Hidden Failure] Runtime with ToolResultCompactionMiddleware.hide keeps raw tool output in final metadata but withholds it from follow-up provider messages`.
- `[Hidden Failure] Runtime with ContextWindow.preset.no_raw_tool_outputs preserves existing hidden-output behavior through compatibility middleware`.
- `[Hidden Failure] Runtime with ContextWindow.preset.compact_tool_outputs preserves max_tool_result_chars behavior through compatibility middleware`.
- `[Silent Failure] Runtime applies `before_model_call` provider_messages transform to the current call, not only to the next retry.
- `[Silent Failure] Runtime does not mutate original `options["messages"]` passed by the caller.
- `[Hidden Assumption] Runtime output_schema response_format injection remains present after message compaction.
- `[Hidden Assumption] Middleware compaction does not transform internal `isDone` output.
- `[Hidden Assumption] Primitive binding still stores the intended raw successful tool output when compaction middleware is active.

Middleware composition tests:

- `[Edge Case] ToolResultCompactionMiddleware and AuditLogMiddleware compose in either order without hiding audit metadata`.
- `[Hidden Failure] ToolPolicyMiddleware deny_tool still prevents tool execution before compaction middleware can transform a result`.
- `[Silent Failure] Two message compaction middleware instances compose deterministically with later transform fields winning`.
- `[Hidden Assumption] fail_open compaction middleware exception records middleware metadata and lets runtime continue.

External dependencies:

- All provider calls are mocked with fake runners.
- No network, filesystem, MCP subprocess, or real provider key is needed.

### Manual / QA Test Cases

1. `[Edge Case]` Given an agent with `ToolResultCompactionMiddleware.truncate(max_chars=5)` and a tool returning `1234567890`, when the agent runs, then the second model call sees truncated content and final metadata contains the raw `1234567890`.
2. `[Hidden Failure]` Given an agent using `ContextWindow.preset.no_raw_tool_outputs`, when a tool returns secret text, then the second model call does not contain secret text and final metadata still contains it.
3. `[Silent Failure]` Given `MessageHistoryCompactionMiddleware.keep_last(n=1)`, when messages contain multiple previous assistant messages, then only the newest non-system message remains model-visible.
4. `[Hidden Assumption]` Given `SummaryCompactionMiddleware.summarize_oldest_n(...)` with a fake summarizer, when provider messages are compacted, then the fake summarizer is called and no provider runner is invoked for summarization.
5. `[Hidden Failure]` Given invalid constructor values such as `percentage=1.5` or `max_chars=-1`, when middleware is constructed, then it fails fast with `ValueError`.

Script verification:

- Create `scripts/test-context-compaction-middleware.py`.
- The script must run every scenario above either directly or through imported unittest cases.
- The script must print `PASS` or `FAIL` per test case.
- The script must print `X/Y tests passed`.
- The script must exit non-zero on failure.

Full verification commands:

```powershell
python -m compileall vidbyte
python -m unittest tests.test_context_compaction_middleware tests.test_context_compaction_tools tests.test_agent_runtime tests.test_agent_middleware
python -m unittest discover -s tests
python scripts/test-context-compaction-middleware.py
```

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib | Python >=3.11 | dataclasses, enums, protocols, unittest | Existing runtime only |
| pydantic | Existing `>=2,<3` | Not used directly by this feature | No new risk |
| httpx | Existing dependency | Not used by this feature | No new risk |
| Live LLM providers | N/A | Not required | Must not be used in tests |

No new dependencies or external services are introduced.

---

## 12. Rollout & Deployment

- This is an SDK-only change.
- The change is intended to be backward-compatible for existing users.
- Existing `ContextCompactionTool` remains available.
- Existing context-window admission presets remain available.
- New code should prefer middleware compaction.
- No feature flag is required.

Deployment order after approval:

1. Create isolated worktree from updated `main`.
2. Commit this design doc first.
3. Add shared compaction engine and exports.
4. Add middleware transform dataclass and pipeline aggregation.
5. Add compaction middleware built-ins.
6. Wire runtime transform application and compatibility middleware.
7. Refactor legacy `ContextCompactionTool`.
8. Add tests and script verification.
9. Update README and skill docs.
10. Run compile, focused tests, full tests, and script.
11. Push branch and open draft PR.

Rollback procedure:

1. Revert the feature branch merge commit.
2. Restore `AgentRuntime` direct `ContextWindowAlgorithm.model_visible_tool_result(...)` call.
3. Remove `vidbyte/context/compaction.py` and compaction middleware exports.
4. Restore legacy `ContextCompactionTool` implementation if needed.
5. Remove transform fields from middleware dataclasses and pipeline.

---

## 13. Open Questions

- [ ] Should root `vidbyte` export all three middleware classes, or only `ToolResultCompactionMiddleware` as the most common public entry point?
- [ ] Should `MessageHistoryCompactionMiddleware` run on every `before_model_call`, or should it support trigger thresholds such as `min_message_count` or `min_tokens_used` in the first PR?
- [ ] Should `AgentRuntimeConfig.compaction_trigger_tokens` and `compaction_target_tokens` be wired into default compaction middleware in this PR, or left for a follow-up?
- [ ] Should provider-message summaries be emitted as `assistant` messages for all providers, or should Anthropic/Gemini receive provider-specific summary shapes?
- [ ] Should `ContextCompactionTool` be formally marked deprecated in docstrings now, or only described as compatibility/manual in README?

---

## 14. Alternatives Considered

### Alternative 1: Keep Compaction as ContextWindow Algorithms

- What: Move every compaction mode into `ContextWindow.preset.*`.
- Why rejected: The README and runtime architecture already describe middleware as deterministic, non-model-visible policy. Simple compactions are runtime policy, not full context-window algorithms. Keeping them under `algorithm=` would expand a confusing split.

### Alternative 2: Let Middleware Mutate Runtime Internals Directly

- What: Pass mutable `messages` and `call_options` into `MiddlewareContext` and let middleware edit them.
- Why rejected: Free mutation makes middleware ordering, audit, and failure behavior hard to reason about. Explicit `MiddlewareTransform` keeps effects narrow and testable.

### Alternative 3: Remove `ContextCompactionTool` Immediately

- What: Delete the model-visible compaction tool and force users to migrate to middleware.
- Why rejected: The SDK has existing tests and public imports for this tool. Removing it would be a breaking change. This PR can refactor it into a compatibility wrapper first.

### Alternative 4: One `ContextCompactionMiddleware` Class With a Mode String

- What: Implement one middleware class mirroring `ContextCompactionTool(mode=...)`.
- Why rejected: It would preserve the current kitchen-sink API and blur hook ownership. Separate tool-result, message-history, and summary middleware classes make lifecycle and failure modes clearer.

### Alternative 5: Summarization Middleware Calls the Agent Runner Internally

- What: Let summary compaction middleware invoke the current provider/runner to summarize history.
- Why rejected: Hidden provider calls inside middleware would affect cost, latency, retry, tracing, and prompt visibility in ways users would not expect. An injected summarizer makes this explicit and testable.
