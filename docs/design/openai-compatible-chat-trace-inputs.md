# Design Doc: OpenAI-Compatible Chat Trace Inputs

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-05
**Last Updated:** 2026-06-05

---

## 1. Overview

Fix two related SDK observability and execution bugs found while running a tool-enabled MBPP eval through xAI/Grok. OpenAI-compatible chat providers currently omit the system prompt whenever conversation history exists, which means follow-up tool-loop iterations can lose the instruction to call `isDone`. LangSmith LLM span inputs also split `system`, `prompt`, and history `messages` across separate fields, making later iterations look like they only received assistant code blocks. This change preserves the system prompt in actual OpenAI-compatible request payloads and records clearer provider-visible trace input messages.

---

## 2. Goals & Non-Goals

### Goals

- Preserve system instructions for every OpenAI-compatible chat completion request, including xAI, OpenRouter, DeepSeek, GLM, and MiniMax follow-up turns with history.
- Keep existing history preservation behavior for multi-turn agent runs.
- Make LLM trace inputs show the actual provider-visible message ordering: system, prior history, and current user prompt.
- Keep current top-level trace fields (`system`, `prompt`, `messages`, `tool_count`, `tool_names`) compatible for existing trace consumers.
- Keep the change tightly scoped to provider payload construction and trace input shape.

### Non-Goals

- Do not change agent loop stop semantics for plain assistant text with no tool call.
- Do not change `isDone` parsing or tool-call parsing.
- Do not change MBPP eval prompts or eval report/grader behavior.
- Do not add provider-specific prompt engineering for xAI/Grok.
- Do not add new dependencies or external tracing services.

---

## 3. Background & Context

- The user ran `vidbyte-evals/evals/mbpp/agent_5_tools_execution_grader.py` against `vidbyte-sdk` with LangSmith tracing enabled.
- The trace `69e51ddf-7ccc-4415-a678-cbe69b65b47c` showed iteration 0 with the expected system/tool context, then later iterations with `messages` containing only assistant code-block history.
- Source inspection showed `AgentRuntime._build_iteration_call_options()` passes system text separately from provider history. `AgentRuntime._llm_trace_inputs()` records these as separate `system`, `prompt`, and `messages` fields.
- A fake transport reproduction showed the real OpenAI-compatible JSON payload drops the system prompt when `TextModelConfig.messages` is non-empty:
  - Current `_create_messages()` returns `history + current user prompt`.
  - It only prepends the system message in the no-history branch.
- This affects xAI because `XAIProvider` inherits `OpenAICompatibleProvider`.
- The SDK is a Python 3.11 package using `setuptools`, `pydantic`, and `httpx`, with `unittest` tests under `tests/`.

---

## 4. Requirements

### Functional Requirements

1. When an OpenAI-compatible provider receives both `system` text and non-empty `config.messages`, the generated request `messages` must include a leading `{"role": "system", "content": system}` message before history.
2. When `system` is absent but `config.system` is set, the generated request `messages` must include a leading system message before history.
3. When neither call-level nor config-level system text exists, message construction must remain history followed by the current user prompt.
4. The current user prompt must remain the final user message in OpenAI-compatible chat payloads.
5. Existing tool, tool-choice, response-format, metadata, sampling, endpoint, and timeout behavior must remain unchanged.
6. LLM trace inputs must include an explicit provider-visible message list that combines system, prior messages, and current user prompt.
7. LLM trace inputs must retain existing top-level `system`, `prompt`, and `messages` fields for compatibility.
8. Trace input construction must continue using safe trace helpers so secret-like metadata is not emitted.

### Non-Functional Requirements

- Performance: message construction remains linear in the number of history messages and adds no network calls.
- Scalability: no new shared mutable state or global configuration.
- Security: no API keys, tokens, secrets, credentials, or auth headers are added to traces.
- Observability: trace inputs become easier to inspect in LangSmith without removing existing fields.
- Reliability / error tolerance: malformed or non-mapping history behavior remains consistent with existing `dict(message)` assumptions.

---

## 5. High-Level Design

The provider fix lives in `OpenAICompatibleProvider._create_messages()`. Instead of treating history as an alternate path that bypasses system construction, the method will always construct messages in the same order: resolved system instructions if present, existing history, then the current user prompt. This preserves agentic-loop and tool instructions across follow-up calls while keeping existing history and current prompt behavior.

The trace fix lives in `AgentRuntime._llm_trace_inputs()`. The runtime already has all pieces required to show the provider-visible prompt: `system`, `messages`, and `message`. It will add a new trace field, tentatively `input_messages`, that mirrors the OpenAI-compatible provider-visible ordering. Existing `messages` remains available as raw runtime history so current tests and consumers do not break.

```text
AgentRuntime
  -> call_options: {system, tools, messages(history)}
  -> trace inputs: {system, prompt, messages(history), input_messages(system+history+user)}
  -> TextModelRunner
  -> OpenAICompatibleProvider
  -> HTTP payload messages: system + history + user prompt
```

The design intentionally avoids changing the core loop behavior. If a model returns plain assistant text instead of a tool call, the runtime may still append that text as assistant history and continue until `isDone` or budget stop. This change makes the follow-up request retain the model-visible instructions needed for the model to recover and call `isDone`.

---

## 6. Detailed Design

### 6.1 OpenAI-Compatible Message Construction

**File(s):** `vidbyte/providers/compatible.py`
**Type:** Modified

#### What it does

Builds chat-completions payload messages for OpenAI-compatible providers, including xAI/Grok.

#### Interface / API

```python
def _create_messages(self, config: TextModelConfig, prompt: str, system: str | None) -> list[Mapping[str, Any]]:
```

#### Logic / Algorithm

1. Resolve `instructions = system or config.system`.
2. Start with an empty `messages` list.
3. If `instructions` is present, append `{"role": "system", "content": instructions}`.
4. Extend with `dict(message)` for each item in `config.messages`.
5. Append `{"role": "user", "content": prompt}`.
6. Return `messages`.

#### Edge Cases & Error Handling

- If `config.messages` is empty, output remains system plus current user prompt, matching existing no-history behavior.
- If `config.messages` is non-empty and `instructions` is absent, output remains history plus current user prompt, matching existing history behavior.
- If history already includes a system message, this method may produce two system messages. The runtime currently passes assistant/tool history, not system history. No de-duplication will be added because removing user-supplied history would be a broader semantic change.
- Existing `dict(message)` conversion continues to surface malformed history as an exception.

---

### 6.2 LLM Trace Input Shape

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Builds bounded, sanitized inputs for the `llm.call` trace span.

#### Interface / API

```python
def _llm_trace_inputs(self, handle: RunnerHandle, *, message: str, call_options: Mapping[str, Any], provider: str, iteration_count: int, model_call_count: int, metadata: Mapping[str, Any]) -> dict[str, Any]:
```

#### Logic / Algorithm

1. Continue reading `system`, `messages`, and `tools` from `call_options`.
2. Continue storing top-level `prompt`, `system`, and `messages` as today.
3. Build a provider-visible `input_messages` list:
   1. Add `{"role": "system", "content": system}` if `system` is present.
   2. Add each runtime/provider history message from `messages`.
   3. Add `{"role": "user", "content": message}`.
4. Sanitize `input_messages` through `_safe_trace_value()`.
5. Preserve `tool_count` and `tool_names` behavior.

#### Edge Cases & Error Handling

- If `system` is absent, `input_messages` starts with history.
- If `messages` is empty, `input_messages` contains just system plus user prompt, or just user prompt if system is absent.
- If a history item is not a mapping, `_safe_trace_value()` preserves current broad behavior by converting values safely for tracing instead of changing runtime execution.
- Trace construction must not raise for ordinary values that the current trace path accepts.

---

## 7. Data Model Changes

N/A - No persistent schema, database table, serialized model, or migration is changed.

---

## 8. API Changes

N/A - No public HTTP endpoint, SDK constructor, method signature, or exported type changes.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/openai-compatible-chat-trace-inputs.md` | Design record for provider payload and trace input fixes |
| CREATE | `scripts/test-openai-compatible-chat-trace-inputs.py` | Verification script required by the design-doc workflow |
| MODIFY | `vidbyte/providers/compatible.py` | Preserve system prompt when OpenAI-compatible chat history exists |
| MODIFY | `vidbyte/agents/runtime.py` | Add provider-visible `input_messages` to LLM trace inputs |

---

## 10. Testing Plan

The user noted that new tests or scripts are not required for this task. The scenarios below define the verification surface for implementation review and can be run manually or converted to tests if desired.

### Unit Tests

- `[Silent Failure] OpenAICompatibleProvider._create_messages includes system before history` - Given `system="System"` and one assistant history message, when `_create_messages()` runs, then the first message is the system message, the second is history, and the last is the user prompt.
- `[Edge Case] OpenAICompatibleProvider._create_messages preserves no-history behavior` - Given `system="System"` and no history, when `_create_messages()` runs, then the result is system plus user prompt.
- `[Edge Case] OpenAICompatibleProvider._create_messages preserves no-system history behavior` - Given no system and one assistant history message, when `_create_messages()` runs, then the result is history plus user prompt.
- `[Hidden Assumption] OpenAICompatibleProvider._create_messages uses config.system when call-level system is absent` - Given `config.system="Configured"` and no call-level system, when `_create_messages()` runs, then the configured system is prepended.
- `[Silent Failure] AgentRuntime._llm_trace_inputs exposes provider-visible input_messages` - Given system, history, prompt, and tools, when `_llm_trace_inputs()` runs, then `input_messages` is system, history, user prompt in order.
- `[Hidden Failure] AgentRuntime._llm_trace_inputs keeps existing messages field` - Given history messages, when `_llm_trace_inputs()` runs, then `messages` remains the raw history field for backward compatibility.
- `[Hidden Assumption] AgentRuntime._llm_trace_inputs does not leak secret metadata` - Given metadata with `LANGSMITH_API_KEY` and `XAI_API_KEY`, when `_llm_trace_inputs()` runs, then those keys are absent from trace metadata.

### Integration Tests

- `[Silent Failure] TextModelRunner xAI payload includes system on follow-up turn` - Use a fake HTTP transport and a xAI `TextModelRunner` call with `system`, history `messages`, and tools. Verify the captured `json_body["messages"]` includes system first and user prompt last.
- `[Silent Failure] Tool-loop follow-up trace is readable` - Use a fake runner and recording tracer where iteration 0 returns plain assistant text and iteration 1 stops. Verify the second `llm.call` span contains both `messages` history and provider-visible `input_messages`.
- `[Hidden Failure] Existing tool payload fields still pass through` - Use fake transport with tools, tool choice, response format, and metadata. Verify those fields remain unchanged after the message construction fix.

### Manual / QA Test Cases

1. `[Silent Failure]` Given a one-case MBPP tool eval with `max_iterations=10`, when it is run against xAI with LangSmith tracing, then the latest trace's later `llm.call` inputs show `input_messages` containing the system prompt before assistant history.
2. `[Hidden Assumption]` Given a follow-up xAI provider call with assistant history, when inspecting the fake or captured provider payload, then the system message is present even though history exists.
3. `[Edge Case]` Given a no-history direct text call, when inspecting the provider payload, then it remains system plus user prompt.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| xAI Chat Completions | `https://api.x.ai/v1/chat/completions` via registry defaults | OpenAI-compatible chat provider affected by message ordering | Provider may have stricter rules around multiple system messages; this change only prepends the SDK system when supplied |
| LangSmith | `LANGSMITH_ENDPOINT` / `https://api.smith.langchain.com` | Stores `agent.run` and `llm.call` trace inputs | Larger trace payloads from `input_messages`, bounded by existing safe trace handling |
| Python stdlib / unittest | Python `>=3.11` | Local verification and existing test framework | No new dependency |

---

## 12. Rollout & Deployment

- No feature flag is planned because the provider behavior is a correctness fix.
- This is not intended as a breaking API change.
- Deployment is a normal SDK release or PR merge into `main`.
- Rollback procedure: revert the provider and runtime changes. This restores prior trace shape and prior OpenAI-compatible message construction.
- The change affects all OpenAI-compatible chat providers inheriting `OpenAICompatibleProvider`, not only xAI.

---

## 13. Open Questions

- [ ] Should `input_messages` become the preferred trace field name, or should it be named `provider_messages` to match middleware terminology?
- [ ] Should the provider de-duplicate system messages if caller-supplied history already includes a `role=system` message? Current design avoids de-duplication to preserve caller history exactly.
- [ ] Should a future PR change agent-loop semantics so plain assistant text can be treated as a final answer when no tools are required, or is strict `isDone` still desired?

---

## 14. Alternatives Considered

### Alternative 1: Move system prompt into runtime `messages`

- What: Have `AgentRuntime._build_iteration_call_options()` add system and user prompt directly into `messages`.
- Why rejected: The SDK already separates `system`, current prompt, and provider history, and providers such as OpenAI Responses, Anthropic, and Gemini use different system/message layouts. Pushing provider-specific structure into runtime would blur boundaries.

### Alternative 2: Only change tracing, not provider payload

- What: Add `input_messages` to traces but leave `OpenAICompatibleProvider._create_messages()` unchanged.
- Why rejected: Fake transport reproduction proves the provider payload actually drops system instructions on history turns. A trace-only fix would hide the real execution bug.

### Alternative 3: Stop looping on plain assistant text

- What: Treat a non-tool assistant response as the final answer in agentic loops.
- Why rejected: Existing README behavior says the loop continues until `isDone` or budget stop. Changing that would be a broader runtime semantics change and could break tool-loop workflows that expect intermediate assistant text.

### Alternative 4: Force `tool_choice` to `isDone`

- What: Force the model to call `isDone` after generating code or make `isDone` mandatory.
- Why rejected: This is provider/model behavior tuning, not a fix for the observed SDK payload and trace bugs. It could also prevent legitimate intermediate tool use.
