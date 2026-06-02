# Design Doc: Provider-Native Structured Outputs

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-02
**Last Updated:** 2026-06-02

---

## 1. Overview

This feature extends the typed output schema work from PR #91 so Vidbyte uses provider-native constrained structured outputs when the selected model provider supports them, then keeps the PR #91 runtime validation path as the fallback and final safety check.

The implementation adds a provider mapping layer that converts a declared agent `output_schema` into the correct request shape for OpenAI, Anthropic, Gemini, and OpenAI-compatible providers. It also adds an optional strict-tool-schema path for providers that support constrained tool-call arguments. Local Python tool return values are still validated by the existing PR #91 `ToolSpec.output_schema` logic because model providers cannot constrain the output of SDK-executed local tools.

---

## 2. Goals & Non-Goals

### Goals
- Use provider-native structured final outputs for `BaseAgent.output_schema` when available.
- Keep local output validation from PR #91 as the final contract for every provider response.
- Fall back to PR #91 prompt-hint behavior when provider-native structured outputs are unavailable, disabled, or unsupported for the selected provider mode.
- Add an explicit structured output mode: `auto`, `native`, or `prompt`.
- Pass `response_format` from `AgentRuntime` through `TextModelRunner.arun()` and `TextModelRunner.run()` into provider adapters.
- Serialize Anthropic structured outputs as `output_config: {"format": ...}`.
- Reuse existing OpenAI and Gemini provider `response_format` plumbing where possible.
- Support optional strict provider tool input schemas for model-generated tool-call arguments, without changing local tool output validation.
- Preserve backward compatibility: agents without `output_schema` behave exactly as they do today.

### Non-Goals
- Replacing PR #91 runtime validation. Provider-native guarantees are not treated as sufficient on their own.
- Retrying or repairing invalid final outputs. This is a follow-up; this feature only adds native constrained generation plus validation/fallback.
- Constraining local Python tool outputs through providers. Providers can constrain model outputs and model-generated tool inputs, not SDK tool return values.
- Full JSON Schema normalization for every provider-specific supported subset. The first implementation sends resolved schemas and relies on provider errors plus local validation.
- Adding a new `jsonschema` dependency.
- Changing non-linear/search/actor runtimes. This work targets the linear/direct agent runtime path that calls text providers.

---

## 3. Background & Context

### Repo Audit

The SDK is a Python 3.11 package configured by `pyproject.toml`, with `pydantic>=2,<3` as the only runtime dependency. Tests are standard `unittest`/`pytest`-runnable Python tests under `tests/`, with standalone verification scripts under `scripts/`.

The current provider stack is:
- `BaseAgent` builds an `AgentRuntime` and delegates direct text execution through `_run_direct()`.
- `AgentRuntime._build_iteration_call_options()` assembles `system`, `tools`, and `messages` kwargs for the runner.
- `TextModelRunner.arun()` builds a `TextModelConfig` copy with call-scoped `tools`, `tool_choice`, and `messages`, then calls the selected provider.
- `TextModelConfig.response_format` already exists.
- `OpenAIProvider` already serializes `TextModelConfig.response_format` under `payload["text"]["format"]`.
- `GeminiProvider` already serializes `TextModelConfig.response_format` under `generationConfig.responseMimeType` and `generationConfig.responseSchema`.
- OpenAI-compatible providers already serialize `response_format` into chat-completions payloads.
- `AnthropicProvider` currently passes tools and `tool_choice`, but does not yet serialize structured output `output_config.format`.

PR #91 adds:
- `BaseAgent.output_schema`, `AgentSpec.output_schema`, and `ToolSpec.output_schema`.
- `AgentResult.structured` and `ToolResult.structured`.
- `OutputSchemaValidator.resolve()`, `validate()`, and `schema_prompt_hint()`.
- Agent final-output validation and tool-output validation.

Important branch state:
- `origin/main` and PR #91 are currently divergent.
- This feature assumes PR #91 is rebased onto current `origin/main` and merged first, or that this feature is implemented as a stacked branch on top of a rebased PR #91.
- If implementation starts while PR #91 is still unmerged and unrebased, branch setup is blocked until the base is chosen.

### Provider Docs Checked

OpenAI Responses API documents `text.format` with `type: "json_schema"`, `schema`, `name`, and optional `strict`; strict schema adherence is available for a supported JSON Schema subset. Source: https://developers.openai.com/api/reference/resources/responses/methods/create

Anthropic documents JSON outputs through `output_config.format` with `type: "json_schema"` and a schema, and strict tool use through `strict: true` on tool definitions. Source: https://platform.claude.com/docs/en/build-with-claude/structured-outputs

Gemini documents structured output with JSON Schema; the repo's current REST adapter already maps `TextModelConfig.response_format` to `generationConfig.responseMimeType = "application/json"` and `generationConfig.responseSchema`. Source: https://ai.google.dev/gemini-api/docs/structured-output

---

## 4. Requirements

### Functional Requirements

1. `StructuredOutputMode` must support `AUTO`, `NATIVE`, and `PROMPT`.
2. `BaseAgent.__init__` must accept `structured_output_mode` with default `AUTO`.
3. `BaseAgent.__init__` must accept `strict_provider_tool_schemas: bool = False`.
4. `BaseAgent.fork()` must preserve `structured_output_mode` and `strict_provider_tool_schemas`.
5. `AgentSpec` must accept `structured_output_mode` and `strict_provider_tool_schemas`.
6. `AgentRuntime` must accept and store `structured_output_mode` and `strict_provider_tool_schemas`.
7. When `output_schema` is set and mode is `AUTO`, `AgentRuntime` must attach a native provider response format for OpenAI, Anthropic, Gemini, xAI, OpenRouter, DeepSeek, GLM, and MiniMax when the provider mapping supports them.
8. When mode is `PROMPT`, `AgentRuntime` must not attach provider-native response format and must keep the PR #91 prompt hint.
9. When mode is `NATIVE`, `AgentRuntime` must raise a configuration error before the model call if the provider mapping does not support native structured output.
10. When native response format is attached, `AgentRuntime` must not also append the PR #91 schema prompt hint unless the mapper explicitly says prompt fallback is required.
11. `TextModelRunner.arun()` and `TextModelRunner.run()` must accept optional `response_format` and pass it into the call-scoped `TextModelConfig`.
12. `StreamingTextModelRunner.stream()` must accept optional `response_format` and pass it into the call-scoped `TextModelConfig`.
13. `AnthropicProvider` must serialize `config.response_format` as `payload["output_config"] = {"format": dict(config.response_format)}`.
14. `Tools.provider_schemas()`, `ToolsFormatter.format_tools()`, and provider-specific tool formatters must accept `strict: bool = False`.
15. When `strict_provider_tool_schemas=True`, provider tool schemas must include strict tool input controls only where the provider shape supports them:
    - OpenAI-compatible function tools: include strict function schema fields in the provider-supported location.
    - Anthropic tools: include top-level `strict: True`.
    - Gemini: no-op unless a confirmed supported strict field exists in the adapter contract.
16. Existing tool parsing and tool result formatting must remain unchanged.
17. Local validation from PR #91 must still populate `AgentResult.structured` and `ToolResult.structured`.
18. If provider-native output produces invalid JSON or a schema mismatch, PR #91 validation must still return `structured=None` and `metadata["output_schema_error"]`.
19. No existing public API call without `output_schema` may change payload shape.
20. All implementation methods must use one-line signatures and a short comment immediately below each function/method signature, per the design-doc skill requirements.

### Non-Functional Requirements

- No new runtime dependency.
- No live API calls in tests.
- Tests must verify request payloads through fake transports/runners.
- The provider mapping must be isolated in a class, not spread as ad hoc `if provider` blocks throughout runtime logic.
- The runtime must remain provider-agnostic outside the mapper's public interface.
- Backward compatibility is mandatory for existing agents, tools, runners, and provider adapters.

---

## 5. High-Level Design

The design adds one provider-native planning layer between `AgentRuntime` and provider calls.

```
BaseAgent(output_schema=..., structured_output_mode="auto")
        |
        v
AgentRuntime._build_iteration_call_options()
        |
        v
ProviderStructuredOutputPlanner.plan(provider, schema, mode)
        |
        +--> native response_format for supported providers
        +--> prompt fallback decision for unsupported/disabled paths
        |
        v
TextModelRunner.arun(..., response_format=...)
        |
        v
Provider payload
        |
        v
Provider text result
        |
        v
PR #91 OutputSchemaValidator.validate()
        |
        v
AgentResult(output=str, structured=T | None, metadata=...)
```

Strict provider tool inputs are a separate call option:

```
AgentRuntime._resolve_tool_schemas(provider)
        |
        v
Tools.provider_schemas(provider, strict=self.strict_provider_tool_schemas)
        |
        v
ToolsFormatter provider-specific schema shape
```

This keeps final structured output and tool-call argument strictness related but not conflated. `output_schema` describes the final answer contract; `strict_provider_tool_schemas` controls model-generated tool argument constraints; `ToolSpec.output_schema` still validates local tool return values.

---

## 6. Detailed Design

### 6.1 `StructuredOutputMode`

**File:** `vidbyte/lib/enums/structured_output.py`
**Type:** New file

#### What it does
Defines the public mode for selecting native provider structured outputs versus prompt fallback.

#### Interface / API

```python
class StructuredOutputMode(str, Enum):
    AUTO = "auto"
    NATIVE = "native"
    PROMPT = "prompt"

    @classmethod
    def coerce(cls, value: StructuredOutputMode | str | None) -> StructuredOutputMode:
        # Normalizes user input into a supported structured output mode.
```

#### Edge Cases & Error Handling
- `None` maps to `AUTO`.
- Unknown strings raise `ConfigurationError` with the invalid value.

---

### 6.2 Provider Structured Output Planner

**File:** `vidbyte/providers/structured_output.py`
**Type:** New file

#### What it does
Owns provider-specific response-format construction and prompt-fallback decisions.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class StructuredOutputPlan:
    response_format: Mapping[str, Any] | None = None
    use_prompt_hint: bool = False
    native_supported: bool = False
    provider: str = ""

class ProviderStructuredOutputPlanner:
    def plan(self, *, provider: str, schema: type | Mapping[str, Any] | None, mode: StructuredOutputMode) -> StructuredOutputPlan:
        # Builds native response format or prompt-fallback plan for the provider.
```

#### Provider Shapes

OpenAI Responses:

```python
{
    "type": "json_schema",
    "name": "agent_output",
    "schema": resolved_schema,
    "strict": True,
}
```

OpenAI-compatible chat providers:

```python
{
    "type": "json_schema",
    "json_schema": {
        "name": "agent_output",
        "schema": resolved_schema,
        "strict": True,
    },
}
```

Anthropic:

```python
{
    "type": "json_schema",
    "schema": resolved_schema,
}
```

Gemini:

```python
resolved_schema
```

#### Logic / Algorithm
1. If schema is `None`, return an empty plan.
2. If mode is `PROMPT`, return `use_prompt_hint=True`.
3. Resolve the schema via `OutputSchemaValidator.resolve(schema)`.
4. Map provider family using existing `ToolsFormatter.provider_from_model(provider)`.
5. Build the provider-specific `response_format`.
6. If unsupported:
   - `AUTO` returns `use_prompt_hint=True`.
   - `NATIVE` raises `ConfigurationError`.
7. Return a plan with `native_supported=True` and `use_prompt_hint=False`.

#### Edge Cases & Error Handling
- Invalid schema values propagate as programmer errors from `OutputSchemaValidator.resolve`.
- Unknown provider strings in `AUTO` fall back to prompt hint.
- Unknown provider strings in `NATIVE` raise `ConfigurationError`.

---

### 6.3 `BaseAgent` and `AgentSpec` Wiring

**Files:** `vidbyte/agents/base.py`, `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified

#### What it does
Adds public configuration for structured output mode and strict provider tool input schemas.

#### Interface / API

```python
BaseAgent(
    ...,
    output_schema=MyModel,
    structured_output_mode=StructuredOutputMode.AUTO,
    strict_provider_tool_schemas=False,
)
```

`AgentSpec` receives matching fields so configured agents can declare the same behavior.

#### Logic / Algorithm
1. Coerce `structured_output_mode` with `StructuredOutputMode.coerce`.
2. Store `self.structured_output_mode`.
3. Store `self.strict_provider_tool_schemas`.
4. Forward both into `_runtime()`.
5. Preserve both in `fork()`.

#### Edge Cases & Error Handling
- Invalid mode strings raise `ConfigurationError` during agent construction.
- `fork()` preserves the settings unless a future PR adds explicit override parameters.

---

### 6.4 `AgentRuntime` Native Plan Integration

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does
Builds provider call options from the native structured output plan and only uses prompt fallback when required.

#### Interface / API

```python
AgentRuntime(..., output_schema=..., structured_output_mode=..., strict_provider_tool_schemas=...)
```

#### Logic / Algorithm
1. Constructor stores `output_schema`, `structured_output_mode`, `strict_provider_tool_schemas`, and a `ProviderStructuredOutputPlanner`.
2. `_resolve_tool_schemas(provider)` calls `self.tools.provider_schemas(provider, strict=self.strict_provider_tool_schemas)`.
3. `_build_iteration_call_options()` computes a structured output plan before building the system string.
4. If `plan.response_format` is not `None`, attach `call_options.setdefault("response_format", plan.response_format)`.
5. `_build_system_string(context, use_schema_hint=plan.use_prompt_hint)` appends the PR #91 prompt hint only when requested.
6. `_final_result()` continues using PR #91 local validation regardless of native provider mode.

#### Edge Cases & Error Handling
- User-supplied `response_format` in `options` should not be overwritten by default. If both user `response_format` and `output_schema` are set, native schema planning must prefer user-supplied call option and record fallback/local validation behavior in tests.
- Native mode with unsupported provider raises before the provider call.
- Auto mode with unsupported provider uses prompt hint and no `response_format`.

---

### 6.5 Runner Pass-Through

**Files:** `vidbyte/lib/runners/text.py`, `vidbyte/lib/runners/streaming_text.py`
**Type:** Modified

#### What it does
Allows the runtime to pass a call-scoped response format without mutating the runner's base config.

#### Interface / API

```python
async def arun(..., response_format: Mapping[str, Any] | None = None) -> TextModelResponse:
    # Runs one text model call with optional call-scoped structured output format.

def run(..., response_format: Mapping[str, Any] | None = None) -> TextModelResponse:
    # Synchronously runs one text model call with optional call-scoped structured output format.

def stream(..., response_format: Mapping[str, Any] | None = None) -> Iterator[str]:
    # Streams one text model call with optional call-scoped structured output format.
```

#### Logic / Algorithm
- Include `response_format=response_format or self._config.response_format` in the `replace()` call only when an explicit call-scoped value is present.
- Preserve existing `TextModelConfig.response_format` if callers configured it at runner construction time.

#### Edge Cases & Error Handling
- `None` means no call-scoped override.
- Existing runner-level response formats remain effective.

---

### 6.6 Anthropic Provider Payload

**File:** `vidbyte/providers/anthropic.py`
**Type:** Modified

#### What it does
Serializes `TextModelConfig.response_format` to Anthropic's current structured output API.

#### Interface / API

```python
payload["output_config"] = {"format": dict(config.response_format)}
```

#### Logic / Algorithm
1. Add `_attach_response_format(payload, config)`.
2. Call it from `_create_payload()` after sampling and before tools or metadata.
3. Keep existing `tools`, `tool_choice`, `thinking`, metadata, and `extra_body` behavior.

#### Edge Cases & Error Handling
- If `extra_body` includes `output_config`, it will still override through the existing extra-body merge behavior. A test should document this precedence.
- `response_format=None` leaves the Anthropic payload unchanged.

---

### 6.7 Strict Provider Tool Input Schemas

**Files:** `vidbyte/lib/tools/formatter.py`, `vidbyte/tools/catalog.py`, `vidbyte/providers/base.py`
**Type:** Modified

#### What it does
Allows agent runtime to request provider strictness for model-generated tool inputs without changing local tool execution.

#### Interface / API

```python
Tools.provider_schemas(provider_or_model: str, *, strict: bool = False) -> tuple[dict[str, Any], ...]
ToolsFormatter.format_tools(tools: object, provider_or_model: str, *, strict: bool = False) -> tuple[dict[str, Any], ...]
ToolsFormatter.to_openai_tool(spec: ToolSpec, *, strict: bool = False) -> dict[str, Any]
ToolsFormatter.to_anthropic_tool(spec: ToolSpec, *, strict: bool = False) -> dict[str, Any]
ToolsFormatter.to_gemini_tool(spec: ToolSpec, *, strict: bool = False) -> dict[str, Any]
tool_spec_to_provider_schema(spec: ToolSpec, provider: str, *, strict: bool = False) -> Mapping[str, Any]
```

#### Provider Shapes
- OpenAI/xAI/OpenRouter/compatible: strict information is attached to the function schema shape supported by OpenAI-compatible APIs.
- Anthropic: `strict: True` is added at the top level of the tool definition.
- Gemini: strict is a no-op in V1 unless the repo's adapter adds a documented field later.

#### Edge Cases & Error Handling
- Strict defaults to `False`, preserving all existing payloads.
- Strict mode does not mutate the `ToolSpec.input_schema`.
- Empty tool lists still return an empty tuple.

---

### 6.8 Exports

**Files:** `vidbyte/lib/enums/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does
Exports `StructuredOutputMode` for public use.

#### Edge Cases & Error Handling
- Importing `vidbyte.StructuredOutputMode` must work.
- Existing imports from `vidbyte.lib.enums` must remain unchanged.

---

## 7. Data Model Changes

### New Enum

```python
StructuredOutputMode.AUTO = "auto"
StructuredOutputMode.NATIVE = "native"
StructuredOutputMode.PROMPT = "prompt"
```

### Agent Fields

`BaseAgent` and `AgentSpec` gain:

```python
structured_output_mode: StructuredOutputMode | str = StructuredOutputMode.AUTO
strict_provider_tool_schemas: bool = False
```

### Result Models

No new result fields beyond PR #91. `AgentResult.structured` and `ToolResult.structured` remain the typed output surfaces.

---

## 8. API Changes

### Public Python API

New optional agent arguments:

```python
agent = BaseAgent(
    name="extractor",
    system_prompt="Extract structured data.",
    runner=runner,
    output_schema=ContactInfo,
    structured_output_mode="auto",
    strict_provider_tool_schemas=True,
)
```

New optional runner call argument:

```python
await runner.arun("Extract data", response_format={...})
runner.run("Extract data", response_format={...})
```

New public enum:

```python
from vidbyte import StructuredOutputMode
```

### Compatibility

All new fields have defaults. Existing code without `output_schema`, without `response_format`, and without strict tool schemas keeps identical payloads.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/provider-native-structured-outputs.md` | Design source of truth |
| CREATE | `vidbyte/lib/enums/structured_output.py` | Public structured output mode enum |
| CREATE | `vidbyte/providers/structured_output.py` | Provider-native response format planner |
| CREATE | `scripts/test-provider-native-structured-outputs.py` | Required verification script |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Export `StructuredOutputMode` |
| MODIFY | `vidbyte/__init__.py` | Top-level public export |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add `AgentSpec` structured output mode fields |
| MODIFY | `vidbyte/agents/base.py` | Accept, store, fork, and forward new agent settings |
| MODIFY | `vidbyte/agents/runtime.py` | Attach native response format, prompt fallback, strict tool schemas |
| MODIFY | `vidbyte/lib/runners/text.py` | Pass call-scoped `response_format` into `TextModelConfig` |
| MODIFY | `vidbyte/lib/runners/streaming_text.py` | Pass call-scoped `response_format` into streaming config |
| MODIFY | `vidbyte/providers/anthropic.py` | Serialize `output_config.format` |
| MODIFY | `vidbyte/lib/tools/formatter.py` | Add optional strict provider tool schema formatting |
| MODIFY | `vidbyte/tools/catalog.py` | Thread strict flag to `ToolsFormatter` |
| MODIFY | `vidbyte/providers/base.py` | Thread strict flag through provider schema helper |
| MODIFY | `tests/test_agent_runtime.py` | Runtime native/fallback/strict behavior tests |
| MODIFY | `tests/test_text_model_runner.py` | Runner response format pass-through tests |
| MODIFY | `tests/test_provider_tool_schema_translation.py` | Strict provider tool schema tests |
| CREATE | `tests/test_provider_native_structured_outputs.py` | Planner and Anthropic payload tests |

Summary: 5 files to create, 14 files to modify, 0 files to delete.

---

## 10. Testing Plan

### Unit Tests

**`StructuredOutputMode`**
- [Edge Case] `coerce(None)` returns `AUTO`.
- [Edge Case] `coerce("auto")`, `coerce("native")`, and `coerce("prompt")` return enum members.
- [Hidden Failure] `coerce("bad")` raises `ConfigurationError` instead of silently falling back.
- [Silent Failure] `str(StructuredOutputMode.AUTO)` or `.value` remains `"auto"` for stable metadata/logging.
- [Hidden Assumption] Passing an existing enum member returns the same member.

**`ProviderStructuredOutputPlanner`**
- [Edge Case] `schema=None` returns no response format and no prompt hint.
- [Edge Case] `PROMPT` mode returns no response format and `use_prompt_hint=True`.
- [Hidden Failure] `NATIVE` mode with unsupported provider raises `ConfigurationError`.
- [Silent Failure] OpenAI plan uses `{"type": "json_schema", "name": ..., "schema": ..., "strict": True}` and does not use chat-completions wrapper.
- [Silent Failure] OpenAI-compatible plan uses `{"type": "json_schema", "json_schema": {...}}`.
- [Silent Failure] Anthropic plan uses `{"type": "json_schema", "schema": ...}`.
- [Silent Failure] Gemini plan returns the raw resolved schema, not an OpenAI wrapper.
- [Hidden Assumption] Pydantic model schemas resolve through `OutputSchemaValidator.resolve()`.
- [Hidden Assumption] Raw dict schemas are copied, not mutated.

**`TextModelRunner`**
- [Edge Case] `response_format=None` preserves existing behavior.
- [Hidden Failure] Call-scoped `response_format` is included in the replaced `TextModelConfig`.
- [Silent Failure] Existing runner-level `TextModelConfig.response_format` is not erased when call-scoped value is omitted.
- [Hidden Assumption] `run()` forwards `response_format` to `arun()` in the sync wrapper path.

**`StreamingTextModelRunner`**
- [Edge Case] Streaming with no `response_format` keeps existing payload shape.
- [Hidden Failure] Streaming with `response_format` passes it to provider config.
- [Silent Failure] Existing streaming `tools`, `tool_choice`, and `messages` still pass through.
- [Hidden Assumption] Unsupported streaming providers still fail at init, not when response format is set.

**`AnthropicProvider`**
- [Edge Case] `config.response_format=None` omits `output_config`.
- [Hidden Failure] `config.response_format` adds `payload["output_config"]["format"]`.
- [Silent Failure] Existing `tools`, `tool_choice`, `thinking`, and metadata are preserved alongside `output_config`.
- [Hidden Assumption] `extra_body` can override `output_config`, matching existing extra-body precedence.

**Strict Provider Tool Schemas**
- [Edge Case] Empty `Tools().provider_schemas(..., strict=True)` returns `()`.
- [Hidden Failure] Strict flag does not mutate `ToolSpec.input_schema`.
- [Silent Failure] Anthropic strict schemas include top-level `strict: True`.
- [Silent Failure] OpenAI-compatible strict schemas include the provider-supported strict function schema fields.
- [Silent Failure] Gemini strict mode remains shape-compatible and does not add undocumented fields.
- [Hidden Assumption] Default `strict=False` produces byte-for-byte equivalent schemas for existing tests.

### Integration Tests

**AgentRuntime native structured output**
- [Edge Case] Agent without `output_schema` does not include `response_format` and does not append schema prompt hint.
- [Hidden Failure] OpenAI provider with `output_schema` in `AUTO` passes `response_format` to the fake runner.
- [Hidden Failure] Anthropic provider with `output_schema` in `AUTO` passes `response_format` to the fake runner.
- [Hidden Failure] Gemini provider with `output_schema` in `AUTO` passes raw schema response format to the fake runner.
- [Silent Failure] Native-supported providers do not also append the PR #91 schema prompt hint.
- [Silent Failure] `PROMPT` mode appends the schema prompt hint and does not pass `response_format`.
- [Hidden Assumption] `NATIVE` mode with unsupported provider raises before `invoke_runner` is called.
- [Hidden Assumption] User-supplied `response_format` in run options is not overwritten by auto-generated schema format.

**AgentRuntime strict provider tool inputs**
- [Edge Case] No user tools with `strict_provider_tool_schemas=True` still includes only internal tools as currently designed.
- [Hidden Failure] Strict flag reaches `Tools.provider_schemas()` from runtime.
- [Silent Failure] Tool parsing after a strict schema request still works for OpenAI, Anthropic, and Gemini fake payloads.
- [Hidden Assumption] Strict tool inputs do not affect local `ToolSpec.output_schema` validation.

**PR #91 validation remains active**
- [Hidden Failure] Native structured output that returns invalid JSON still results in `AgentResult.structured is None` and `metadata["output_schema_error"]`.
- [Silent Failure] Native structured output that returns valid JSON matching schema populates `AgentResult.structured`.
- [Hidden Assumption] Prompt fallback path still validates with the same `OutputSchemaValidator`.

### Manual / QA Test Cases

1. [Edge Case] Create an OpenAI `BaseAgent` with no `output_schema`; inspect fake transport payload and verify no `text.format`.
2. [Hidden Failure] Create an OpenAI `BaseAgent` with `output_schema`; inspect payload and verify `text.format.type == "json_schema"`.
3. [Hidden Failure] Create an Anthropic `TextModelRunner` call with response format; inspect payload and verify `output_config.format`.
4. [Silent Failure] Create a Gemini `TextModelRunner` call with response format; inspect payload and verify `generationConfig.responseMimeType == "application/json"` and `responseSchema` equals the schema.
5. [Hidden Assumption] Enable `strict_provider_tool_schemas`; verify Anthropic tool declarations include `strict: True` and local tool result validation behavior is unchanged.

### Verification Script

Create `scripts/test-provider-native-structured-outputs.py` and execute every test case above without live credentials. The script must print `PASS` or `FAIL` per case, print a final `X/Y tests passed` summary, and exit non-zero on failure.

---

## 11. Dependencies & External Services

No new Python dependencies.

External provider APIs affected by payload shape:
- OpenAI Responses API structured outputs.
- Anthropic Messages API structured outputs.
- Gemini generateContent structured outputs.
- OpenAI-compatible chat providers that accept `response_format`.

All tests use fake transports/runners and do not call external APIs.

---

## 12. Rollout & Deployment

1. Merge or rebase PR #91 onto current `origin/main`.
2. Implement this feature in an isolated worktree.
3. Run the standalone verification script.
4. Run focused tests:
   - `python -m pytest tests/test_provider_native_structured_outputs.py`
   - `python -m pytest tests/test_agent_runtime.py`
   - `python -m pytest tests/test_text_model_runner.py`
   - `python -m pytest tests/test_provider_tool_schema_translation.py`
5. Run the broader test suite if time permits: `python -m pytest tests/`.
6. Open a draft PR.

Rollout is backward-compatible because all new behavior is opt-in through `output_schema`, `structured_output_mode`, or `strict_provider_tool_schemas`.

---

## 13. Open Questions

1. Should this implementation wait for PR #91 to merge into `main`, or should it be stacked on a rebased PR #91 branch?
   - Recommendation: rebase PR #91 onto `origin/main`, then stack this branch on top of it if PR #91 is still open.
2. Should `strict_provider_tool_schemas` default to `False` as designed, or should `AUTO` mode imply strict tool inputs too?
   - Recommendation: keep default `False` for compatibility and because provider strict schema subsets can reject existing tools.
3. Should `NATIVE` mode fail when a user-supplied call-level `response_format` overrides the generated one?
   - Recommendation: fail fast to avoid silently violating the declared `output_schema` contract.
4. Should we add schema normalization for provider-supported subsets in this PR?
   - Recommendation: not in V1. Add a follow-up after collecting real provider rejection cases.

---

## 14. Alternatives Considered

### Alternative 1: Only Prompt Injection Plus Validation

This is PR #91's current behavior. It is simple and portable, but it does not use provider-native constrained decoding and can still produce invalid final JSON.

Rejected because the requested behavior explicitly wants provider-native structured outputs first.

### Alternative 2: Provider-Native Only, No Local Validation

This would reduce duplicate work, but provider docs still document invalid-output cases such as refusals and token limits. Provider schema subsets also differ.

Rejected because local validation is the stable SDK boundary.

### Alternative 3: Put Provider Branches Directly In `AgentRuntime`

This would be fast to implement, but it would couple runtime orchestration to provider payload details and make future providers harder to add.

Rejected in favor of `ProviderStructuredOutputPlanner`.

### Alternative 4: Enable Strict Provider Tool Schemas By Default

This would maximize determinism but risks breaking existing tools whose schemas are valid enough for normal tool use but not accepted by strict constrained decoding subsets.

Rejected for backward compatibility. Strict tool schemas remain opt-in.

---

## Appendix: Implementation Context To Preserve

- Intent: provider-native structured final agent outputs first, PR #91 prompt hint and validation fallback second.
- Scope: linear/direct text agent runtime, text runners, provider payload mappers, optional strict model tool-call input schemas.
- Non-goals: local tool output constrained by providers, retry/repair loops, new JSON Schema dependency.
- Key decisions: isolate provider mapping in a class; default to `AUTO`; keep strict tool inputs opt-in.
- Base dependency: PR #91 typed output schema must be present before implementation.
- Acceptance criteria: native response format appears for supported providers, prompt fallback appears only when needed, local validation still populates `.structured`, and default behavior remains unchanged.
