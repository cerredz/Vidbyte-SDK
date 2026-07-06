# Design Doc: Provider-Aware Tool-Error Rendering

**Status:** Implemented
**Author:** Claude
**Created:** 2026-07-05
**Last Updated:** 2026-07-05

> **Doc 2 of 3** in the tool-error initiative.
> 1. `tool-error-taxonomy-and-authoring` — the *author* layer (structured `ToolError` / `ToolErrorKind` / `retryable` on `ToolResult`). **Prerequisite.**
> 2. **`provider-aware-tool-error-rendering`** (this doc) — the *render* layer. Turns a structured error `ToolResult` into a model-visible message shaped correctly for each provider's tool-result protocol.
> 3. `tool-error-policy-and-retry` — the *decide* layer (settings + middleware). Consumes this doc's rendering.
>
> **This is the doc that owns the user's explicit requirement: "each provider takes in tools in a specific way."** Depends on Doc 1's structured error being present on `ToolResult`. Tool-error rendering is intentionally full-detail by default and does not expose a verbosity enum or redaction tier.

---

## 1. Overview

When a tool fails, the agent loop already appends the result to the conversation (`runtime.py:1339-1343`) and keeps going — but the message it appends carries only `ToolResult.output` and is shaped identically regardless of provider, so the model learns almost nothing about *what kind* of failure occurred and, critically, the providers' own error affordances go unused. Anthropic's `tool_result` block supports an `is_error: true` flag (currently never set); Gemini's `functionResponse` carries a structured `response` object with a `status` we under-populate; OpenAI chat-completions `role: "tool"` messages and the OpenAI Responses API `function_call_output` items have no dedicated error flag, so the error signal must be encoded into the content itself in a legible way. This doc makes `ToolsFormatter.format_tool_result` — the single chokepoint every provider funnels through — render a structured, provider-native error envelope from the `ToolErrorKind` / `hint` / `retryable` fields established in Doc 1.

---

## 2. Original User Prompts

**Prompt 1:** question for the vidbyte-sdk/ repo, in regards to our tools (vidbyte/tools). right now what is the lifecycle behind tooling errors during the agent runtime. For example, how do we handle schema/arguements errors, execution errors, etc, and what are some other types of tools errors that could potentially occur?

**Prompt 2:** well before we get to exact implementation I want to express my intent. I basically first want each error tool to have its own tool errors (argeument errors, execution error, etc). I seems like we have these already, and if there are any more error classes we could define for our tools please briefly describe these (also I think it is a very good idea for each tool to potentially come with like a custom string message just incase there is some very nuonced detail about the error, ex: like a terminal command tool would come with like a 'make sure you are running the terminal commands on the right operations system' or something like that, and we could add these first class error messages to the tools themselves). Then, with these tool error messages I want make it so that these error messages actually get propagated to the agent and get filled within the context window so that if we have a tool error the run doesnt just stop and the agent can actually see information about tool error. How can we add this and what is the cleanest entry point. The idea that I had was we add like some "tool policy" settings to the vidbyte/agent/settings (agent loop settings), and then with these settings we can derive the tool error/execution logic in the agent class (tool settings like retry_number, include full error message, etc, I feel like you could do a better job of deriving exact settings for this). What do you think about all of this?

**Prompt 3:** great, can you decompose all of this into like 2-3 design docs and one thing that I want you to remember is to take into considers that each providers takes in tools in a specific way, so just make sure you take this into consideration in your design docs

---

## 3. Structured Conversation Notes

### Key Decisions

- **`ToolsFormatter.format_tool_result` is THE entry point.** It is the single function through which every provider's tool-result message is built (`formatter.py:172-200`). The runtime calls it exactly once per non-internal tool result at `runtime.py:1343`. All error-rendering logic lands here; the runtime loop is not touched by this doc.
- **Each provider gets a purpose-built error envelope respecting its native protocol** (this is the user's headline requirement). The three shapes and their error affordances:
  - **Anthropic** — result is `{"role": "user", "content": [{"type": "tool_result", "tool_use_id": ..., "content": ...}]}`. Anthropic's API supports **`"is_error": true`** on the `tool_result` block. We currently do NOT set it. → On error, set `is_error: true` and put the structured envelope in `content`.
  - **Gemini** — result is `{"role": "function", "parts": [{"functionResponse": {"name": ..., "response": {"output": ..., "status": ...}}}]}`. It already threads `status`. → On error, populate `response` with `{"error": <kind>, "message": ..., "hint": ..., "retryable": ...}` and set `status` to the kind/error, since Gemini expects a structured `response` object, not a bare string.
  - **OpenAI (chat completions)** — result is `{"role": "tool", "tool_call_id": ..., "name": ..., "content": ...}`. **No dedicated error field exists.** → Encode the error legibly *inside* `content` (see envelope format below).
  - **OpenAI Responses API** — tool output is a `function_call_output` item, not a `role: tool` message. The parser already distinguishes Responses vs chat completions (`formatter.py:132`, `_parse_openai_tool_calls` handles `output` list with `type in {function_call, tool_call}` and marks `metadata={"provider_shape": "openai_responses"}` at `:268`). **Verify whether `format_tool_result` needs a Responses-specific branch** — currently it returns a `role: tool` dict for all non-Anthropic/Gemini providers. If the Responses runner expects `function_call_output`, this is a latent gap the error work should close or at least document.
  - **xAI / Grok, OpenRouter, `compatible`** — OpenAI-compatible; `provider_from_model` (`formatter.py:26`) routes `xai`/`grok` and the default to the OpenAI shape. They inherit the OpenAI chat-completions envelope.
- **A single canonical text envelope, formatted once, then placed per provider.** Define one helper that renders the structured error into a compact human+machine legible string (used verbatim in OpenAI/Anthropic `content` and mirrored into Gemini's structured `response`). Proposed envelope:
  ```
  [tool_error kind=invalid_arguments retryable=false]
  <message>
  Hint: <hint>            # when a hint is present
  ```
  This gives the model a stable, parseable first line plus prose, and mirrors the repo's existing `<tool>...</tool>` compact-rendering aesthetic (`ToolSpec.to_prompt_str`, `tools.py:95`).
- **Full detail is the only rendering mode.** Tool errors always include the structured header, model-visible message, hint when present, and diagnostic detail when present. The settings layer controls retry/abort decisions, not the amount of error detail shown to the model.

### Rejected Alternatives

- **One identical error string for all providers** (status quo). Rejected — it's exactly what wastes each provider's native error channel and is the thing the user called out.
- **Rendering the error in the runtime loop before calling the formatter.** Rejected — provider shape knowledge belongs in `ToolsFormatter`, which already owns every provider-specific tool concern (schema conversion, tool-call parsing, assistant-turn extraction). Splitting provider logic across runtime and formatter would be a regression.
- **Overloading `ToolStatus` with error subtypes.** Rejected (also rejected in Doc 1) — kind lives in metadata; the formatter reads it.

### Constraints & Assumptions

- **`format_tool_result` is a pure `@staticmethod`** taking `(call, result, provider_or_model)` and returning a `Mapping`. It keeps a simple signature because rendering full tool-error detail is unconditional rather than policy-selected.
- **Provider adapters forward `messages` verbatim.** Confirmed by audit: the Anthropic adapter leaves tool blocks in raw content and passes messages through (`providers/anthropic.py:117-123`); the formatter's output dicts are provider-native and go straight to the API. So getting the shape right in `format_tool_result` is sufficient — no per-adapter change needed (except possibly the Responses-API branch, see Open Questions).
- Success-path rendering MUST be unchanged; only `result.status is ERROR` triggers the envelope.
- Must not break `_apply_primitive_binding` (`runtime.py:1346`) which rewrites *successful* results into acknowledgments before formatting — errors never go through primitive binding (`result.status.value != "success"` guard at `:1348`), so ordering is fine.

### Clarifications & Answers

- **Q: Where does the tool result actually enter the model's context?** A: `runtime.py:1343` — `messages.append(dict(ToolsFormatter.format_tool_result(call, visible_result, provider)))`. `visible_result` may be a middleware-transformed result (`after_decision.transform.model_visible_tool_result`, `:1341-1342`) — Doc 3 uses that seam, but this doc renders whatever `ToolResult` it's given.
- **Q: Does the model currently even know an error occurred?** A: Only by reading prose in `output`. No structured signal, no `is_error`. That's the gap this doc closes.

### Terminology / Glossary

- **Error envelope** — the standardized rendering of a structured error into provider-appropriate form (text string and/or structured fields).
- **Provider error affordance** — a provider's native mechanism for marking a tool result as an error: Anthropic `is_error`, Gemini `response.status`/structured object, OpenAI = none (content-encoded).
- **`provider_from_model`** — `formatter.py:26`, maps a provider or model string to one of `anthropic`/`gemini`/`xai`/`openai`.

### Implementation Hints for the Downstream Model

- **Primary file:** `vidbyte/lib/tools/formatter.py`. The method to change is `format_tool_result` at **`formatter.py:172-200`**. Branches: anthropic (`:181`), gemini (`:183`), default/openai (`:195`). Add error handling inside each branch keyed on `result.status`.
- **The canonical envelope helper** should be a new private `@staticmethod _render_error_envelope(result, options) -> str` on `ToolsFormatter`, reading `result.metadata` for the Doc 1 keys (`error` = kind, `hint`, `retryable`). Reuse it in all branches.
- **Anthropic block** — set `is_error: True` alongside `content`:
  ```python
  {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call_id,
      "content": envelope_text, "is_error": True}]}
  ```
- **Gemini** — put structure in `response`, not a bare string:
  ```python
  {"role": "function", "parts": [{"functionResponse": {"name": call.tool_name,
      "response": {"error": kind, "message": msg, "hint": hint, "retryable": retryable, "status": "error"}}}]}
  ```
- **OpenAI / xAI / compatible** — `content` = envelope text; the `role: tool` shape is unchanged otherwise.
- **OpenAI Responses API** — check the runner path. `_assistant_turn_openai` returns `None` for Responses payloads (`formatter.py:132-133`) and `_parse_openai_tool_calls` tags `provider_shape: openai_responses` (`:268`). `format_tool_result` has no Responses branch today. Determine (read the OpenAI runner and `providers/openai.py`) whether tool outputs on the Responses API must be `function_call_output` items; if so add a branch. At minimum, document the finding. See `docs/design/openai-compatible-chat-trace-inputs.md` and `docs/design/assistant-tool-call-history.md` for prior provider-shape work.
- **Do not change `to_openai_tool` / `to_anthropic_tool` / `to_gemini_tool`** (the *inbound* tool *schema* formatters, `:64-101`) — those convert `ToolSpec → provider tool declaration` and are about tool *definitions*, not results. This doc is exclusively about the *result* direction.
- **Testing:** there are almost certainly existing formatter tests. Add per-provider error-shape assertions: Anthropic sets `is_error`, Gemini `response.status == "error"`, OpenAI content contains the `[tool_error ...]` line. Grep tests for `format_tool_result`.
- **Match house style:** `@staticmethod`, `from __future__ import annotations`, Context Protocol Header already present at top of `formatter.py` — extend the "Architecture" section of that header to mention error rendering.

### Open Questions

- **OpenAI Responses API tool-output shape** — does the current Responses runner already work with the `role: tool` dict, or is there a pre-existing mismatch this doc should fix vs. merely document? Needs a read of the OpenAI runner. (Flagged, not assumed.)
- **Should `retryable` be surfaced to the model at all?** Arguments both ways: it helps the model decide whether to re-try vs. change approach, but if Doc 3 does *silent* retry the model shouldn't be told "retryable" for something it won't get to retry. Recommendation: include `retryable` in the envelope only for errors the model is expected to act on (terminal or reflect-to-model kinds), and omit it for kinds Doc 3 retries silently. This couples slightly to Doc 3 — keep the envelope flexible.
- **Truncation interaction:** `ToolResultCompactionMiddleware.truncate` (`runtime.py:86`, from context-window algorithms) may truncate tool result output. Ensure the `[tool_error ...]` first line and hint survive truncation (put them first; consider making the compaction aware of error results). Coordinate with Doc 3.

---

## 4. Goals & Non-Goals

### Goals

- Render tool-error `ToolResult`s into provider-native error envelopes in `format_tool_result`, one branch per provider family.
- Set Anthropic `is_error: true`, populate Gemini structured `response`/`status`, and content-encode for OpenAI/xAI.
- Provide a single canonical text envelope helper reused across providers.
- Render full message, hint, and diagnostic detail whenever those fields are present; no verbosity or redaction options are exposed.
- Resolve or explicitly document the OpenAI Responses API tool-output shape.

### Non-Goals

- Defining the `ToolErrorKind`/`ToolError` contract (Doc 1).
- Defining the settings object or wiring settings → formatter (Doc 3 owns `AgentLoopSettings.tool_error_policy` and passing it down).
- Retry, circuit-breaking, or loop control (Doc 3).
- Changing inbound tool *schema* formatting (`to_*_tool`).
- Changing provider adapters (unless the Responses-API investigation forces a minimal change).

---

## 5. Background & Context

The user's explicit instruction for this decomposition was to "take into consideration that each provider takes in tools in a specific way." The audit confirms the SDK already centralizes all provider-shape knowledge in `ToolsFormatter`: schema conversion, tool-call parsing, assistant-turn extraction, and result formatting each branch on `provider_from_model`. But the *result* path (`format_tool_result`) is the least provider-aware of them — it collapses to two shapes (Anthropic/Gemini special-cased, everything else `role: tool`) and ignores every provider's error signaling. With Doc 1 giving results a structured `kind`/`hint`/`retryable`, this doc spends that structure where it matters most: the exact wire shape each model provider expects for a failed tool call, so the model reliably perceives the failure and its remediation.

---

## 6. Requirements

1. When `result.status is ERROR`, `format_tool_result` MUST produce a provider-native error envelope; when `SUCCESS`, output MUST be byte-for-byte unchanged from today.
2. Anthropic error results MUST set `"is_error": true` on the `tool_result` block.
3. Gemini error results MUST populate `functionResponse.response` with a structured object containing at least `error` (kind), `message`, and (when present/allowed) `hint`, and set an error `status`.
4. OpenAI / xAI / compatible error results MUST encode the structured error legibly within `content`, leading with a stable machine-parseable first line.
5. A single canonical envelope helper MUST format the `kind`/`message`/`hint`/`retryable` from `ToolResult.metadata` (the Doc 1 keys), used consistently across providers.
6. Rendering MUST always include full model-visible detail: the error header, message, hint when present, retryability when present, and diagnostic detail when present.
7. The OpenAI Responses API tool-output path MUST be verified; if it requires `function_call_output` shaping, a branch MUST be added; otherwise the finding MUST be documented in the implementation.
8. No change to inbound tool-schema formatters or to success-path primitive binding.

---

## 7. Non-Functional Requirements

- **Correctness/compat:** wrong shape = provider API error or model confusion. Per-provider tests are mandatory. The default (no options) path must be safe for every provider.
- **Security:** the formatter does not redact tool-error details. Tool authors and execution layers must avoid placing secrets in `ToolResult.output` or error metadata because those fields are intentionally model-visible on failure.
- **Observability:** none new; the tracer already records the error at the pipeline (Doc 1). Optionally include the rendered envelope in trace output for debugging.
- **Performance:** error path only; negligible.

---

## 8. High-Level Design

Concentrate all changes in `ToolsFormatter.format_tool_result`. Add a private `_render_error_envelope(result)` that reads the Doc 1 metadata keys and produces the canonical full-detail text. Then, inside each provider branch, when the result is an error, emit the provider's native error shape: Anthropic adds `is_error: true` and uses the envelope as `content`; Gemini writes a structured `response` object plus an error `status`; the OpenAI-family default uses the envelope as `content`. Investigate the OpenAI Responses API tool-output shape and add a `function_call_output` branch if required, or document why the existing `role: tool` shape suffices.

Data flow: Doc 1 produces an error `ToolResult` with structured metadata → the runtime hands it (possibly after a Doc 3 middleware transform) to `format_tool_result` at `runtime.py:1343` → the formatter selects the provider branch via `provider_from_model` → `_render_error_envelope` builds the shared text → the branch wraps it in the provider-native error structure → the provider adapter forwards the message verbatim to the model API. The model now receives a first-class error signal in the form its provider understands.

```
error ToolResult (kind, message, hint, retryable)   [from Doc 1]
        |
        v
ToolsFormatter.format_tool_result(call, result, provider)   (formatter.py:172)
        |
        |-- _render_error_envelope(result) -> "[tool_error kind=... retryable=...]\n<msg>\nHint: ..."
        |
        +-- provider == anthropic -> tool_result block + "is_error": true
        +-- provider == gemini    -> functionResponse.response{error,message,hint,retryable,status:"error"}
        +-- provider == openai/xai/compatible -> role:tool, content = envelope
        +-- provider == openai_responses (if needed) -> function_call_output item   [INVESTIGATE]
        |
        v
provider adapter forwards message verbatim -> model sees native error
```

---
