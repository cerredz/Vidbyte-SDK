# Design Doc: LangSmith Default Tracing

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-29
**Last Updated:** 2026-06-29

---

## 1. Overview

This feature adds a first-class `Trace.langsmith_default(...)` preset for the Vidbyte SDK and tightens the default single-agent LangSmith trace payload. Developers will be able to enable the SDK's recommended LangSmith tracing with one agent constructor argument while seeing clearer LangSmith-native `agent.run`, `llm.call`, and `tool.call` runs that expose system prompt, user prompt, tool schemas, tool input, and tool output without writing custom tracer code.

---

## 2. Goals & Non-Goals

### Goals

- Add a discoverable `Trace.langsmith_default(...)` factory method for the recommended single-agent LangSmith tracing preset.
- Preserve the existing low-level `Trace.langsmith(...)` helper for callers who want the raw provider adapter.
- Keep developer enablement to one line: `trace=Trace.langsmith_default(...)`.
- Reuse the existing `LangSmithTracer`, `TracerBase`, `BaseAgent(trace=...)`, and `AgentRuntime` span emission paths.
- Keep LangSmith run type behavior aligned with its native UI defaults: `agent.run` as `chain`, `llm.call` as `llm`, and `tool.call` as `tool`.
- Ensure `llm.call` span inputs explicitly expose the system prompt, user prompt, full message list, provider, model, iteration, tool schemas, and context-window summary.
- Ensure `tool.call` span inputs explicitly expose tool name, sanitized tool input/arguments, call ID, provider, and sanitized call metadata.
- Continue closing `llm.call` with model output and `tool.call` with tool output or error.
- Document the difference between `Trace.langsmith(...)`, `Trace.langsmith_default(...)`, and future session/multi-agent tracing.
- Update SDK skill references so future tracing changes know where default LangSmith preset logic belongs.

### Non-Goals

- Do not implement multi-agent/session grouping in this change; that is covered by `docs/design/session-tracer.md`.
- Do not add new LangSmith run types such as `retriever`, `embedding`, `prompt`, or `parser` in this first default preset.
- Do not add `agent.iteration`, middleware-decision, permission-decision, retry, or context-build spans in this change.
- Do not change the `TracerBase` abstract interface.
- Do not change `LangSmithTracer` constructor behavior, endpoint behavior, strict mode, flushing, or error swallowing.
- Do not add new mandatory dependencies or optional dependency groups.
- Do not remove or rename `Trace.langsmith(...)`.
- Do not add new tests or verification scripts under this no-tests workflow.

---

## 3. Background & Context

The SDK already has a provider-neutral tracing contract under `vidbyte/lib/tracing/`. `BaseAgent` accepts `trace=` or `tracer=`, starts one `agent.run` root trace in `generate_reply()`, and passes the trace context to `AgentRuntime`. `AgentRuntime` emits `llm.call` spans around model invocations and `tool.call` spans around tool execution. The public `Trace` facade in `vidbyte/trace/base.py` currently exposes `Trace.langsmith(...)`, which constructs the existing `LangSmithTracer`.

The current single-agent tree is already close to the desired shape:

```text
agent.run             run_type="chain"
|-- llm.call          run_type="llm"
`-- tool.call         run_type="tool"
```

LangSmith's native browser treatment is driven by `run_type`, not by the span name alone. The SDK already maps `llm.*` to `llm`, `tool.*` to `tool`, and other spans to `chain` in `LangSmithTracer`. That means `agent.run`, `llm.call`, and `tool.call` are SDK names using LangSmith-native run types.

The missing pieces are ergonomics and payload completeness. Users currently have to know that `Trace.langsmith(...)` is the recommended LangSmith option, and `tool.call` does not include tool arguments in the span input. `llm.call` contains a message list and tools, but the most important values should also be surfaced as explicit fields so they are easier to scan in the LangSmith UI.

The repo also has a separate draft design for `SessionTracer`. This default-tracing design deliberately does not merge that work. A user should later be able to combine both concepts, but this PR should make the single-agent default better first.

---

## 4. Requirements

### Functional Requirements

1. `Trace.langsmith_default(...)` must be available from `vidbyte.trace.Trace`.
2. `from vidbyte import Trace` must expose the same `Trace.langsmith_default(...)` method through the existing root export.
3. `Trace.langsmith_default(...)` must accept the same LangSmith settings as `Trace.langsmith(...)`: `api_key`, `project`, `endpoint`, `strict`, and `include_runtime_info`.
4. `Trace.langsmith_default(...)` must construct and return a `LangSmithTracer` using those forwarded settings.
5. `Trace.langsmith(...)` must remain unchanged and continue returning a plain `LangSmithTracer`.
6. Existing `Agent(..., trace=Trace.langsmith_default(...))` must work through the existing `BaseAgent(trace=...)` path.
7. `agent.run` must continue to be the root run for one agent reply and continue to be classified by LangSmith as `run_type="chain"`.
8. `llm.call` must continue to be emitted once per model invocation and continue to be classified by LangSmith as `run_type="llm"`.
9. `tool.call` must continue to be emitted once per executed tool call and continue to be classified by LangSmith as `run_type="tool"`.
10. `llm.call` inputs must include an explicit `prompt` field containing the current user prompt.
11. `llm.call` inputs must include an explicit `user_prompt` field containing the current user prompt.
12. `llm.call` inputs must include an explicit `system` field when a system string is present.
13. `llm.call` inputs must include an explicit `system_prompt` field when a system string is present.
14. `llm.call` inputs must continue including the full `messages` list in chat-message shape.
15. `llm.call` inputs must include `input_messages` as an alias of `messages` for LangSmith scanability.
16. `llm.call` inputs must include tool schemas when tools are present.
17. `llm.call` inputs must include `tool_names` and `tool_count` when tools are present.
18. `llm.call` inputs must keep `context_window_summary`.
19. `tool.call` inputs must include `tool_name`.
20. `tool.call` inputs must include sanitized `tool_input`.
21. `tool.call` inputs must include sanitized `arguments` as an alias of `tool_input`.
22. `tool.call` inputs must include `call_id` when one exists.
23. `tool.call` inputs must include `provider`.
24. `tool.call` inputs must include sanitized call metadata when present.
25. Existing output behavior must remain: `llm.call` closes with model output, and `tool.call` closes with tool result output or error.
26. Existing secret-key filtering behavior must be reused for new prompt, message, tool schema, tool input, and metadata payloads.
27. README documentation must show the recommended one-line default usage.
28. `vidbyte/trace/README.md` must document the preset and the run tree it produces.
29. SDK skill files must mention `Trace.langsmith_default(...)` as the recommended single-agent LangSmith tracing helper.

### Non-Functional Requirements

- Performance: payload enrichment must remain simple dictionary construction and must not add network calls or extra provider SDK calls.
- Security: new payload fields must use the existing safe trace helpers so API keys, tokens, secrets, passwords, credentials, auth values, and `LANGSMITH_*` metadata keys are filtered.
- Reliability: the new preset must not change provider error behavior; missing LangSmith dependency or credentials still raise `TracerConfigurationError` during tracer construction, while delivery failures keep existing adapter behavior.
- Compatibility: existing `Trace.langsmith(...)`, `trace=`, `tracer=`, `DebugTracer`, `NullTracer`, and custom tracer behavior must remain valid.
- Observability: the resulting default LangSmith trace should be understandable in the browser without user-written wrappers.
- Maintainability: provider-neutral runtime payload enrichment belongs in `vidbyte/agents/runtime.py`; LangSmith construction helpers belong in `vidbyte/trace/base.py`; provider delivery remains in `vidbyte/providers/tracing/langsmith.py`.

---

## 5. High-Level Design

The public API change is intentionally small: add `Trace.langsmith_default(...)` beside `Trace.langsmith(...)`. The method returns the existing `LangSmithTracer`; it is a named preset rather than a new provider adapter class. This keeps the developer workflow seamless:

```python
from vidbyte import Agent, Trace

agent = Agent(
    name="researcher",
    system_prompt="Work carefully.",
    provider="openai",
    model_name="gpt-4.1",
    tools=[lookup_document],
    trace=Trace.langsmith_default(project="vidbyte-agents"),
)
```

The runtime changes are provider-neutral. `AgentRuntime._llm_trace_inputs(...)` will emit more explicit keys for values it already has: prompt, system string, messages, tool schemas, tool names, and counts. `AgentRuntime.execute_tool_call(...)` will enrich `tool.call` span inputs with sanitized arguments and call metadata. These improvements benefit `Trace.debug(...)` and any other tracer too, but they are designed around the LangSmith default browser experience.

The trace tree remains simple and stable:

```text
Agent(trace=Trace.langsmith_default(...))
  |
  v
agent.run                         chain
|-- llm.call                      llm
|   |-- inputs.prompt
|   |-- inputs.system_prompt
|   |-- inputs.messages
|   |-- inputs.tools
|   `-- outputs.output
`-- tool.call                     tool
    |-- inputs.tool_name
    |-- inputs.tool_input
    `-- outputs.output
```

This design does not introduce LangSmith `retriever`, `embedding`, `prompt`, or `parser` runs yet. Those are real LangSmith run types, but the current SDK does not have a single generic retrieval/embedding/prompt-build/parser hook that can be safely mapped without broader design. The default preset should be stable and low-noise; future verbose presets can add those specialized spans where the SDK has clear ownership.

---

## 6. Detailed Design

### 6.1 Trace Facade Default LangSmith Preset

**File(s):** `vidbyte/trace/base.py`
**Type:** Modified

#### What it does

Adds a named public helper for the recommended single-agent LangSmith tracing preset.

#### Interface / API

```python
class Trace:
    @staticmethod
    def langsmith_default(api_key: str | None = None, project: str | None = None, endpoint: str | None = None, strict: bool = False, include_runtime_info: bool = False) -> TracerBase: ...
```

#### Logic / Algorithm

1. Add `Trace.langsmith_default(...)` directly after `Trace.langsmith(...)` or near the provider helpers.
2. Forward `api_key`, `project`, `endpoint`, `strict`, and `include_runtime_info` to `LangSmithTracer`.
3. Return the constructed `LangSmithTracer`.
4. Do not alter `Trace.langsmith(...)`.

#### Edge Cases & Error Handling

- Missing LangSmith package continues to raise `TracerConfigurationError` from `LangSmithTracer`.
- Missing credentials continue to raise `TracerConfigurationError` from `LangSmithTracer`.
- Invalid endpoint or delivery failures keep existing strict/non-strict behavior.

---

### 6.2 LLM Call Trace Inputs

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Makes every `llm.call` span easier to inspect in LangSmith by promoting the most important context-window values to explicit inputs.

#### Interface / API

```python
def _llm_trace_inputs(self, handle: RunnerHandle, *, message: str, call_options: Mapping[str, Any], provider: str, iteration_count: int, model_call_count: int, metadata: Mapping[str, Any]) -> dict[str, Any]: ...
```

#### Logic / Algorithm

1. Keep the existing method and call sites.
2. Continue reading `system`, `messages`, and `tools` from `call_options`.
3. Continue building the chat-style `trace_messages` list with system, historical messages, and current user prompt.
4. Add `prompt` and `user_prompt` fields with `_trace_text(message)`.
5. Add `system` and `system_prompt` fields when `system` exists.
6. Keep `messages` as the full trace message list.
7. Add `input_messages` as the same full trace message list.
8. Keep `tools` when tool schemas are available.
9. Add `tool_names` and `tool_count` when tool schemas are available.
10. Keep provider, model, iteration, model_call, metadata, and context_window_summary.
11. Use `_safe_trace_value(...)`, `_safe_trace_mapping(...)`, and `_trace_text(...)` for all values that may contain user data.

#### Edge Cases & Error Handling

- If `system` is absent, omit `system` and `system_prompt` rather than storing `None`.
- If no tools are present, omit `tools` and use `tool_count=0` in `context_window_summary`.
- If tool schemas are not simple mappings, rely on `_safe_trace_value(...)` to produce bounded trace-safe structures.
- Long prompts and system strings continue to be truncated by `_trace_text(...)`.

---

### 6.3 Tool Call Trace Inputs

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Makes every `tool.call` span show the tool name and sanitized input arguments in LangSmith before the tool output is recorded on span close.

#### Interface / API

```python
async def execute_tool_call(self, call: ToolCall, *, provider: str, trace_context: SpanContext | None = None) -> tuple[ToolCallContext, ToolResult]: ...
```

#### Logic / Algorithm

1. Keep the existing method signature and call sites.
2. Build `tool_input = _safe_trace_value(dict(call.arguments))`.
3. Build `tool_metadata = _safe_trace_mapping(call.metadata)` when metadata exists.
4. Start the span with:
   - `tool_name=call.tool_name`
   - `tool_input=tool_input`
   - `arguments=tool_input`
   - `call_id=call.call_id`
   - `provider=provider`
   - `metadata=tool_metadata`
5. Preserve the existing tool resolution, permission, validation, execution, output-schema validation, and error handling.
6. Preserve existing `end_span(..., output=result.output)` on success or tool-level result errors.
7. Preserve existing `end_span(..., error=exc)` on registry, permission, execution, and unexpected exceptions.

#### Edge Cases & Error Handling

- Empty arguments become `{}`.
- `call_id=None` is acceptable; implementation may pass it through or omit it.
- Secret-like argument and metadata keys are removed by existing safe trace helpers.
- Tool execution failures still return `ToolResult.error(...)` and close the span with an error.

---

### 6.4 README Documentation

**File(s):** `README.md`
**Type:** Modified

#### What it does

Documents the recommended default LangSmith preset in the existing Tracing section.

#### Interface / API

```python
from vidbyte import Agent, Trace

agent = Agent(
    name="observed-agent",
    system_prompt="Work carefully.",
    provider="openai",
    model_name="gpt-4.1",
    tools=[lookup_document],
    trace=Trace.langsmith_default(project="vidbyte-agents"),
)
```

#### Logic / Algorithm

1. Add a short paragraph explaining that `Trace.langsmith_default(...)` is the recommended single-agent LangSmith preset.
2. Show the one-line `trace=` usage.
3. State that it emits `agent.run`, `llm.call`, and `tool.call` with LangSmith-native run types.
4. State that multi-agent/session grouping is handled separately by session tracing once available.

#### Edge Cases & Error Handling

- Documentation must not imply `Trace.langsmith_default(...)` groups multiple agents into one root trace.
- Documentation must not imply retriever, embedding, prompt, or parser spans are emitted yet.

---

### 6.5 Trace Package README

**File(s):** `vidbyte/trace/README.md`
**Type:** Modified

#### What it does

Adds package-level documentation for the LangSmith default preset and the resulting run tree.

#### Interface / API

```python
trace = Trace.langsmith_default(project="vidbyte-agents")
```

#### Logic / Algorithm

1. Add `Trace.langsmith_default(...)` to the usage section.
2. Document the default single-agent tree: `agent.run`, `llm.call`, and `tool.call`.
3. Mention that specialized LangSmith run types are deferred to future verbose/specialized tracing work.

#### Edge Cases & Error Handling

- N/A - documentation-only change.

---

### 6.6 SDK Skill Documentation

**File(s):** `skills/vidbyte-sdk/SKILL.md`, `skills/sdk/SKILL.md`
**Type:** Modified

#### What it does

Updates SDK development guardrails and feature references so future tracing changes preserve the new preset.

#### Interface / API

```text
- Prefer Trace.langsmith_default(...) for user-facing single-agent LangSmith examples.
```

#### Logic / Algorithm

1. Add a rule that public trace facade helpers live in `vidbyte/trace/base.py`.
2. Add a rule or note that `Trace.langsmith_default(...)` is the recommended user-facing single-agent LangSmith helper.
3. Keep provider adapters under `vidbyte/providers/tracing/`.
4. Keep runtime payload enrichment in `vidbyte/agents/runtime.py`.

#### Edge Cases & Error Handling

- N/A - documentation-only change.

---

### 6.7 LLMs Reference

**File(s):** `llms.txt`
**Type:** Modified

#### What it does

Keeps the generated long-form SDK reference aligned with the new public default LangSmith preset.

#### Interface / API

```text
Trace.langsmith_default(...)
```

#### Logic / Algorithm

1. Add `Trace.langsmith_default(...)` near the existing tracing reference text.
2. Mention that it is the recommended single-agent LangSmith preset.
3. Keep wording consistent with README.

#### Edge Cases & Error Handling

- N/A - documentation-only change.

---

## 7. Data Model Changes

### 7.1 LLM Trace Input Dictionary

**Change type:** Modified

```python
{
    "agent_name": str,
    "provider": str,
    "model": str | None,
    "iteration": int,
    "model_call": int,
    "prompt": str,
    "user_prompt": str,
    "system": str,              # present when available
    "system_prompt": str,       # present when available
    "messages": list[dict[str, Any]],
    "input_messages": list[dict[str, Any]],
    "tools": list[dict[str, Any]],      # present when available
    "tool_names": tuple[str, ...],      # present when available
    "metadata": dict[str, Any],
    "context_window_summary": str,
}
```

**Migration strategy:** N/A - in-process trace payload only. Existing consumers should tolerate additive input keys.

### 7.2 Tool Trace Input Dictionary

**Change type:** Modified

```python
{
    "tool_name": str,
    "tool_input": dict[str, Any],
    "arguments": dict[str, Any],
    "call_id": str | None,
    "provider": str,
    "metadata": dict[str, Any],
}
```

**Migration strategy:** N/A - in-process trace payload only. Existing consumers should tolerate additive input keys.

---

## 8. API Changes

### 8.1 Trace Facade API: LangSmith Default

**Change type:** New

**Request:**

```python
trace = Trace.langsmith_default(api_key=None, project=None, endpoint=None, strict=False, include_runtime_info=False)
```

**Response:**

```python
LangSmithTracer(...)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Missing `langsmith` package raises `TracerConfigurationError` |
| N/A | Missing LangSmith API key raises `TracerConfigurationError` |
| N/A | Strict-mode delivery failures raise `TracerConfigurationError` through existing adapter behavior |

### 8.2 Agent Constructor API

**Change type:** Unchanged usage with new preset

**Request:**

```python
agent = Agent(..., trace=Trace.langsmith_default(project="vidbyte-agents"))
```

**Response:**

```python
agent._tracer  # LangSmithTracer instance internally
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Existing `BaseAgent` behavior applies; passing both `trace` and `tracer` raises `ConfigurationError` |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/langsmith-default-tracing.md` | Design doc for the LangSmith default tracing preset |
| MODIFY | `vidbyte/trace/base.py` | Add `Trace.langsmith_default(...)` facade helper |
| MODIFY | `vidbyte/agents/runtime.py` | Enrich `llm.call` and `tool.call` trace inputs |
| MODIFY | `README.md` | Document recommended single-agent LangSmith preset |
| MODIFY | `vidbyte/trace/README.md` | Document trace package default LangSmith behavior |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Update trace guardrails for the default preset |
| MODIFY | `skills/sdk/SKILL.md` | Update SDK developer reference for the default preset |
| MODIFY | `llms.txt` | Keep generated SDK reference aligned with new tracing API |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing `langsmith` optional package | Existing optional adapter behavior | Used by `Trace.langsmith_default(...)` through `LangSmithTracer` | Missing package or credentials raise existing `TracerConfigurationError` |
| LangSmith API | Existing configured endpoint or client default | Stores traces emitted by the existing adapter | Delivery behavior remains best-effort unless `strict=True` |

No new mandatory dependency is added to `pyproject.toml`.

---

## 11. Rollout & Deployment

- No feature flag is required.
- This is additive and backward compatible.
- Existing users can keep using `Trace.langsmith(...)`.
- New users can use `Trace.langsmith_default(...)` as the recommended single-agent LangSmith preset.
- Deployment is a normal SDK package release.
- Rollback procedure: remove `Trace.langsmith_default(...)`, revert the runtime payload additions, and remove related docs. Existing `Trace.langsmith(...)` behavior remains the fallback.

---

## 12. Open Questions

- [ ] Should a future `Trace.langsmith_verbose(...)` add `agent.iteration`, middleware, retry, permission, prompt-build, and parser spans?
- [ ] Should future retrieval and embedding tools emit LangSmith `retriever` and `embedding` run types directly, or should those stay modeled as normal `tool.call` spans?
- [ ] Should `Trace.langsmith_default(...)` eventually return a specialized wrapper object if future default behavior needs runtime options, or is a named facade helper around `LangSmithTracer` enough?

---

## 13. Alternatives Considered

### Alternative 1: Rename `Trace.langsmith(...)` To Mean The Default Preset

- What: Treat the existing helper as the default and only change payloads/docs.
- Why rejected: The user explicitly wants prebuilt options. A named `Trace.langsmith_default(...)` makes the default preset discoverable without breaking callers who already use `Trace.langsmith(...)`.

### Alternative 2: Create A New `DefaultLangSmithTracer` Adapter Class

- What: Add a subclass or wrapper around `LangSmithTracer` for default tracing.
- Why rejected: The default behavior is not provider delivery behavior; it is SDK runtime payload shape. A new adapter would add a type without changing where the meaningful payload data is produced.

### Alternative 3: Add All LangSmith Run Types Immediately

- What: Emit `retriever`, `embedding`, `prompt`, and `parser` spans as part of the default preset.
- Why rejected: The SDK has clear generic ownership for `agent.run`, `llm.call`, and `tool.call`; it does not yet have one safe generic hook for every retrieval, embedding, prompt-build, or parser operation. Adding these now would either be incomplete or noisy.

### Alternative 4: Bundle Session Grouping Into This Default Preset

- What: Make `Trace.langsmith_default(...)` also group multiple agents into one root trace.
- Why rejected: Session grouping is a separate behavior with its own lifecycle and existing design doc. Keeping this preset single-agent avoids hidden global/session state in the default case.
