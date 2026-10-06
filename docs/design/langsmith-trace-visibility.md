# Design Doc: LangSmith Trace Visibility — Agent Run Hierarchy & Context Window Capture

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-25
**Last Updated:** 2026-06-25

---

## 1. Overview

This change fixes two LangSmith tracing bugs in the Vidbyte SDK that prevent
users from inspecting agent behavior in the job-applier harness. First,
`agent.run` spans are misclassified as `run_type="tool"` instead of
`run_type="chain"`, which makes LangSmith display them as leaf tool calls
rather than expandable container nodes — hiding the system prompt, tools, and
child LLM/tool spans that are already being recorded. Second, the per-iteration
context window (the full message history sent to the LLM at each loop step) is
not captured in the LLM trace span, so users can only see a single snapshot of
the initial user message instead of the evolving conversation.

---

## 2. Goals & Non-Goals

### Goals
- Fix `LangSmithTracer.start_span` run_type classification so `agent.run` spans appear as `chain` containers in LangSmith's trace tree
- Make each `agent.run` visible as a clickable, expandable entry in the LangSmith left sidebar, with all agents in one session grouped under a single root trace
- Capture the full per-iteration context window (system prompt, conversation messages, tool schemas) in each `llm.call` span so users can inspect exactly what the model saw at every loop step
- Allow callers to optionally override `run_type` via an attribute so future span types are not locked into name-based heuristics

### Non-Goals
- Replacing the name-based run_type heuristic entirely (it remains the default; override is opt-in)
- Changing the `TracerBase` abstract interface signature (no new mandatory parameters)
- Modifying the Langfuse or Phoenix tracer implementations (they are not used by the job-applier harness today)
- Moving the `langchain-tracing` skill from Codex to opencode (separate concern, documented as follow-up)
- Changing the `SessionTracer` session-grouping design (it is correct; the bug is in the SDK tracer's run_type)

---

## 3. Background & Context

The job-applier harness uses a `SessionTracer` wrapper
(`vidbyte-harnesses/.../agents/tracing.py`) that groups every agent run under
one root LangSmith trace per run session. `begin_session()` opens a root trace
via `LangSmithTracer.start_trace()`; each subsequent `BaseAgent.generate_reply()`
call enters `SessionTracer.start_trace()`, which converts the call to
`LangSmithTracer.start_span(parent=root_ctx)` so all agent invocations land in
the same trace tree.

The trace hierarchy that **should** appear in LangSmith is:

```
job-applier-run (chain, root trace)
├── agent.run (chain, agent 1)
│   ├── llm.call (llm, iteration 1)
│   ├── tool.call (tool, iteration 1)
│   └── llm.call (llm, iteration 2)
├── agent.run (chain, agent 2)
│   └── llm.call (llm, iteration 1)
└── agent.run (chain, agent 3)
    └── ...
```

Instead, the user sees only a flat view with one user-message snapshot because
`agent.run` spans are created with `run_type="tool"`, which LangSmith renders as
non-expandable leaf nodes.

### Current state

- `LangSmithTracer.start_span` (langsmith.py:118) classifies run_type with a
  binary heuristic: `"llm"` if the name starts with `"llm."`, otherwise
  `"tool"`. There is no `"chain"` branch, so `agent.run` — the most important
  container span — is misclassified as `"tool"`.
- `BaseAgent.generate_reply` (base.py:443-453) already passes `system_prompt`,
  `tools`, `prompt`, `provider`, `model`, and `metadata` as attributes to
  `start_trace("agent.run", ...)`. These become `inputs` in LangSmith but are
  invisible when the run is displayed as a tool leaf.
- `AgentRuntime._llm_trace_inputs` (runtime.py:1106-1142) captures `system`,
  `messages`, `tool_count`, `tool_names`, `prompt`, and `metadata` for each
  LLM call. However, `messages` comes from `call_options.get("messages")`
  which may be empty on the first iteration (the initial user message is passed
  separately as the `message` positional arg). The `system` string includes
  the system prompt + loop settings + primitives zone + context body, but this
  is only visible if the user can drill into the `llm.call` span — which
  requires the parent `agent.run` to be an expandable `chain` node.

---

## 4. Requirements

### Functional Requirements
1. `agent.run` spans created via `LangSmithTracer.start_span` must use
   `run_type="chain"` so LangSmith displays them as expandable container nodes
   in the trace tree.
2. `llm.call` spans must continue to use `run_type="llm"`.
3. `tool.call` spans must continue to use `run_type="tool"`.
4. Any span whose name does not match `llm.*` or `tool.*` must default to
   `run_type="chain"` (the LangSmith convention for container/agent runs).
5. Callers must be able to override the run_type by passing
   `run_type="..."` as a span attribute. When present, this value is used
   directly and removed from the `inputs` payload so it does not leak into
   trace data.
6. Each `llm.call` span must capture the full context window sent to the model
   at that iteration: the system string, the complete conversation messages
   list (including the initial user message when it is the first iteration),
   and the tool schemas.
7. The initial user message must appear in the `llm.call` span's `messages`
   field on iteration 0 even when `call_options["messages"]` is empty — the
   runtime must synthesize a `{"role": "user", "content": message}` entry.
8. All existing trace attributes (agent_name, provider, model, iteration,
   model_call, prompt, metadata) must continue to be captured.

### Non-Functional Requirements
- **Performance:** The additional context window capture must not add more
  than 5% overhead to the tracing path. Tracing remains best-effort and
  non-blocking; errors in the tracer never propagate to break the agent loop.
- **Backward compatibility:** The `start_span` signature remains
  `(self, name, parent, **attributes)`. The `run_type` override is popped
  from `**attributes` so existing callers that do not pass it are unaffected.
- **Observability:** The fix is verifiable by running the job-applier harness
  with tracing enabled and confirming in LangSmith that (a) multiple
  `agent.run` entries appear under one trace and (b) each `llm.call` span
  shows the full message history.
- **Reliability:** The `_call_langsmith` error swallowing is preserved — a
  failed `create_run` or `update_run` still records the error without raising
  (unless strict mode is on).

---

## 5. High-Level Design

The fix has two components, both in the SDK:

**Component A — run_type classification** (langsmith.py): Replace the binary
`"llm" if name.startswith("llm.") else "tool"` heuristic with a three-way
classification: `"llm"` for `llm.*`, `"tool"` for `tool.*`, and `"chain"` for
everything else. Add support for an optional `run_type` attribute that callers
can pass to override the heuristic. The attribute is popped from `inputs`
before the LangSmith `create_run` call so it does not appear as trace data.

**Component B — context window capture** (runtime.py): Enhance
`_llm_trace_inputs` to synthesize the initial user message into the `messages`
list on iteration 0 when `call_options["messages"]` is empty. This ensures the
first LLM call's trace span shows the full context the model saw, not an empty
message list.

Together, these changes make LangSmith display the expected trace tree:
multiple `agent.run` chain entries under one root, each expandable to show
`llm.call` and `tool.call` children with full context window inputs.

```
LangSmith Trace Tree (after fix)

job-applier-run (chain)
├── agent.run (chain)          ← was "tool", now "chain" (expandable)
│   ├── inputs: system_prompt, tools, prompt, provider, model
│   ├── llm.call (llm)
│   │   └── inputs: system, messages (full context), tool_names, iteration
│   ├── tool.call (tool)
│   └── llm.call (llm)
│       └── inputs: system, messages (updated context), tool_names
├── agent.run (chain)
│   └── ...
```

---

## 6. Detailed Design

### 6.1 LangSmithTracer.start_span — run_type classification fix

**File:** `vidbyte/providers/tracing/langsmith.py`
**Type:** Modified

#### What it does
Classifies each child span's `run_type` correctly so LangSmith renders the
trace tree with the right node types (chain containers, LLM calls, tool calls).

#### Interface / API
```python
def start_span(
    self,
    name: str,
    parent: SpanContext | None = None,
    **attributes: Any,
) -> LangSmithSpanContext:
    ...
```

No signature change. The `run_type` override is extracted from `**attributes`.

#### Logic / Algorithm
1. Pop `run_type` from `attributes` if present (default: `None`).
2. If `run_type` is `None`, infer from name:
   - `name.startswith("llm.")` → `"llm"`
   - `name.startswith("tool.")` → `"tool"`
   - otherwise → `"chain"`
3. Use the resolved `run_type` in the `create_run` call.
4. The remaining `attributes` (with `run_type` removed) become `inputs`.

#### Edge Cases & Error Handling
- If a caller passes `run_type="invalid_value"`, LangSmith will reject the
  run creation. The `_call_langsmith` handler catches this and records the
  error without raising (unless strict mode is on). This is existing behavior
  and no change is needed.
- If `run_type` is passed as a non-string (e.g., `None` explicitly), it is
  treated as "not provided" and the name-based heuristic runs.

---

### 6.2 AgentRuntime._llm_trace_inputs — context window capture fix

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does
Ensures the `llm.call` trace span captures the complete context window sent to
the model at each iteration, including the initial user message on iteration 0.

#### Interface / API
```python
def _llm_trace_inputs(
    self,
    handle: RunnerHandle,
    *,
    message: str,
    call_options: Mapping[str, Any],
    provider: str,
    iteration_count: int,
    model_call_count: int,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    ...
```

No signature change.

#### Logic / Algorithm
1. Build the `inputs` dict as today (agent_name, provider, model, iteration,
   model_call, prompt, metadata).
2. Capture `system` from `call_options.get("system")` if present (existing).
3. Capture `messages` from `call_options.get("messages")` if present (existing).
4. **New:** If `messages` is empty/None and `iteration_count == 0`, synthesize
   `messages = [{"role": "user", "content": message}]` so the first LLM call
   shows the user's prompt in the context window.
5. Capture tool info (tool_count, tool_names) as today (existing).
6. **New:** Add `context_window_summary` field — a lightweight text summary
   that concatenates system length, message count, and tool count for at-a-glance
   visibility in LangSmith's run list view.

#### Edge Cases & Error Handling
- If `call_options["messages"]` is an empty tuple/list on iteration > 0, leave
  it as-is (the messages may genuinely be empty if the runner uses a different
  message-passing convention).
- The `_safe_trace_value` / `_trace_text` wrappers still apply, truncating
  any string longer than 12,000 chars. This prevents oversized trace payloads.

---

### 6.3 SessionTracer — no changes needed

**File:** `vidbyte-harnesses/harnesses/job_applier/agents/tracing.py`
**Type:** Unchanged

The `SessionTracer` correctly converts `start_trace` → `start_span` when inside
a session, and correctly propagates `parent_run_id` and `trace_id`. The bug
was purely in the SDK's `run_type` classification, not in the session wrapper.

---

## 7. Data Model Changes

N/A - No schema changes. LangSmith run metadata is freeform JSON; the fix only
changes the `run_type` field value and adds optional fields to the `inputs`
payload.

---

## 8. API Changes

N/A - No public API endpoint changes. The `start_span` method signature is
unchanged; the `run_type` override is an optional attribute that existing
callers do not need to pass.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/providers/tracing/langsmith.py` | Fix run_type classification: add "chain" default, support optional run_type override attribute |
| MODIFY | `vidbyte/agents/runtime.py` | Enhance _llm_trace_inputs: synthesize initial user message on iteration 0, add context_window_summary field |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| langsmith | installed via pip | Python client for LangSmith trace run creation | Low — no API change, just correct run_type values that the client already accepts |
| LangSmith API | https://api.smith.langchain.com | Trace storage and UI | None — run_type="chain" is a standard LangSmith run type |

---

## 11. Rollout & Deployment

- **Feature flags:** No feature flag needed. The fix is a bugfix to existing
  tracing behavior. Tracing remains opt-in via `TracingConfig.enabled`.
- **Breaking change:** No. Existing callers that do not pass `run_type` as an
  attribute get the corrected heuristic (which is strictly better: `agent.run`
  now gets `chain` instead of `tool`). No caller currently depends on
  `agent.run` being classified as `tool`.
- **Deployment order:** Single SDK change. Reinstall the SDK with
  `pip install -e .` in the harness environment.
- **Rollback:** Revert the two file changes. Tracing continues to work but
  with the original misclassification.

---

## 12. Open Questions

- [ ] Should the `run_type` override attribute be standardized across all
      tracer implementations (Langfuse, Phoenix) or kept LangSmith-specific?
      Current design: LangSmith-specific (popped from attributes before the
      create_run call). If other tracers receive `run_type` in attributes, it
      will silently appear in their inputs — harmless but slightly noisy.
- [ ] Should the `context_window_summary` field be added to the `agent.run`
      span as well (not just `llm.call`), so users can see a high-level
      overview without drilling into each LLM call? Current design: only in
      `llm.call` since that is where the full context is available.

---

## 13. Alternatives Considered

### Alternative 1: Add run_type as a mandatory parameter to TracerBase.start_span
- **What:** Change the abstract `start_span` signature to
  `start_span(self, name, parent, *, run_type="chain", **attributes)` and
  update all three tracer implementations.
- **Why rejected:** Changes the abstract interface, requiring updates to
  Langfuse, Phoenix, and any custom tracers. The attribute-based override is
  backward-compatible and achieves the same result without interface churn.

### Alternative 2: Fix run_type in the SessionTracer instead of the SDK
- **What:** Have `SessionTracer.start_trace` pass `run_type="chain"` as an
  attribute when it delegates to `LangSmithTracer.start_span`.
- **Why rejected:** The bug affects ALL `start_span` calls with non-`llm.`
  names, not just `agent.run` through the SessionTracer. Fixing it in the SDK
  tracer fixes it for every caller, including direct SDK users who don't use
  the harness's SessionTracer.

### Alternative 3: Use LangSmith's @traceable decorator instead of manual create_run
- **What:** Replace the manual `client.create_run` / `client.update_run` calls
  with LangSmith's `@traceable` decorator on agent methods.
- **Why rejected:** Massive refactor that changes the tracing architecture
  fundamentally. The current manual approach gives fine-grained control over
  span names, parents, and timing. The bug is a one-line classification fix,
  not an architectural problem.
