# Design Doc: Assistant Tool-Call History (#144)

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-15
**Last Updated:** 2026-06-15

---

## 1. Overview

When `AgentRuntime` executes a multi-turn tool loop, each model response that contains tool calls is discarded after its tool results are dispatched. Only the tool-result messages (`{"role": "tool", ...}` / `{"role": "user", "content": [tool_result...]}`) are appended to the conversation history. The assistant message that *decided* to call those tools — containing `tool_calls` (OpenAI) or `tool_use` content blocks (Anthropic) or `functionCall` parts (Gemini) — is never recorded. On the next model call the provider receives tool results orphaned from the decision that triggered them, violating every provider's multi-turn tool-use contract and causing API errors or unpredictable model behavior.

---

## 2. Goals & Non-Goals

### Goals
- Append one assistant/model message to `messages` for every model response that contains tool calls, immediately before the corresponding tool-result messages.
- Support OpenAI chat completions, Anthropic, and Gemini by extracting the assistant turn directly from the raw provider response.
- Keep the fix contained to `ToolsFormatter` and the single insertion point in `_arun_once`.
- Add a new `format_assistant_tool_calls` static method to `ToolsFormatter` following the same pattern as the existing `format_tool_result`.

### Non-Goals
- Fixing the Responses API (OpenAI) multi-turn format. `format_tool_result` already returns chat-completions format for Responses API calls (`{"role": "tool", ...}` instead of `{"type": "function_call_output", ...}`). That is a pre-existing inconsistency tracked separately. `format_assistant_tool_calls` will return `None` for Responses API payloads and skip insertion.
- Modifying how text-only (no-tool-call) assistant turns are recorded. The existing `_assistant_message` path (line 397 of `runtime.py`) is unchanged.
- Changing the `messages` data model or the provider adapters.

---

## 3. Background & Context

### Provider multi-turn contract

Every major provider requires an assistant turn before tool results in the conversation history:

**OpenAI chat completions:**
```
messages = [
  {"role": "user", "content": "do X"},
  {"role": "assistant", "content": null, "tool_calls": [{"id": "call_1", "type": "function", "function": {...}}]},
  {"role": "tool", "tool_call_id": "call_1", "content": "result"},
  {"role": "user", "content": "follow-up"}   # ← next model call includes everything above
]
```

**Anthropic:**
```
messages = [
  {"role": "user", "content": "do X"},
  {"role": "assistant", "content": [{"type": "tool_use", "id": "tu_1", ...}]},
  {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_1", "content": "result"}]}
]
```

**Gemini:**
```
contents = [
  {"role": "user", "parts": [{"text": "do X"}]},
  {"role": "model", "parts": [{"functionCall": {"name": "...", "args": {...}}}]},
  {"role": "function", "parts": [{"functionResponse": {...}}]}
]
```

### Current behavior

`_arun_once` (line 437 of `runtime.py`) loops over `tool_calls` and calls `_process_tool_call` for each. Inside `_process_tool_call` (line 1304), only the tool result is appended:

```python
messages.append(dict(ToolsFormatter.format_tool_result(call, visible_result, provider)))
```

The assistant turn is never appended anywhere in the tool path. The `_assistant_message` helper at line 1400 is only used for non-tool-call final responses.

---

## 4. Requirements

### Functional Requirements
1. `ToolsFormatter` must expose a new static method `format_assistant_tool_calls(raw: object, provider_or_model: str) -> Mapping[str, Any] | None` that returns the assistant turn for a given provider response.
2. For **OpenAI** (chat completions): extract `choices[0]["message"]` from the raw payload and return it as-is (it already contains `role`, `content`, and `tool_calls`).
3. For **Anthropic**: return `{"role": "assistant", "content": <content-list>}` where `<content-list>` is `raw_payload["content"]`.
4. For **Gemini**: return `candidates[0]["content"]` from the raw payload (already `{"role": "model", "parts": [...]}`).
5. For **OpenAI Responses API** (payloads with an `output` list but no `choices`) and any unrecognized shape: return `None`.
6. `_arun_once` in `runtime.py` must append the result of `format_assistant_tool_calls` to `messages` immediately before the `for call in tool_calls:` loop, skipping the append when `None` is returned.
7. When the model returns multiple tool calls in one response (Anthropic batches all `tool_use` blocks into a single content array; OpenAI batches them into one `tool_calls` array), exactly one assistant message must be appended per model response — not one per individual tool call.
8. The fix must not alter behavior for text-only responses (no tool calls) or for any of the middleware decision paths.

### Non-Functional Requirements
- No new external dependencies.
- The new method follows the same static method pattern as `format_tool_result` — no instance state.
- Existing tests must remain passing.

---

## 5. High-Level Design

```
_arun_once (runtime.py)
  │
  ├─ raw_result = await _invoke_with_middleware(...)
  ├─ tool_calls = ToolsFormatter.parse_tool_calls(raw_result, provider)
  │
  ├─ [NEW] assistant_msg = ToolsFormatter.format_assistant_tool_calls(raw_result, provider)
  ├─ [NEW] if assistant_msg: messages.append(dict(assistant_msg))
  │
  └─ for call in tool_calls:
       _process_tool_call(call, ...)
         └─ messages.append(ToolsFormatter.format_tool_result(call, result, provider))
```

`format_assistant_tool_calls` extracts the assistant turn directly from the provider's raw response object (`raw.raw`) to avoid re-serializing arguments and to preserve any extra fields the provider returned (e.g., `refusal`, text content blocks alongside tool calls in Anthropic).

---

## 6. Detailed Design

### 6.1 `ToolsFormatter.format_assistant_tool_calls` — `vidbyte/lib/tools/formatter.py`

**File:** `vidbyte/lib/tools/formatter.py`
**Type:** Modified (new static method added)

#### What it does
Returns the provider-native assistant/model message for a model response that contains tool calls, or `None` when the payload shape is not recognized or not supported.

#### Interface / API
```python
@staticmethod
def format_assistant_tool_calls(raw: object, provider_or_model: str) -> Mapping[str, Any] | None:
    """Return the assistant turn for a tool-call response so it can be prepended to tool results."""
```

#### Logic / Algorithm

1. Extract `raw_payload = getattr(raw, "raw", raw)`. If not a `Mapping`, return `None`.
2. Resolve `provider = ToolsFormatter.provider_from_model(provider_or_model)`.
3. **OpenAI / xai** path (provider not `"anthropic"` or `"gemini"`):
   - If `raw_payload.get("output")` is a list → Responses API shape → return `None` (not supported for multi-turn yet).
   - Otherwise look up `choices = raw_payload.get("choices")`.
   - If `choices` is a list and non-empty, get `message = choices[0].get("message")`.
   - If `message` is a `Mapping` and `"tool_calls"` is in `message`, return `dict(message)`.
   - Otherwise return `None`.
4. **Anthropic** path:
   - `content = raw_payload.get("content")`. If not a list or empty, return `None`.
   - If any item in `content` has `"type": "tool_use"`, return `{"role": "assistant", "content": list(content)}`.
   - Otherwise return `None` (text-only response, no tool calls).
5. **Gemini** path:
   - `candidates = raw_payload.get("candidates")`. If not a list or empty, return `None`.
   - `content = candidates[0].get("content")` if `candidates[0]` is a `Mapping`, else `None`.
   - If `content` is a `Mapping` and any part in `content.get("parts", [])` has `"functionCall"` or `"function_call"`, return `dict(content)`.
   - Otherwise return `None`.

#### Edge Cases & Error Handling
- Raw response that is not a `Mapping` (e.g., a string): return `None`.
- `choices` list exists but `message["tool_calls"]` is absent or empty: return `None` (text response).
- Anthropic content list has text blocks but no `tool_use` blocks: return `None`.
- Responses API (`output` list present): return `None`.

---

### 6.2 `_arun_once` — `vidbyte/agents/runtime.py`

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified (two lines added)

#### What it does
Inserts the assistant's tool-call decision message into `messages` before tool results are appended.

#### Interface / API
No signature change. Two lines inserted at line 437, before `for call in tool_calls:`.

#### Logic / Algorithm

```python
# BEFORE (existing):
for call in tool_calls:
    processed = await self._process_tool_call(...)

# AFTER (new):
assistant_tool_msg = ToolsFormatter.format_assistant_tool_calls(raw_result, provider)
if assistant_tool_msg is not None:
    messages.append(dict(assistant_tool_msg))
for call in tool_calls:
    processed = await self._process_tool_call(...)
```

#### Edge Cases & Error Handling
- `format_assistant_tool_calls` returns `None` (Responses API, text-only response): skip, no append.
- `tool_calls` is non-empty but `format_assistant_tool_calls` returns `None`: tool results are still appended without an assistant turn (same as before; avoids silent data corruption for unsupported shapes).

---

## 7. Data Model Changes

N/A — no schema or persistent data changes. The `messages` list is ephemeral per run.

---

## 8. API Changes

N/A — no HTTP endpoints.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/lib/tools/formatter.py` | Add `format_assistant_tool_calls` static method |
| MODIFY | `vidbyte/agents/runtime.py` | Append assistant turn in `_arun_once` before `for call in tool_calls:` |
| MODIFY | `tests/test_provider_tool_schema_translation.py` | Add unit tests for `format_assistant_tool_calls` |
| MODIFY | `tests/test_agent_tool_loop.py` | Add integration tests verifying messages content on multi-turn calls |

---

## 10. Testing Plan

### Unit Tests

**`tests/test_provider_tool_schema_translation.py` — new class `AssistantToolCallHistoryFormatterTests`:**

- `it('returns openai assistant message when choices has tool_calls')` — [Hidden Failure]: primary fix — confirms the method extracts the right shape
- `it('returns None for openai text-only response with no tool_calls')` — [Edge Case]: must not insert a phantom assistant turn for text responses
- `it('returns anthropic assistant message when content has tool_use block')` — [Hidden Failure]: Anthropic multi-turn
- `it('returns None for anthropic text-only response with no tool_use blocks')` — [Edge Case]: text-only Anthropic response
- `it('returns gemini model message when parts has functionCall')` — [Hidden Failure]: Gemini multi-turn
- `it('returns None for gemini text-only response with no functionCall parts')` — [Edge Case]: text-only Gemini response
- `it('returns None for openai responses-api shape (output list)')` — [Hidden Assumption]: Responses API must not produce broken history
- `it('returns None for non-Mapping raw response')` — [Edge Case]: raw is a string or None
- `it('preserves text content blocks alongside tool_use in anthropic response')` — [Silent Failure]: Anthropic allows text + tool_use in same content; the full content must be preserved, not just the tool_use blocks
- `it('returns correct role field for each provider')` — [Silent Failure]: "assistant" for OpenAI/Anthropic, "model" for Gemini
- `it('handles multiple tool calls in one openai response (one message, multiple tool_calls)')` — [Hidden Failure]: batch tool calls must produce exactly one assistant message

**`tests/test_agent_tool_loop.py` — additions to `AgentToolLoopTests`:**

- `it('includes assistant tool-call message before tool result in messages on second iteration')` — [Hidden Failure]: the core regression check; inspect `runner.calls[1]["kwargs"]["messages"]` to verify ordering
- `it('does not insert duplicate assistant turns when model makes two sequential tool-call responses')` — [Silent Failure]: two-tool-call round trips must each produce exactly one assistant turn
- `it('messages list is empty on first call and populated on second call with correct interleaving')` — [Hidden Assumption]: first call has no history; second call must have [assistant tool-call, tool result] pairs

### Integration Tests
- Simulate a two-round OpenAI chat completions loop: round 1 returns a tool call, round 2 returns isDone. Inspect `messages` passed to the second call to verify `[{"role": "assistant", "tool_calls": [...]}, {"role": "tool", ...}]` ordering.
- Same simulation with Anthropic shape: verify `[{"role": "assistant", "content": [tool_use_block]}, {"role": "user", "content": [tool_result_block]}]`.
- Same simulation with Gemini shape: verify `[{"role": "model", "parts": [functionCall]}, {"role": "function", "parts": [functionResponse]}]`.

### Manual / QA Test Cases
1. Given an OpenAI-compatible agent with a real tool, when the model calls the tool once, then inspect the second API call's `messages` array and verify the assistant message with `tool_calls` precedes the tool result message. — [Hidden Failure]
2. Given an Anthropic agent with a real tool, when the model responds with both a text block and a `tool_use` block, then the second call's `messages` must contain an assistant turn with the full content array (text + tool_use), not just the tool_use block. — [Silent Failure]
3. Given a default (no-tool-call) agent response, when the model returns text with no tool calls, then `messages` must not contain any assistant turn (no phantom insertion). — [Hidden Assumption]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `json` | stdlib | Already imported by `formatter.py` | None |

---

## 12. Rollout & Deployment

- No feature flags. This is a bug fix; the correct behavior is always desired.
- No breaking API changes to `ToolsFormatter`'s public interface — `format_assistant_tool_calls` is a new additive method.
- The behavior change is limited to multi-turn tool-call runs. Single-turn and text-only runs are unaffected.
- Rollback: revert the two-line insertion in `_arun_once`. The new `format_assistant_tool_calls` method is inert if never called.

---

## 13. Open Questions

- [ ] **OpenAI Responses API multi-turn**: `format_tool_result` returns `{"role": "tool", ...}` for Responses API calls instead of `{"type": "function_call_output", ...}`. Fixing Responses API multi-turn requires updating both `format_tool_result` and handling the assistant turn as individual `function_call` items (not a single role message). This should be a follow-up issue.
- [ ] **Anthropic streaming / delta objects**: If the raw response is a streaming delta rather than a complete message object, `raw_payload["content"]` may be absent. Currently the SDK uses non-streaming requests only, so this is not an active concern.

---

## 14. Alternatives Considered

### Alternative 1: Reconstruct assistant turn from ToolCall objects
- What: Build `{"role": "assistant", "tool_calls": [...]}` from the already-parsed `ToolCall` objects instead of extracting from the raw response.
- Why rejected: `ToolCall` objects don't carry the full provider response (e.g., `refusal` field in OpenAI, text content blocks in Anthropic). Reconstructing would silently drop content the model included alongside tool calls, which matters for Anthropic where text + tool_use can coexist in one message. Extracting from `raw` is lossless and avoids re-serializing arguments.

### Alternative 2: Move insertion into `_process_tool_call`
- What: Append the assistant turn inside `_process_tool_call` on the first call per model response.
- Why rejected: `_process_tool_call` is called once per tool call. When the model returns multiple tool calls in one response (Anthropic batch), appending inside it would require deduplication logic to avoid multiple assistant messages. Inserting once before the `for call in tool_calls:` loop is cleaner and semantically correct: one model response → one assistant message.

### Alternative 3: Record raw response in `_invoke_with_middleware` and defer insertion
- What: Store the raw response alongside the message list and insert the assistant turn lazily when the next iteration begins.
- Why rejected: Adds state complexity and defers a mandatory invariant (assistant turn before tool results must hold within the same iteration). Inline insertion at the known site is simpler.
