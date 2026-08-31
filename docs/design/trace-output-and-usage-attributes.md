# Design Doc: Trace Close-Time Attributes and Usage Wiring

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-31
**Last Updated:** 2026-08-31

---

## 1. Overview

PR #390 (branch `feat/otel-genai-openinference-trace-shapes`, not yet merged) gave Vidbyte two spec-verified trace shapes — OTel GenAI semantic conventions and OpenInference — but both shapes can only see attributes that exist at the moment a span *opens*. Model response text, token usage, and cost are only known after the model call returns, so today they never reach either shape: they flow through a separate `end_span(output=...)` call that stores a single unstructured string, under a field name (`output.value`) neither spec defines. This doc designs the missing half — a `translate_end` hook mirroring the existing `translate_start` — and wires it to the two data sources that should feed it: the per-call model response (already parsed once at the `llm.call` span) and the run-level `UsageRollup` already tracked on every `BaseAgent`.

---

## 2. Goals & Non-Goals

### Goals
- Let a `ProviderTraceTranslator` shape close-time span data (response text, token usage, cost) the same way it already shapes open-time data, without adding a second object model.
- Wire the OTel GenAI and OpenInference translators (from PR #390) to emit the response/usage fields their own specs define, closing the gap documented in that PR's design doc (Non-Goals: "no wiring of PR #304's usage/cost tracking into span attributes yet").
- Attach the whole-run `UsageRollup` (already computed by `BaseAgent.get_usage()`) to the root `agent.run` trace when it closes.
- Keep every existing tracer, translator, and facade method's current behavior unchanged for callers who pass nothing new — purely additive.
- Make the mechanism generic enough that a future field (e.g. a new usage axis, a new response shape) is one more dict key at an existing call site, not a new abstraction.

### Non-Goals
- Re-implementing or redesigning the OTel GenAI / OpenInference *open-time* mappings already shipped in PR #390 — those are treated as a dependency, unchanged.
- Building a dedicated MLflow translator. Research earlier in this project found MLflow's own "third-party OTel span attributes" compatibility page already remaps raw `gen_ai.*` attributes (including, per its own docs, `gen_ai.output.messages` → `mlflow.spanOutputs`) — so this feature is very likely sufficient to make MLflow render correctly too, without MLflow-specific code. Confirming that empirically against a real MLflow tracking server is called out as a follow-up, not in scope here.
- Adding `translate_end` support to `LangSmithProviderTranslator` or `GenericProviderTranslator`. `translate_end` is optional (detected via `hasattr`), so both keep exactly their current behavior. LangSmith already has native `usage_metadata` support on `update_run`; wiring that is a smaller, separate follow-up.
- Changing `AgentRuntime._invoke_with_middleware`'s signature or return shape. Its docstring states it has external callers (`reflexion.py`, `multi_provider_agentic_grader.py`) with a frozen keyword signature; this design works within that constraint (Section 6.6).
- A new "AgentStatistics" object, a `record_trace()` free function, or new middleware hooks. `UsageTracker`/`UsageRollup` (`vidbyte/agents/pricing/`) already do this job; this doc extends the *trace* side to reach them, not the usage-tracking side.

---

## 3. Background & Context

This follows directly from a design conversation about PR #390. That PR's own design doc lists as explicitly out of scope: "no wiring of PR #304's usage/cost tracking into span attributes yet." Investigating where that wiring would go surfaced a structural fact, not just a missing mapping:

- `ProviderTraceTranslator.translate_start(spec) -> ProviderSpanPayload` is the only method in the protocol (`vidbyte/trace/providers/base.py`). It runs once, when a span opens.
- Every tracer's `end_span`/`end_trace` (`TracerBase`, `TraceController`, `OTelTracer`, `PhoenixTracer`, `LangSmithTracer`, `LangfuseTracer`, `DebugTracer`, `SessionTracer`/`SessionTraceController`) accepts exactly two optional fields: `output: str | None` and `error: BaseException | None`. There is no `attributes` parameter anywhere in the close-time contract.
- In `vidbyte/agents/runtime.py`, the `llm.call` span (`_invoke_with_middleware`, lines 578-594) opens *before* `handle.invoke(...)` runs and closes immediately after with only `output=output_text`. `self.usage_tracker.record_call(raw_result)` — the call that actually prices the response — runs one call-frame later, in the loop that calls `_invoke_with_middleware`, after that method has already returned and the span has already closed.
- A closer read of `OTelGenAIProviderTranslator._translate_llm` (`vidbyte/trace/providers/otel_genai.py`) shows it already *checks* for `input_tokens`, `output_tokens`, and `finish_reason` in `spec.attributes` — but `_llm_trace_inputs()` (`runtime.py:1126`), the only function that builds those attributes, never sets any of the three (it only has pre-call data: prompt, system, tools, message history). So today those three `if` branches are dead in every real run through `BaseAgent` — not a bug exactly, but evidence the mapping was written for data that had no path to reach it yet. This design doc builds that path.

---

## 4. Requirements

### Functional Requirements

1. `ProviderTraceTranslator` gains an optional `translate_end(spec: SpanSpec, attributes: Mapping[str, Any]) -> dict[str, Any]` method. A translator that does not define it (any existing custom translator, `LangSmithProviderTranslator`, `GenericProviderTranslator`) must keep behaving exactly as it does today — `TraceController` must detect its absence via `hasattr` and skip translation, never raise.
2. `TracerBase.end_span` and `TracerBase.end_trace` (and every concrete subclass) gain `**attributes: Any`, mirroring the existing `**attributes: Any` on `start_span`/`start_trace`. Calling either with only `output=`/`error=` (every existing call site) must be unaffected.
3. `TraceController.end_span`/`end_trace` must: sanitize any passed `**attributes` through the same `safe_trace_value(..., max_chars=self.profile.max_chars, redact=self.profile.redact)` redaction path `_sanitize_spec` already uses for open-time attributes; pass the sanitized attributes and the span's original `SpanSpec` (already carried on `SemanticSpanContext.spec`) to `translator.translate_end` when present; forward the returned dict into `self.inner.end_span`/`end_trace` as `**kwargs`, alongside the existing `output`/`error`.
4. `OTelGenAIProviderTranslator.translate_end` must, for `SpanKind.LLM` spans, map (when present in the passed attributes) `output_messages` → `gen_ai.output.messages`, `input_tokens` → `gen_ai.usage.input_tokens`, `output_tokens` → `gen_ai.usage.output_tokens`, `finish_reason` → `gen_ai.response.finish_reasons`, using the same field names `_translate_llm`'s open-time mapping already uses (Section 3 confirms these are the verified spec names, unchanged from PR #390's research — no new fields are being invented here, only re-fired at a time when real values exist).
5. `OTelGenAIProviderTranslator.translate_end` must, for the `agent.run` spec (matched by name, exactly like `_translate_agent` does at open time), namespace every passed attribute under `vidbyte.usage.*` rather than inventing an unverified `gen_ai.*` aggregate-usage field — the OTel GenAI spec defines `gen_ai.usage.*` at the per-call span level, not at the invoke_agent span level, and this doc does not introduce a new spec claim.
6. `OpenInferenceProviderTranslator.translate_end` must, for `SpanKind.LLM` spans, map `output_messages` → `llm.output_messages.<index>.message.role`/`.content` (the same indexed-message pattern `_translate_llm` already uses for input), and `output_tokens`/`total_tokens` → `llm.token_count.completion`/`.total` (verified field names already cited in PR #390's design doc, Section 3, alongside the already-shipped `llm.token_count.prompt`).
7. Any attribute passed to `translate_end` that neither translator's LLM branch explicitly maps must be namespaced under `vidbyte.` exactly as the existing `_namespaced_extras` helper already does for open-time attributes — including any cached-token field, until its real spec name (if one exists) is verified live against the spec during implementation (Section 13).
8. `AgentRuntime._invoke_with_middleware` must compute a *non-mutating* usage preview from `raw_result` immediately before closing the `llm.call` span, and pass it plus `output_text` as `**attributes` to `end_span`. It must not append to `usage_tracker`'s ledger a second time — the existing `usage_tracker.record_call(raw_result)` call at the calling loop (`runtime.py:412`) remains the single place a call is actually priced and recorded.
9. `UsageTracker` gains a `preview_call(response: object) -> UsageRecord | None` method with the same parsing/pricing behavior as `record_call`, refactored to share a private helper, but which never appends to `self._records` and never advances `call_index`.
10. `BaseAgent.generate_reply` must pass the run's final `UsageRollup` (`self.get_usage()`) as `**attributes` to the `agent.run` trace's `end_trace` call, only when the rollup has at least one recorded call (an empty rollup must add no attributes, not empty/zero placeholders).
11. Every existing test in `tests/test_semantic_tracing.py`, `tests/test_otel_genai_trace_shape.py`, `tests/test_openinference_trace_shape.py`, `tests/test_trace_facade.py`, and the full agent runtime suite must continue to pass unmodified.

### Non-Functional Requirements
- **Backward compatibility:** every signature change is additive (`**attributes: Any` / a new optional protocol method); no existing call site anywhere in the repo should require a change to keep compiling and passing.
- **No double-billing:** the non-mutating `preview_call` path (Requirement 9) is a correctness requirement, not a style preference — a regression here would silently double-count cost and tokens in `UsageRollup`.
- **Spec integrity:** every new `gen_ai.*`/`llm.*` field name must already be cited, verified, in PR #390's design doc (`docs/design/otel-genai-and-openinference-trace-shapes.md`, Section 3) or re-verified live against the published spec before being hardcoded; anything not verified goes through the `vidbyte.` namespace fallback, never a guessed spec field name.
- **Failure containment:** a translator raising inside `translate_end`, or a malformed `attributes` mapping, must not break the span close or the agent run — matches the existing fail-open posture of `OTelTracer`/`PhoenixTracer` (`except Exception: pass` around span mutation).
- **Observability parity:** this feature only adds attributes; it must not remove or rename any attribute either shape already emits today.

---

## 5. High-Level Design

Two independent pieces, matching the two ends of the gap identified in Section 3.

**Piece 1 — widen the close-time contract.** `end_span`/`end_trace` grow a `**attributes` kwarg through the same layers `start_span`/`start_trace` already use it: `TracerBase` (abstract contract) → each concrete tracer (`OTelTracer`, `PhoenixTracer`, `LangSmithTracer`, `LangfuseTracer`, `DebugTracer`, session tracers) → `TraceController`, which is also where the new optional `translate_end` hook gets invoked, using the exact `SpanSpec` already stored on `SemanticSpanContext` from when the span opened. This is the same shape the existing `translate_start`/`ProviderSpanPayload` pair already established — `translate_end` returns a plain `dict[str, Any]`, not a new type.

**Piece 2 — feed it from two call sites that already have the data.** In `AgentRuntime._invoke_with_middleware`, right after the model call returns (where `output_text` is already computed today), a new non-mutating `usage_tracker.preview_call(raw_result)` produces the same `UsageRecord` shape the ledger will separately record one frame later — without touching the ledger, so nothing is billed twice. In `BaseAgent.generate_reply`, the already-existing `self.get_usage()` rollup is attached to the root trace's `end_trace` call.

```
 model call returns
        |
        v
 _invoke_with_middleware (runtime.py)
    output_text = handle.extract_text(raw_result)      [existing]
    usage_preview = usage_tracker.preview_call(raw_result)   [new, non-mutating]
    end_span(llm_span, output=output_text, **usage_attrs)    [attributes= new]
        |
        v
 TraceController.end_span
    sanitize attrs (existing safe_trace_value)
    translator.translate_end(spec, attrs)  -> shaped dict     [new hook]
        |
        v
 inner.end_span(context, output=.., error=.., **shaped)      [OTelTracer / Phoenix / etc.]
        |
        v
 real gen_ai.output.messages / llm.output_messages.*.content on the wire

 (separately, unchanged) usage_tracker.record_call(raw_result)  <- still the only ledger write
```

The two pieces don't depend on each other in a way that risks partial failure: if `translate_end` is absent, `TraceController` simply forwards nothing extra, exactly like today.

---

## 6. Detailed Design

### 6.1 `ProviderTraceTranslator` protocol

**File(s):** `vidbyte/trace/providers/base.py`
**Type:** Modified

#### What it does
Declares the optional close-time counterpart to `translate_start`.

#### Interface / API
```python
class ProviderTraceTranslator(Protocol):
    provider: str

    def translate_start(self, spec: SpanSpec) -> ProviderSpanPayload: ...

    # Optional: absence is detected via hasattr, never assumed present.
    def translate_end(self, spec: SpanSpec, attributes: Mapping[str, Any]) -> dict[str, Any]: ...
```
`Protocol` classes cannot express "optional method" directly with a body, so `translate_end` is declared but every caller must check `hasattr(translator, "translate_end")` rather than assume it exists — matching how `_TraceFactory.resolve_translator` already checks `hasattr(provider, "translate_start")` for custom translators today.

#### Logic / Algorithm
No runtime logic in this file; it is a structural typing contract.

#### Edge Cases & Error Handling
- A custom translator supplied via `Trace.profile(provider=my_translator)` that only has `translate_start` must keep working unchanged (Requirement 1).

---

### 6.2 `TraceController` close-time translation

**File(s):** `vidbyte/trace/controller.py`
**Type:** Modified

#### What it does
Threads `**attributes` from `end_span`/`end_trace` through sanitization and the translator, then into the inner tracer.

#### Interface / API
```python
class TraceController(TracerBase):
    def end_trace(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None, **attributes: Any) -> None: ...
    def end_span(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None, **attributes: Any) -> None: ...
    def _translate_end(self, spec: SpanSpec | None, attributes: Mapping[str, Any]) -> dict[str, Any]: ...
```

#### Logic / Algorithm
1. `end_span`/`end_trace` coerce `context` to a `SemanticSpanContext` exactly as today; if suppressed or not semantic, pop and return (unchanged).
2. Call the new private `_translate_end(semantic.spec, attributes)`:
   - Return `{}` immediately if `attributes` is empty (avoid calling into the translator for the overwhelming majority of spans that pass none).
   - Return `{}` if `getattr(self.translator, "translate_end", None)` is `None`.
   - Otherwise sanitize `attributes` through `safe_trace_value(dict(attributes), max_chars=self.profile.max_chars, redact=self.profile.redact)` — the same call `_sanitize_spec` already makes — then call `translate_end(spec, sanitized)` and return its result.
3. Forward the returned dict as `**translated` into `self.inner.end_span(...)`/`end_trace(...)`, alongside the existing `output=output, error=error`.

#### Edge Cases & Error Handling
- `semantic.spec` can be `None` only for a root context built before any span opened; `_translate_end` treats `spec is None` as "skip translation, return `{}`" rather than raising.
- A `translate_end` implementation raising must not be swallowed silently at this layer specifically to avoid masking a genuine implementation bug during development — but the concrete translators in 6.3/6.4 are themselves written defensively (fall back to omitting a field, never raise on a missing key), so in practice this path should not raise once implemented correctly. No new `except Exception: pass` is added here; the existing per-tracer fail-open behavior downstream (`OTelTracer`, `PhoenixTracer`) remains the safety net for transport-level failures.

---

### 6.3 `OTelGenAIProviderTranslator.translate_end`

**File(s):** `vidbyte/trace/providers/otel_genai.py`
**Type:** Modified

#### Interface / API
```python
class OTelGenAIProviderTranslator:
    def translate_end(self, spec: SpanSpec, attributes: Mapping[str, Any]) -> dict[str, Any]: ...
    def _translate_llm_end(self, attributes: Mapping[str, Any]) -> dict[str, Any]: ...
    def _translate_agent_end(self, attributes: Mapping[str, Any]) -> dict[str, Any]: ...
```

#### Logic / Algorithm
1. `translate_end` dispatches the same way `translate_start` does: `spec.name == "agent.run"` → `_translate_agent_end`; `spec.kind is SpanKind.LLM` → `_translate_llm_end`; everything else → namespace every key under `vidbyte.` with no consumed-key exclusions (mirrors `_translate_generic`).
2. `_translate_llm_end`: maps `output_messages` → `gen_ai.output.messages` (only if present and non-empty), `input_tokens`/`output_tokens` → `gen_ai.usage.input_tokens`/`.output_tokens`, `finish_reason` → `gen_ai.response.finish_reasons`; every other key namespaced under `vidbyte.` (this is where a `cached_input_tokens` key lands until/unless a verified spec field is confirmed — Section 13).
3. `_translate_agent_end`: every key namespaced under `vidbyte.usage.` (Requirement 5) — deliberately does not reuse `_translate_llm_end`'s field names, since those are per-call-scoped by spec, not whole-run.

#### Edge Cases & Error Handling
- Missing keys are simply omitted, matching `_translate_llm`'s existing "never raise, never invent a placeholder value" behavior for open-time fields.

---

### 6.4 `OpenInferenceProviderTranslator.translate_end`

**File(s):** `vidbyte/trace/providers/openinference.py`
**Type:** Modified

#### Logic / Algorithm
1. `translate_end` dispatches on `spec.kind`: `LLM` → `_translate_llm_end`; else → namespace everything under `vidbyte.` (no `openinference.span.kind` to re-set at close time; it was already set at open).
2. `_translate_llm_end`: expands `output_messages` into `llm.output_messages.<index>.message.role`/`.message.content` (same pattern `_translate_llm`'s open-time `input_messages` expansion already uses); maps `output_tokens` → `llm.token_count.completion`, `total_tokens` → `llm.token_count.total` (verified names, already cited in PR #390's design doc alongside the shipped `llm.token_count.prompt`).

#### Edge Cases & Error Handling
- Same non-raising, omit-if-absent behavior as 6.3.

---

### 6.5 `UsageTracker.preview_call`

**File(s):** `vidbyte/agents/pricing/tracker.py`
**Type:** Modified

#### What it does
Produces the same priced `UsageRecord` shape as `record_call`, without mutating the ledger — the mechanism that avoids double-billing (Requirement 9).

#### Interface / API
```python
class UsageTracker:
    def record_call(self, response: object) -> UsageRecord | None: ...   # unchanged behavior
    def preview_call(self, response: object) -> UsageRecord | None: ...  # new
    def _price_call(self, response: object, *, call_index: int) -> UsageRecord | None: ...  # new, shared
```

#### Logic / Algorithm
1. Extract the current body of `record_call` (provider/model/payload parsing, `_parse_usage`, `UsageRecord` construction, `mark_recording_corrupted` on parse failure) into `_price_call(response, call_index=...)`.
2. `record_call` becomes: `record = self._price_call(response, call_index=len(self._records) + 1)`; if not `None`, `self._records.append(record)`; return `record`. Identical external behavior to today.
3. `preview_call` becomes: `return self._price_call(response, call_index=len(self._records) + 1)` — same `call_index` numbering a real `record_call` right now would use, but **never appended**. A caller must not treat `preview_call`'s returned `call_index` as durable, since a real `record_call` may append a different record before this preview's index is ever real; the design doc calls this out explicitly rather than leaving it implicit, since it is the one field of the returned record that is not simply "the same value `record_call` would have produced."
4. `mark_recording_corrupted()` behavior: `preview_call`'s parse failure must **not** call `mark_recording_corrupted()` — that flag means "a real record was lost," and a preview was never going to be recorded. Only `_price_call`'s caller decides whether to flag corruption; `record_call` keeps doing so on failure, `preview_call` does not.

#### Edge Cases & Error Handling
- `preview_call(None)` / a malformed `response` object: identical to `record_call`'s existing behavior — `_parse_usage` returns `None`, `_price_call` returns `None`, no exception.
- Calling `preview_call` many times for the same response (e.g. a retried span-close path) must be side-effect-free and idempotent, since it never touches `self._records`.

---

### 6.6 `AgentRuntime._invoke_with_middleware` — wiring the `llm.call` span

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified (signature and return type unchanged — see Non-Goals)

#### What it does
Builds the close-time attributes dict from the same `raw_result` already in scope when `end_span` is called, using the new non-mutating preview.

#### Interface / API
```python
def _llm_trace_outputs(self, raw_result: object, output_text: str, handle: RunnerHandle) -> dict[str, Any]: ...
```
(new private helper, mirrors the existing `_llm_trace_inputs`; `_invoke_with_middleware`'s own signature is unchanged, per the frozen-signature constraint noted in its docstring)

#### Logic / Algorithm
1. At the existing success path (`runtime.py:592-594`), immediately after `output_text = handle.extract_text(raw_result)`:
   ```python
   usage_preview = self.usage_tracker.preview_call(raw_result)
   self._tracer.end_span(llm_span, output=output_text, **self._llm_trace_outputs(raw_result, output_text, usage_preview))
   ```
2. `_llm_trace_outputs` builds: `{"output_messages": ({"role": "assistant", "content": _trace_text(output_text)},)}` always; plus, only when `usage_preview is not None`: `input_tokens`, `output_tokens`, and (only when the provider reports it) `cached_input_tokens`, from `usage_preview.usage`; plus `finish_reason` when `handle`/`raw_result` exposes one (reusing whatever existing metadata extraction `_runner_output_metadata`-equivalent path already surfaces this — verified during implementation, Section 13, since no current code path reads a finish reason today).
3. The error path (`runtime.py:596-597, 617-620`) is unchanged — no usage data exists for a failed call, and `end_span(llm_span, error=exc)` already correctly reports nothing extra.

#### Edge Cases & Error Handling
- `usage_preview is None` (unrecognized provider, malformed payload — same conditions `record_call` already tolerates): `_llm_trace_outputs` must omit all usage fields, keeping only `output_messages`, never emit a zero/placeholder.
- A provider that doesn't report cached tokens (`ProviderUsage.cached_input_tokens` defaults to `None`): omitted entirely, not emitted as `0`.
- This method fires on every iteration of a multi-turn agent loop, so `_llm_trace_outputs` must stay cheap (no additional network or disk I/O) — it only touches already-in-memory objects, matching `_llm_trace_inputs`'s existing cost profile.

---

### 6.7 `BaseAgent.generate_reply` — whole-run usage on the root trace

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### Interface / API
```python
def _usage_trace_attributes(self) -> dict[str, Any]: ...  # new private helper
```

#### Logic / Algorithm
1. At `runtime.py:630`'s equivalent in `base.py` (the success `end_trace` call, currently `self._tracer.end_trace(trace_ctx, output=_format_trace_output(result))`), change to:
   ```python
   self._tracer.end_trace(trace_ctx, output=_format_trace_output(result), **self._usage_trace_attributes())
   ```
2. `_usage_trace_attributes`: reads `rollup = self.get_usage()`; if `rollup.model_call_count == 0` returns `{}` (Requirement 10 — no zero-value noise on a run that made no model calls, e.g. a pure tool-only or cached path); otherwise returns a flat dict of `input_tokens`, `output_tokens`, `total_tokens`, `cost_usd`, `model_call_count`, `cost_complete`, `operation_count` pulled straight off the existing `UsageRollup` dataclass fields (`vidbyte/agents/pricing/records.py`) — no new fields invented, every key already exists on `UsageRollup` today.
3. The error path (`base.py:631-645`) is intentionally left unchanged — a run that raised may have a partial rollup, and attaching partial usage to an error trace is left as a explicit non-goal to avoid conflating "usage so far" with "usage for a completed run" (Section 13 open question).

#### Edge Cases & Error Handling
- `rollup.model_call_count == 0`: emit nothing (Requirement 10).
- `rollup.cost_usd is None` (an unpriced model, e.g. a custom/unknown provider): the key is simply absent from the dict — `_usage_trace_attributes` never coerces `None` into a placeholder.

---

### 6.8 Every remaining `TracerBase` implementation — accept and forward `**attributes`

**File(s):** `vidbyte/lib/tracing/base.py`, `vidbyte/trace/debug.py`, `vidbyte/trace/session.py`, `vidbyte/providers/tracing/otel.py`, `vidbyte/providers/tracing/phoenix.py`, `vidbyte/providers/tracing/langsmith.py`, `vidbyte/providers/tracing/langfuse.py`, `vidbyte/agents/multi/tracing.py`
**Type:** Modified

#### What it does
Widens every concrete `end_span`/`end_trace` to accept `**attributes: Any`, so the chain in Section 6.2 has somewhere to land regardless of which tracer is `inner`.

#### Interface / API (per file)
- `TracerBase` (abstract): `end_span`/`end_trace` gain `**attributes: Any` in the abstract signature. `NullTracer` already declares `**_: Any` and needs no code change, only benefits from the now-consistent abstract contract.
- `OTelTracer.end_span`/`end_trace` (`otel.py:101,117`): accept `**attributes: Any`; pass into the existing private `_set_attributes(span, attributes)` before `span.end()` — this method already exists and already does exactly the right coercion (primitives pass through, everything else JSON-encoded), it is just never called with anything beyond `output.value`/`error.message` today.
- `PhoenixTracer.end_span`/`end_trace` (`phoenix.py:60,104`): accept `**attributes: Any`; loop `for key, value in attributes.items(): context.span.set_attribute(key, value if isinstance(value, (str, bool, int, float)) else json.dumps(value, default=str))`, reusing the coercion pattern already inline in `start_span`/`start_trace` (currently `str(value)`-only there; this method needs the richer coercion since `output_messages` is a tuple of dicts, not a string — see Alternatives Considered for why `start_span`'s cruder `str(value)` is left untouched).
- `LangSmithTracer.end_span`/`end_trace` (`langsmith.py:103,132`): merge `attributes` into the existing `outputs={"output": output}` dict passed to `update_run` — becomes `outputs={"output": output, **attributes}` when `attributes` is non-empty, else unchanged.
- `LangfuseTracer.end_span`/`end_trace` (`langfuse.py:63,105`): accept `**attributes: Any`; pass as `metadata=attributes or None` into `context.handle.update(...)`/`.end(...)`, mirroring how `start_span` already passes `metadata=attributes or None`.
- `DebugTracer.end_span`/`end_trace` (`debug.py`): accept `**attributes: Any`; include them in the recorded event dict (useful for the new tests in Section 10, which assert against `DebugTracer`'s event log rather than a live OTel exporter).
- `SessionTracer`/`SessionTraceController` (`session.py`, four methods): accept and forward `**attributes: Any` to whichever tracer they wrap, unchanged control flow otherwise.
- `MultiAgentTracer.end_span` (`agents/multi/tracing.py:54`): accept and forward `**attributes: Any` for consistency; not exercised by this feature's own test plan since multi-agent control-flow spans do not carry usage data, but left inconsistent would be a trap for a future contributor extending multi-agent tracing.

#### Edge Cases & Error Handling
- Every existing call site in the repo that calls `end_span(context, output=..., error=...)` with no extra kwargs must be unaffected — `**attributes` defaults to `{}` everywhere.
- `PhoenixTracer`/`OTelTracer`/`LangfuseTracer`/`LangSmithTracer` already wrap their span-mutation code in `try/except Exception: pass` (or, for LangSmith, `_call_langsmith`'s existing error handling); the new attribute-setting code is added inside that same guarded region, not a new unguarded one.

---

## 7. Data Model Changes

N/A — no persisted schema changes. `SpanSpec`, `ProviderSpanPayload`, `UsageRecord`, and `UsageRollup` are all reused unchanged; `UsageTracker` gains a method, not a field.

---

## 8. API Changes

N/A — this is an internal SDK tracing/runtime change with no HTTP surface. The only public-facing surface is the `vidbyte.trace` / `vidbyte.Agent` Python API, whose signatures only widen (Section 6), never break.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/trace/providers/base.py` | Add optional `translate_end` to `ProviderTraceTranslator` |
| MODIFY | `vidbyte/trace/providers/otel_genai.py` | Implement `translate_end` for LLM and agent.run spans |
| MODIFY | `vidbyte/trace/providers/openinference.py` | Implement `translate_end` for LLM spans |
| MODIFY | `vidbyte/trace/controller.py` | Widen `end_span`/`end_trace`; call `translate_end`; sanitize attrs |
| MODIFY | `vidbyte/lib/tracing/base.py` | Widen `TracerBase.end_span`/`end_trace` abstract signatures |
| MODIFY | `vidbyte/trace/debug.py` | Widen `DebugTracer.end_span`/`end_trace`; record attrs in event log |
| MODIFY | `vidbyte/trace/session.py` | Widen `SessionTracer`/`SessionTraceController` end methods |
| MODIFY | `vidbyte/providers/tracing/otel.py` | Widen `OTelTracer.end_span`/`end_trace`; forward into `_set_attributes` |
| MODIFY | `vidbyte/providers/tracing/phoenix.py` | Widen `PhoenixTracer.end_span`/`end_trace`; richer value coercion |
| MODIFY | `vidbyte/providers/tracing/langsmith.py` | Widen `LangSmithTracer.end_span`/`end_trace`; merge into `outputs` |
| MODIFY | `vidbyte/providers/tracing/langfuse.py` | Widen `LangfuseTracer.end_span`/`end_trace`; forward as `metadata` |
| MODIFY | `vidbyte/agents/multi/tracing.py` | Widen `MultiAgentTracer.end_span` for consistency |
| MODIFY | `vidbyte/agents/pricing/tracker.py` | Add non-mutating `UsageTracker.preview_call`; extract shared `_price_call` |
| MODIFY | `vidbyte/agents/runtime.py` | Add `_llm_trace_outputs`; wire `llm.call` span close to `preview_call` + `output_text` |
| MODIFY | `vidbyte/agents/base.py` | Add `_usage_trace_attributes`; wire `agent.run` trace close to `get_usage()` |
| CREATE | `tests/test_trace_close_attributes.py` | Unit tests for `translate_end`, `TraceController` wiring, all widened tracers |
| CREATE | `tests/test_usage_preview_and_trace_wiring.py` | Unit + integration tests for `preview_call`, no-double-billing, runtime/BaseAgent wiring |
| CREATE | `scripts/test-trace-output-and-usage-attributes.py` | Phase 5 verification script |

---

## 10. Testing Plan

### Unit Tests

`tests/test_trace_close_attributes.py`:
- `describe('ProviderTraceTranslator protocol')` -> `it('TraceController.end_span forwards nothing extra when the translator has no translate_end')` — [Hidden Assumption] (verifies `GenericProviderTranslator`/`LangSmithProviderTranslator` are truly unaffected)
- `describe('ProviderTraceTranslator protocol')` -> `it('TraceController.end_span calls translate_end with the same SpanSpec that opened the span, not a fresh one')` — [Hidden Failure] (would silently lose kind/name context if a new empty spec were built instead of reusing `SemanticSpanContext.spec`)
- `describe('OTelGenAIProviderTranslator.translate_end')` -> `it('maps output_messages/input_tokens/output_tokens/finish_reason to gen_ai.* fields only when present')` — [Silent Failure] (must assert absence when a key is missing, not a zero/empty default — mirrors the existing open-time test's own stated pattern)
- `describe('OTelGenAIProviderTranslator.translate_end')` -> `it('namespaces agent.run usage attributes under vidbyte.usage. rather than inventing a gen_ai.* aggregate field')` — [Hidden Failure] (this is the test that would catch quietly inventing an unverified aggregate spec field, matching PR #390's existing golden-fixture discipline)
- `describe('OpenInferenceProviderTranslator.translate_end')` -> `it('expands output_messages into llm.output_messages.<i>.message.role/.content')` — [Edge Case] (0, 1, and 3-message tuples)
- `describe('OpenInferenceProviderTranslator.translate_end')` -> `it('maps output_tokens/total_tokens to llm.token_count.completion/.total')` — [Silent Failure]
- `describe('translate_end fallback')` -> `it('namespaces every unrecognized key under vidbyte. for a generic (e.g. algorithm.reflexion.trial) span close')` — [Hidden Failure]
- `describe('DebugTracer')` -> `it('records close-time attributes in the event log without dropping output/error')` — [Edge Case]
- `describe('OTelTracer.end_span')` -> `it('sets a tuple-of-dicts attribute (output_messages) via the existing JSON coercion, not a Python repr')` — [Silent Failure] (would previously have been unreachable code — this is a new path)
- `describe('PhoenixTracer.end_span')` -> `it('coerces a non-primitive close-time attribute the same way OTelTracer does, not via str())')` — [Silent Failure] (the crude `str(value)` coercion `start_span` uses today would corrupt a message list into an unparseable Python-repr string)
- `describe('LangSmithTracer.end_span')` -> `it('merges attributes into outputs alongside the existing "output" key without overwriting it')` — [Hidden Assumption]
- `describe('every widened tracer')` -> `it('end_span(context, output=...) with no attributes behaves identically to before this change')` — [Hidden Assumption] (regression guard across all 8 tracers)

`tests/test_usage_preview_and_trace_wiring.py`:
- `describe('UsageTracker.preview_call')` -> `it('returns the same UsageRecord shape record_call would, without appending to records')` — [Silent Failure] (assert `len(tracker.records) == 0` after `preview_call`, not just that a value came back)
- `describe('UsageTracker.preview_call')` -> `it('does not call mark_recording_corrupted on a malformed payload')` — [Hidden Assumption] (a preview parse failure is not a lost real record)
- `describe('UsageTracker.preview_call')` -> `it('calling preview_call N times followed by one record_call results in exactly one record')` — [Hidden Failure] (the core no-double-billing guarantee, directly targeted)
- `describe('UsageTracker.record_call')` -> `it('behavior and return value are unchanged by the _price_call refactor')` — [Hidden Assumption] (regression guard on the extracted-method refactor)
- `describe('AgentRuntime._invoke_with_middleware')` -> `it('llm.call span close carries output_messages, input_tokens, output_tokens when the provider response is well-formed')` — [Edge Case]
- `describe('AgentRuntime._invoke_with_middleware')` -> `it('llm.call span close carries only output_messages, omitting all usage fields, when the provider is unrecognized')` — [Silent Failure] (must not emit zero-value placeholders)
- `describe('AgentRuntime._invoke_with_middleware')` -> `it('a failed model call (exception path) attaches no usage attributes to end_span')` — [Edge Case]
- `describe('AgentRuntime._invoke_with_middleware')` -> `it('a full multi-iteration agent run ends with usage_tracker.records length equal to the number of successful model calls, not double')` — [Hidden Failure] (integration-level version of the no-double-billing guarantee, across the real call path this design doc modifies)
- `describe('BaseAgent._usage_trace_attributes')` -> `it('returns empty dict when no model calls were made this run')` — [Edge Case]
- `describe('BaseAgent._usage_trace_attributes')` -> `it('omits cost_usd when the rollup cost is None, rather than emitting null/0')` — [Silent Failure]
- `describe('BaseAgent.generate_reply')` -> `it('agent.run end_trace call carries the full-run usage rollup on success')` — [Edge Case]
- `describe('BaseAgent.generate_reply')` -> `it('agent.run end_trace call on the error path attaches no usage attributes')` — [Hidden Assumption] (documents the deliberate Section 6.7 scope boundary)

### Integration Tests
- Full flow: `Trace.otel_genai(...)` (or `DebugTracer` standing in for the OTel wire format, per existing PR #390 test convention) wrapping a `BaseAgent` with a stubbed runner returning a fixed usage payload — run one prompt, one tool call, assert the exported `llm.call` span carries `gen_ai.output.messages`/`gen_ai.usage.input_tokens`/`.output_tokens`, and the `agent.run` trace carries `vidbyte.usage.total_tokens`/`.cost_usd`.
- Same flow under `Trace.openinference(...)`, asserting `llm.output_messages.0.message.content` and `llm.token_count.completion`.
- Fallback flow (`AgentFallback` mid-run model switch): confirm usage from *both* the pre-switch and post-switch model calls is separately recorded once each (not merged, not dropped, not doubled) — this exercises `preview_call`/`record_call` across the one existing code path (`_fallback_transition`) that already calls `_invoke_with_middleware` more than once per logical turn.
- Silent-failure path to watch for specifically: a translator that only implements `translate_start` (e.g. a real user's custom translator written before this feature existed) must see literally zero behavior change — this can only be caught by an integration test that constructs such a translator and asserts the exported span is byte-identical to a pre-this-PR run, not just "doesn't crash."
- Hidden assumption the integration surfaces that unit tests can't: `UsageTracker` is constructed once per `BaseAgent` and `reset()` at the start of every `generate_reply` (`base.py:595`) — a unit test of `preview_call` in isolation can't catch a regression where `_usage_trace_attributes` accidentally reads a *stale* rollup from a previous turn; only a two-turn integration test (call `generate_reply` twice, assert the second trace's usage reflects only the second turn) catches this.

### Manual / QA Test Cases
1. Given an agent configured with `Trace.otel_genai(endpoint="http://localhost:4318/v1/traces")` pointed at a local OTel collector in debug-exporter mode, when the agent answers one prompt with no tool calls, then the collector's console output shows the `chat <model>` span's attributes including a populated `gen_ai.output.messages` and non-zero `gen_ai.usage.output_tokens` — not just `output.value`. — [Silent Failure]
2. Given the same setup with `provider="openinference"`, when the same run executes, then the span shows `llm.output_messages.0.message.content` matching the model's actual reply text. — [Silent Failure]
3. Given an agent whose configured provider/model is not in the pricing registry (an unpriced or unknown model), when it completes a run, then the `agent.run` trace shows no `vidbyte.usage.cost_usd` attribute at all, rather than `cost_usd: null` or `cost_usd: 0`. — [Edge Case]
4. Given an agent with a configured fallback chain that switches models mid-run after a provider error, when the run completes, then `usage_tracker.get_usage().model_call_count` equals the number of *successful* model calls across both models, not inflated by the preview computed for tracing. — [Hidden Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| PR #390 (`feat/otel-genai-openinference-trace-shapes`) | unmerged branch, this repo | Supplies `ProviderTraceTranslator`, `OTelGenAIProviderTranslator`, `OpenInferenceProviderTranslator`, `OTelTracer`, `Trace.otel_genai`/`Trace.openinference` — this doc's changes are additive on top of that code | This doc's branch must be based on that branch, not a fresh `main` pull, until #390 merges (Section 12) |
| `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http` | as pinned by PR #390 | Unchanged; `OTelTracer._set_attributes` (reused, not modified in shape) | None new |
| OTel GenAI semantic conventions spec | `open-telemetry/semantic-conventions-genai` (live, pre-1.0) | Source of truth for `gen_ai.output.messages`/`gen_ai.usage.*`/`gen_ai.response.finish_reasons` field names | Spec is pre-1.0 and evolving — re-verify live during implementation per PR #390's own established practice, not from this doc's memory of it |
| OpenInference semantic conventions spec | `Arize-ai/openinference` | Source of truth for `llm.output_messages.*`/`llm.token_count.*` | Same as above |

---

## 12. Rollout & Deployment

- **Not a breaking change** — every modified signature only widens (new optional `**attributes`/method); no existing caller anywhere in the repo needs to change.
- **No feature flag** — this is SDK-internal library behavior, not a runtime toggle; a caller opts in simply by using `Trace.otel_genai(...)`/`Trace.openinference(...)` as before, and now gets richer spans automatically.
- **Branch basing is the one deployment decision that needs explicit sign-off before Phase 3.** This feature's code depends directly on types (`ProviderTraceTranslator`, `OTelGenAIProviderTranslator`, `OpenInferenceProviderTranslator`, `OTelTracer`) that exist only on the still-unmerged `feat/otel-genai-openinference-trace-shapes` branch (PR #390). The project's own field guide / prior-incident memory on this repo (stacked-PR orphan risk: PRs based on feature branches have silently lost merged work twice) says to always target `main`. The reconciled approach: create this feature's worktree **from `feat/otel-genai-openinference-trace-shapes`** (since the dependency is real, not just convenient), but open the resulting PR with `--base main` (not the intermediate branch) — so GitHub's diff naturally shrinks to just this doc's commits once PR #390 merges into `main`, rather than this PR silently losing its identity if the intermediate branch is later deleted. This is called out explicitly rather than silently deviating from the skill's literal "branch from a clean main pull" instruction.
- **Rollback:** revert is a plain `git revert` of this feature's commits; nothing here is migrated data or a deployed service.

---

## 13. Open Questions

- [ ] Does the OTel GenAI spec define a real `gen_ai.usage.*` field for cache-read/cached input tokens, or should `cached_input_tokens` stay namespaced under `vidbyte.` indefinitely? Must be checked live against the spec during implementation (Section 6.3), not assumed.
- [ ] Is there an existing, already-parsed "finish reason" available anywhere in `raw_result`/`runner_metadata` today, or does surfacing `gen_ai.response.finish_reasons` require a small new extraction helper? `_llm_trace_outputs` (Section 6.6) currently assumes one is discoverable; if none exists yet, this field should be dropped from this doc's scope rather than invented.
- [ ] Should a *failed* run's `agent.run` trace (the `error` path in `base.py:631-645`) still attach whatever partial `UsageRollup` exists at the point of failure? This doc currently says no (Section 6.7) to avoid conflating "usage so far" with "usage for a completed run" — worth confirming that's the right call before implementation, since a failed expensive run's cost being invisible in tracing could itself be a real cost-visibility gap.
- [ ] Confirm empirically (against a real MLflow tracking server, not just its docs) that this feature alone makes `Trace.otel_genai(...)` render correctly in MLflow's UI, per the Non-Goals note — if it doesn't, a dedicated MLflow translator becomes a real follow-up rather than a deferred one.

---

## 14. Alternatives Considered

### Alternative 1: Pass an `attributes: Mapping[str, Any]` single parameter instead of `**attributes: Any`
- What: `end_span(context, *, output=None, error=None, attributes=None)` — one extra parameter instead of variadic kwargs.
- Why rejected: `start_span`/`start_trace` already use `**attributes: Any` throughout the codebase (every call site passes attributes as kwargs, e.g. `self._tracer.start_span("llm.call", parent=..., **self._llm_trace_inputs(...))`). Matching that existing convention on the close side keeps the two halves of the contract symmetric and lets call sites keep using the same `**helper_dict()` pattern they already use for opening a span.

### Alternative 2: Make `_invoke_with_middleware` call `usage_tracker.record_call` directly (removing the later call at `runtime.py:412`) instead of adding a non-mutating `preview_call`
- What: Move the real, ledger-mutating `record_call` earlier, into `_invoke_with_middleware`, and delete the later duplicate call.
- Why rejected: `_invoke_with_middleware`'s own docstring states its keyword signature is frozen because `reflexion.py` and `multi_provider_agentic_grader.py` call it directly as an external contract. Its current return type (`tuple[object | AgentResult, int, int]`) doesn't carry a `UsageRecord` back to the caller, and changing that return shape would break those external callers. `preview_call` gets the same data to the span-close site without touching that contract at all, at the cost of parsing the response payload twice per call (cheap — a small in-memory dict, not a network or disk operation).

### Alternative 3: Build a dedicated MLflow `ProviderTraceTranslator` now, alongside this feature
- What: Add `Trace.mlflow(...)` and an `MLflowProviderTranslator` in this same doc, since MLflow was researched earlier in this project as a candidate.
- Why rejected: Databricks' own "third-party OTel span attributes" documentation indicates MLflow already remaps raw `gen_ai.*` attributes on ingestion, including `gen_ai.output.messages` → `mlflow.spanOutputs` — meaning this feature (closing the `gen_ai.output.messages` gap) is likely sufficient for MLflow without any MLflow-specific code. Building a dedicated translator before confirming that empirically risks duplicate, unverified work; moved to Section 13 as a follow-up verification step instead.
