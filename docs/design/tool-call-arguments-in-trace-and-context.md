# Design Doc: Tool-Call Arguments in Trace and Context Window

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-14
**Last Updated:** 2026-06-14

---

## 1. Overview

Today a `tool.call` span and the agent's own next-turn conversation history both record only the **tool name** — the **arguments** the model actually requested are dropped on the floor. This makes eval traces impossible to audit (GitHub issue #141) and, more seriously, means the agent re-reads a tool *result* on the next turn with no record of *what it asked for*. This change threads the requested arguments (plus call ID and provider) into **two distinct consumer surfaces**: the LangSmith/Langfuse/Phoenix trace (for human reviewers) and the provider message history (for the model itself). Each surface gets its own argument policy because the consumers differ.

---

## 2. Goals & Non-Goals

### Goals
- **Trace (issue #141):** a `tool.call` span input records tool name, sanitized arguments, provider, call ID, and a stable `arguments_fingerprint` so a reviewer can group repeated calls by *input* without inferring from output text.
- **Trace close:** the span records execution `state` (succeeded/failed/denied) and an `output_fingerprint` so a reviewer can answer "did identical arguments produce identical output?".
- **Context window:** when the agent calls tools, a provider-native **assistant tool-call turn carrying the arguments** is appended to history before the tool results, so the next model turn sees `read_file{path, line_range}` — not a free-floating result.
- Fix the latent well-formedness bug where Anthropic `tool_result` blocks are emitted with no preceding `tool_use` block.
- One shared serialization foundation (`ToolsFormatter.format_assistant_tool_calls`) so both surfaces sit on one tested primitive.

### Non-Goals
- **No secret redaction in the context window.** The model legitimately needs argument values; silently stripping them corrupts the agent's own memory. Context gets *size-capping only*. Redaction is trace-only.
- No change to how tools are *parsed* from model responses (`parse_tool_calls` is untouched).
- No new tracing backend, no change to span hierarchy/parenting.
- No per-tool argument allowlist (left as a follow-up `# TODO`).
- No change to the `IS_DONE` internal-tool control flow.

---

## 3. Background & Context

The SWE-bench eval trace `973e4286-8271-41f8-b21e-61e71da0eebc` (agent `swe-bench-tools_eval`) had 86 tool calls (`read_file` ×32, `glob` ×19, `grep` ×19, `run_tests` ×16). Every `tool.call` span input was just `{"tool_name": "read_file"}`. Reviewers could not see which path/pattern/test target was requested, so repeated-call diagnosis — the entire point of the eval — required guessing from output hashes.

Investigation (this PR's originating conversation) found the data is **already in hand** at both failure points:

- `runtime.py:956` opens the span with only `tool_name=call.tool_name`, yet `call.arguments`, `call.call_id`, and `provider` are all in scope.
- `runtime.py:437–453` runs the per-call loop; the only thing appended to the `messages` history is `ToolsFormatter.format_tool_result(...)` (`runtime.py:1304`), which serializes output + call_id + name and **drops arguments**. There is a `parse_tool_calls` (provider → `ToolCall`) but **no inverse serializer**, so the assistant `tool_use`/`function_call` turn that carried the arguments is never reconstructed into history.

So both bugs share one upstream fact and diverge only on consumer + policy.

### Constraints / dependencies
- Python ≥ 3.11, stdlib only for new logic (`hashlib`, `json`) — no new dependencies (`pyproject.toml` deps are `pydantic`, `httpx`).
- `end_span` is an abstract contract implemented by `NullTracer`, `LangSmithTracer`, `LangfuseTracer`, `PhoenixTracer`. Widening it touches all four.
- Existing sanitizer `_safe_trace_value` / `_is_secret_trace_key` (`runtime.py:845–859`) and truncator `_trace_text` (`runtime.py:1410`) must be reused, not reinvented.

---

## 4. Requirements

### Functional Requirements

**Trace (issue #141):**
1. The `tool.call` span input MUST include: `tool_name`, `provider`, `call_id` (nullable), `arguments` (secret-redacted mapping), `arguments_text` (redacted + truncated string for display), and `arguments_fingerprint` (stable 12-hex-char hash of the redacted arguments).
2. Secret-like argument keys (`API_KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `CREDENTIAL`, `AUTH`) MUST be removed from traced arguments via the existing `_safe_trace_value`.
3. Oversized argument payloads MUST be truncated in `arguments_text` (reuse `_trace_text`, 12000-char cap) so a 50 KB write body does not dominate the trace request.
4. The span close MUST record `state` (`succeeded` | `failed` | `denied`) and, on success, an `output_fingerprint` (stable 12-hex-char hash of `result.output`).
5. `arguments_fingerprint` MUST be identical for two calls with equal arguments (order-independent over mapping keys) and differ when arguments differ.

**Context window:**
6. When the model emits one or more non-`IS_DONE` tool calls in a turn, the runtime MUST append exactly one provider-native assistant message carrying all of those calls (name + arguments + call_id) to `messages`, before the corresponding tool-result messages.
7. Argument **values** in the context message MUST NOT be secret-redacted (the model needs them). String values longer than the configured cap (`self.algorithm.max_tool_result_chars`) MUST be truncated for token control.
8. The assistant tool-call message MUST be well-formed for the active provider family (OpenAI/xAI `tool_calls` array; Anthropic `tool_use` content blocks; Gemini `functionCall` parts) so that the subsequent `tool_result`/`tool` messages pair correctly.
9. `IS_DONE` tool calls MUST be excluded from the echoed assistant message (symmetry with the result-append exclusion at `runtime.py:1300`), so no dangling `tool_use` is produced.
10. If a turn contains only `IS_DONE`, no assistant tool-call message is appended.

### Non-Functional Requirements
- **Performance:** fingerprints are single SHA-256 over a `json.dumps(sort_keys=True)` string; negligible. Context echo adds tokens per turn — bounded by the existing `max_tool_result_chars` cap.
- **Backward compatibility:** `end_span` widening is additive (new keyword-only param defaulting to `None`); all existing callers and adapters keep working.
- **Security:** trace path must never leak credential-shaped argument keys. Context path deliberately retains values (documented invariant).
- **Observability:** this *is* the observability change; verified via `RecordingTracer` span-input assertions.
- **Reliability:** all new serialization is pure and total — non-serializable values coerce via `str()`/`default=str`; never raises into the agent loop.

---

## 5. High-Level Design

Three coordinated changes on one shared foundation.

```
                 model response (raw)
                          |
              ToolsFormatter.parse_tool_calls   (UNCHANGED)
                          |
                    tuple[ToolCall]  ── arguments, call_id ──┐
                          |                                   |
            ┌─────────────┴───────────────┐                  |
            v                              v                  |
   CONTEXT SURFACE                  TRACE SURFACE             |
   (the model re-reads)             (humans review)          |
            |                              |                  |
 ToolsFormatter                  runtime._tool_trace_inputs   |
 .format_assistant_tool_calls    (redact + fingerprint)       |
 (size-cap, NO redact)                     |                  |
            |                       tracer.start_span         |
 messages.append(assistant turn)   ("tool.call", **inputs)    |
            |                              |                  |
 messages.append(tool_result)      tracer.end_span(           |
 (existing, unchanged)               state, output_fingerprint)
```

**Shared foundation.** A new `ToolsFormatter.format_assistant_tool_calls(calls, text, provider_or_model, max_arg_chars=None)` is the missing inverse of `parse_tool_calls`. It builds one grouped, provider-native assistant message. The context surface calls it directly. (The trace surface does not need provider-native shaping — it records a flat sanitized dict — so it reuses the runtime's existing `_safe_trace_value`/`_trace_text` rather than the formatter.)

**Trace surface.** A new runtime method `_tool_trace_inputs(call, provider)` mirrors the existing `_llm_trace_inputs`, producing the redacted dict + fingerprint, passed into `start_span` at `runtime.py:956`. The `end_span` contract is widened with an optional `metadata` mapping; the tool-span close passes `{"state": ..., "output_fingerprint": ...}`.

**Context surface.** In the tool loop, immediately before `for call in tool_calls:` (`runtime.py:437`), append the grouped assistant message for the non-`IS_DONE` calls. The existing per-call result append (`runtime.py:1304`) is unchanged, so each `tool_use` now pairs with its `tool_result`.

Key decisions:
- **Two policies, one source.** Redact-for-trace vs truncate-for-context is the central decision; encoded as separate code paths, never shared.
- **Group per turn, not per call.** Anthropic/OpenAI require one assistant message with N tool calls; building it once before the loop (rather than inside per-call processing) is the only correct shape.
- **Fingerprints over output-text correlation.** Input fingerprint is a stronger signal than output hashing (different args can collide on identical output — the exact ambiguity #141 calls out).

---

## 6. Detailed Design

### 6.1 `ToolsFormatter.format_assistant_tool_calls` — shared serializer

**File:** `vidbyte/lib/tools/formatter.py`
**Type:** Modified (new public static method + private per-provider helpers)

#### What it does
Builds one provider-native **assistant** message that carries a group of tool calls (name + arguments + call id), the inverse of `parse_tool_calls`. Optionally size-caps oversized string argument values.

#### Interface / API
```python
@staticmethod
def format_assistant_tool_calls(calls: Sequence[ToolCall], text: str, provider_or_model: str, max_arg_chars: int | None = None) -> Mapping[str, Any]:
    # Builds one assistant message carrying a turn's tool calls and arguments for follow-up requests.

# private per-provider builders (mirror the existing to_*_tool / parse_* split):
@staticmethod
def _assistant_tool_calls_openai(calls, text, max_arg_chars) -> dict[str, Any]: ...
@staticmethod
def _assistant_tool_calls_anthropic(calls, text, max_arg_chars) -> dict[str, Any]: ...
@staticmethod
def _assistant_tool_calls_gemini(calls, text, max_arg_chars) -> dict[str, Any]: ...
@staticmethod
def _cap_arguments(arguments: Mapping[str, Any], max_arg_chars: int | None) -> dict[str, Any]:
    # Truncates oversized string argument values for token control; never removes keys.
```

#### Logic / Algorithm
1. `provider = ToolsFormatter.provider_from_model(provider_or_model)` (reuse existing family resolver).
2. For each call, `args = ToolsFormatter._cap_arguments(call.arguments, max_arg_chars)`; `call_id = call.call_id or call.tool_name`.
3. Dispatch to the provider builder:
   - **openai/xai:** `{"role": "assistant", "content": text or None, "tool_calls": [{"id": cid, "type": "function", "function": {"name": n, "arguments": json.dumps(args)}} ...]}`
   - **anthropic:** `{"role": "assistant", "content": ([{"type": "text", "text": text}] if text else []) + [{"type": "tool_use", "id": cid, "name": n, "input": args} ...]}`
   - **gemini:** `{"role": "model", "parts": ([{"text": text}] if text else []) + [{"functionCall": {"name": n, "args": args}} ...]}`
4. `_cap_arguments`: for each value, if `isinstance(value, str)` and `max_arg_chars` set and `len > max_arg_chars`, replace with `_truncate(...)` (reuse the module's existing `f"{text[:max_chars]}...[truncated]"` shape — `formatter.py` already has a truncate helper at line 1410-equivalent? No: that is in runtime; add a local one-liner here). Non-string values pass through unchanged. Keys are never dropped.
5. `json.dumps(..., default=str)` guards non-serializable values in the OpenAI arguments string.

#### Edge Cases & Error Handling
- Empty `calls` → caller never invokes this (guarded in runtime); defensively returns a bare assistant message with no tool calls.
- `text` empty/`None` → omit the text block (Anthropic/Gemini) or set `content: None` (OpenAI).
- `call_id` `None` → fall back to `tool_name` (mirrors `format_tool_result`, `formatter.py:124`).
- Non-mapping / non-JSON argument values → `default=str` coercion; never raises.

---

### 6.2 `runtime._tool_trace_inputs` — trace input builder

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified (new method, mirrors `_llm_trace_inputs` at line 793)

#### What it does
Builds the sanitized, inspectable input dict for the `tool.call` span.

#### Interface / API
```python
def _tool_trace_inputs(self, call: ToolCall, provider: str) -> dict[str, Any]:
    # Builds secret-redacted, fingerprinted tool-call inputs for trace providers.
```

#### Logic / Algorithm
1. `safe_args = self._safe_trace_value(dict(call.arguments))` — reuse existing recursive secret filter.
2. Return:
```python
{
    "tool_name": call.tool_name,
    "provider": provider,
    "call_id": call.call_id,
    "arguments": safe_args,
    "arguments_text": _trace_text(safe_args),          # existing 12k truncator
    "arguments_fingerprint": _args_fingerprint(safe_args),
}
```
3. Wire at `runtime.py:956`: `start_span("tool.call", parent=trace_context, **self._tool_trace_inputs(call, provider))`.

#### Edge Cases & Error Handling
- Empty arguments → `arguments={}`, fingerprint of `{}` (stable constant); harmless.
- Secret key present → removed before hashing, so fingerprint reflects the redacted view (two calls differing only in a secret value would collide — acceptable; secrets aren't a correlation dimension).

---

### 6.3 Module-level fingerprint helpers

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified (new module-level helpers beside `_trace_text` at line 1410)

```python
def _args_fingerprint(arguments: Mapping[str, Any]) -> str:
    # Stable 12-char hash of arguments, order-independent over mapping keys.
    blob = json.dumps(arguments, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]

def _output_fingerprint(output: str) -> str:
    # Stable 12-char hash of a tool output for repeated-call correlation.
    return hashlib.sha256(output.encode("utf-8")).hexdigest()[:12]
```
(Style note: matches the existing module-level `_trace_text` / `_safe_trace_mapping` helper convention in this file rather than introducing a new class, per Phase-1 conventions.)

---

### 6.4 `end_span` contract widening

**Files:** `vidbyte/lib/tracing/base.py`, `vidbyte/providers/tracing/langsmith.py`, `vidbyte/providers/tracing/langfuse.py`, `vidbyte/providers/tracing/phoenix.py`
**Type:** Modified (additive, backward-compatible)

#### What it does
Lets a span carry structured close-time metadata (execution state, output fingerprint).

#### Interface / API
```python
# base.py TracerBase + NullTracer
def end_span(self, context: SpanContext, *, output: str | None = None, error: Exception | None = None, metadata: Mapping[str, Any] | None = None) -> None: ...
```

#### Logic / Algorithm
- **NullTracer:** unchanged no-op (already `**_`).
- **LangSmith** (`langsmith.py:132`): merge `metadata` into the `outputs` dict on the success branch: `outputs={"output": output, **(metadata or {})}`. On the error branch, attach as `extra`/`outputs` too so state is still visible.
- **Langfuse** (`langfuse.py:105`): pass `metadata` into `context.handle.update(...)` (Langfuse spans accept `metadata=`).
- **Phoenix** (`phoenix.py:100`): `for k, v in (metadata or {}).items(): span.set_attribute(f"tool.{k}", v)`.

#### Wire-in (`runtime.py` `execute_tool_call`)
At each `end_span(tool_span, ...)` call (lines 976, 980, 989, 998, 1006), pass `metadata={"state": state.value, ...}`. On the success path (line 976) also include `"output_fingerprint": _output_fingerprint(result.output)`.

#### Edge Cases & Error Handling
- `metadata=None` (every existing caller) → behaves exactly as before.
- Adapter that ignores metadata (e.g. a backend without custom fields) → silently dropped inside the existing `try/except` guards; never raises.

---

### 6.5 Context-window assistant echo

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified (insertion in the tool loop)

#### What it does
Appends the grouped assistant tool-call message (with arguments) to `messages` before the per-call result appends.

#### Logic / Algorithm
Insert immediately before `for call in tool_calls:` (currently `runtime.py:437`):
```python
echoable = tuple(c for c in tool_calls if c.tool_name != IS_DONE_TOOL_NAME)
if echoable:
    messages.append(dict(ToolsFormatter.format_assistant_tool_calls(echoable, last_assistant_output, provider, max_arg_chars=self.algorithm.max_tool_result_chars)))
```
`last_assistant_output` is already bound at `runtime.py:324`; `self.algorithm.max_tool_result_chars` is the existing context cap used by `ToolResultCompactionMiddleware` (`runtime.py:86`).

#### Edge Cases & Error Handling
- Turn = only `IS_DONE` → `echoable` empty → nothing appended; loop returns as today.
- Turn = `[realTool, IS_DONE]` → assistant echoes only `realTool`; its result is appended at 1304; `IS_DONE` result is intentionally not appended (line 1300) → perfectly paired, no dangling block.
- Middleware `DENY_TOOL` → a result is still appended (denied path), so the echoed `tool_use` still pairs.
- Middleware `ABORT_RUN` mid-loop → loop returns without re-sending `messages`; transient imbalance never reaches a provider.

---

## 7. Data Model Changes

N/A — no persistent schema changes. `ToolCall`, `ToolResult`, `ToolCallContext`, and `ToolCallState` are unchanged. `ToolCallContextItem` (`records.py:58`) already carries `arguments` and is untouched. The only new "shapes" are transient trace-input dicts and provider message dicts.

---

## 8. API Changes

N/A — no HTTP/public API endpoints. The one internal contract change is `TracerBase.end_span` (Section 6.4), additive and backward-compatible. `ToolsFormatter.format_assistant_tool_calls` is a new internal static method; no existing signature changes.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/tool-call-arguments-in-trace-and-context.md` | This design doc (first commit) |
| MODIFY | `vidbyte/lib/tools/formatter.py` | New `format_assistant_tool_calls` + per-provider builders + `_cap_arguments` |
| MODIFY | `vidbyte/agents/runtime.py` | `_tool_trace_inputs`, fingerprint helpers, span-open wiring (956), span-close metadata (976/980/989/998/1006), context echo (437) |
| MODIFY | `vidbyte/lib/tracing/base.py` | Widen `end_span` (TracerBase + NullTracer) with `metadata` kw |
| MODIFY | `vidbyte/providers/tracing/langsmith.py` | Merge `metadata` into run outputs |
| MODIFY | `vidbyte/providers/tracing/langfuse.py` | Pass `metadata` to span update |
| MODIFY | `vidbyte/providers/tracing/phoenix.py` | Set `metadata` as span attributes |
| MODIFY | `tests/test_tracing.py` | Span-input + span-close assertions (extend `RecordingTracer` to capture `metadata`) |
| MODIFY | `tests/test_agent_tool_loop.py` | Assert assistant tool-call message appended with arguments, per provider |
| CREATE | `tests/test_tool_call_argument_serialization.py` | Round-trip + fingerprint + redaction-vs-truncation unit tests |
| CREATE | `scripts/test_tool_call_arguments_in_trace_and_context.py` | Phase-5 verification script covering every Section-10 case |

---

## 10. Testing Plan

### Unit Tests

**Serializer — `tests/test_tool_call_argument_serialization.py`**
- `format_assistant_tool_calls` round-trips through `parse_tool_calls` for OpenAI: `parse(format([call])) == [call]` — [Silent Failure] (wrong serialization that still "looks" valid)
- …same round-trip for Anthropic (`tool_use` blocks) — [Silent Failure]
- …same round-trip for Gemini (`functionCall` parts) — [Silent Failure]
- Multi-call turn → exactly ONE assistant message with N tool calls (not N messages) — [Hidden Assumption] (one-call-per-turn)
- Anthropic multi-call assistant message + N `tool_result` blocks form a valid `tool_use`/`tool_result` pairing — [Hidden Failure]
- `_cap_arguments` truncates a 50 000-char string value but keeps the key — [Edge Case]
- `_cap_arguments` does NOT redact a key named `api_key` (value survives in context) — [Hidden Assumption] (context ≠ trace policy)
- Empty `text` → no text block / `content: None` per provider — [Edge Case]
- `call_id=None` → falls back to `tool_name` — [Edge Case]
- Non-serializable argument value (e.g. a set) → `default=str` coercion, no raise — [Hidden Failure]

**Fingerprints**
- `_args_fingerprint({"a":1,"b":2}) == _args_fingerprint({"b":2,"a":1})` (order-independent) — [Silent Failure] (key-order-sensitive hash would falsely separate identical calls)
- Different arguments → different fingerprint — [Edge Case]
- `_args_fingerprint({})` is stable and non-empty — [Edge Case]

**Trace inputs — `tests/test_tracing.py`**
- `tool.call` span input contains `arguments`, `call_id`, `provider`, `arguments_fingerprint` — [Silent Failure] (the #141 regression)
- A secret-keyed argument (`{"token": "xai-..."}`) is absent from span `arguments` — [Hidden Assumption] (trace must redact)
- `arguments_text` for an oversized argument is truncated with the `...[truncated]` marker — [Edge Case]
- Span close records `state="succeeded"` and an `output_fingerprint` on success — [Silent Failure]
- Span close records `state="failed"` on tool error and `state="denied"` on permission denial — [Edge Case]
- `RecordingTracer.end_span` receives `metadata` (extend the double) — [Hidden Failure] (param silently dropped)

**Context loop — `tests/test_agent_tool_loop.py`**
- After an OpenAI tool turn, `runner.calls[1]` history includes an `assistant` message whose `tool_calls[0].function.arguments` contains the requested args — [Silent Failure] (the core context bug)
- A turn containing only `isDone` appends NO assistant tool-call message — [Hidden Assumption]
- A `[realTool, isDone]` turn echoes only `realTool` (no dangling `isDone` tool_use) — [Hidden Failure]
- `end_span`/history unaffected when tracer is `NullTracer` (default path) — [Edge Case]

### Integration Tests
- Full `Agent.run` loop with the `ToolCallingRunner` double (existing pattern in `test_agent_tool_loop.py`): two-iteration run (tool call → final answer); assert the second runner invocation's `messages` contains both the assistant tool-call message (args present) and the tool-result message, in that order. Mock: the runner; real: runtime + formatter. Silent-failure path guarded: arguments present but truncated vs missing entirely.
- Tracing integration via `RecordingTracer` (no real LangSmith): one agent run produces a `tool.call` span with full inputs and a close `metadata` carrying state + output fingerprint. Hidden assumption surfaced: that runners rely on runtime-managed `messages` and do not independently inject the assistant tool-call turn (would double it) — asserted by counting assistant messages.

### Manual / QA Test Cases
1. Run an agent against a real Anthropic model with a multi-tool turn; confirm the provider does not 400 on `tool_use`/`tool_result` pairing — [Hidden Failure]. (This is the well-formedness fix; must be checked live, not just in unit tests.)
2. Inspect a LangSmith `tool.call` span for a `read_file` call: confirm `arguments` shows the path and `arguments_fingerprint` is present; call the same tool twice with identical args and confirm matching fingerprints — [Silent Failure].
3. Run a tool whose argument contains a large blob; confirm the trace truncates it and the context message truncates it, while a short secret-keyed arg is redacted in trace but present in context — [Hidden Assumption].

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `hashlib`, `json` (stdlib) | — | Fingerprints / serialization | None |
| LangSmith / Langfuse / Phoenix client SDKs | existing | Trace sinks (real runs only; tests use `RecordingTracer`) | Low — `end_span` change is additive and guarded by existing `try/except` |
| Provider runners (OpenAI/Anthropic/Gemini/xAI) | existing | Consume the new assistant message | Medium — must confirm runners don't independently inject the assistant turn (QA #1, integration test) |

---

## 12. Rollout & Deployment

- **Feature flags:** none. The behavior is strictly more-correct; gating would add complexity for no benefit.
- **Breaking change:** none externally. `end_span`'s new param is keyword-only with a default. The context echo changes the *content* of provider history toward well-formedness — the main risk vector is a runner that already injects the assistant turn (QA #1 / integration test covers it).
- **Deployment order:** single package; no multi-service ordering.
- **Rollback:** revert the PR. No persisted state, no migrations.

---

## 13. Open Questions

- [ ] Do any production runners independently reconstruct the assistant tool-call turn from the raw response (which would now duplicate it)? Integration test + QA #1 must confirm before un-drafting the PR.
- [ ] Should `output_fingerprint` also be recorded on the *failed* branch (error text correlation), or success-only? Doc currently does success-only; trivially extendable.
- [ ] Is `max_tool_result_chars` the right cap for argument truncation in context, or should arguments get an independent (larger) budget since they're usually smaller than results? Defaulting to the shared cap; revisit if eval token cost spikes.

---

## 14. Alternatives Considered

### Alternative 1: Text-staple arguments onto the tool-result message
- **What:** Prepend `Arguments: {...}` into the `format_tool_result` content instead of adding a real assistant turn.
- **Why rejected:** Not provider-native, pollutes the result message, leaves the Anthropic `tool_result`-without-`tool_use` bug unfixed, and confuses the model with a non-standard shape. The inverse serializer is barely more work and fixes well-formedness too.

### Alternative 2: One assistant message per tool call (inside `_process_tool_call`)
- **What:** Append an assistant message per call rather than one grouped message per turn.
- **Why rejected:** Anthropic/OpenAI require a single assistant message carrying all N tool calls in a turn; per-call messages produce malformed multi-tool turns. Grouping before the loop is the only correct shape.

### Alternative 3: Reuse `_safe_trace_value` for the context arguments too
- **What:** Apply the same secret-redaction to context as to trace.
- **Why rejected:** The model often legitimately needs the argument value; redacting it silently corrupts the agent's own working memory and can break subsequent reasoning. Context gets size-capping only; redaction is trace-only. This is the central design invariant.

### Alternative 4: Leave `end_span` alone; encode state/output in the `output` string
- **What:** Avoid the contract change by stuffing state + fingerprint into the span output text.
- **Why rejected:** Mixing structured metadata into free-text output is exactly the brittleness #141 complains about. An additive keyword param across four adapters is small and keeps the data structured and queryable.

---

## Summary

- **Files:** 3 created (1 doc, 1 unit test, 1 verification script), 8 modified.
- **Key risks:** (1) a runner that already injects the assistant tool-call turn would now double it — covered by an integration test + live QA before un-drafting; (2) the live Anthropic pairing must be verified end-to-end, not just in unit tests.
- **Open questions:** runner double-injection, failed-branch output fingerprint, argument truncation budget (Section 13).

**Awaiting explicit approval before proceeding to Phase 3 (worktree) and implementation.**
