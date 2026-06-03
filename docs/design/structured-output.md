# Design Doc: Structured Output

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-02
**Last Updated:** 2026-06-02

---

## 1. Overview

This feature adds a single `output_schema` parameter to both `BaseAgent` and tool definitions (via `ToolSpec` / `FunctionTool`). When set, the SDK automatically enforces that shape at the boundary closest to the model: for providers that support native structured output (OpenAI, Gemini, OpenAI-compatible), the schema is attached to the API call as the provider-specific `response_format` parameter. For tools — where output is produced by Python code, not the model — the SDK validates the tool's return value after execution; if it does not match the schema, a `ToolResult.error` is returned into the context window so the agent can react.

---

## 2. Goals & Non-Goals

### Goals
- Add one param, `output_schema: type | Mapping[str, Any] | None`, to `BaseAgent.__init__` and to `ToolSpec` / `FunctionTool`
- Resolve Pydantic `BaseModel` subclasses into JSON schema dicts automatically
- For agents on supported providers (OpenAI, Gemini, OpenAI-compatible): attach a provider-native `response_format` to the model API call
- For agents on unsupported providers (Anthropic): do nothing — no prompt injection, no error
- For tools with `output_schema` set: validate tool output after execution; on mismatch return a `ToolResult.error` with a clear "output shape mismatch" message into the context window
- Expose `AgentResult.structured` (the parsed output object) when native enforcement succeeded and parsing was possible
- Thread `output_schema` through `fork()` so forked agents preserve the setting
- Export `OutputSchemaFormatter` from the top-level `vidbyte` namespace

### Non-Goals
- Prompt-injection schema hints as a fallback (no mode enum, no `PROMPT` / `AUTO` / `NATIVE` modes)
- `strict_provider_tool_schemas` or any tightening of tool *input* schemas
- Streaming runner support in this PR (streaming agents don't use the tool loop)
- Agent-level schema validation error recovery (the model produced bad JSON; agent just receives raw text)
- Anthropic native structured output (their API does not expose a JSON-schema response format on the standard path)

---

## 3. Background & Context

PR #96 implemented structured outputs but added three separate parameters (`output_schema`, `structured_output_mode`, `strict_provider_tool_schemas`), a new `StructuredOutputMode` enum with three values, and a prompt-injection fallback path. The result is more surface area than the actual user need: the user wants one knob that says "constrain the shape" and expects the SDK to use the native provider capability when available, with no silent-fallback magic. This doc re-implements the feature with that minimal scope.

The codebase already has the infrastructure:
- `TextModelConfig.response_format` field exists and each provider adapter already reads it
- OpenAI, Gemini, and `OpenAICompatibleProvider` all have `_attach_response_format` / `_attach_generation_config` that consume the field
- `ToolsFormatter.provider_from_model()` already normalizes provider strings to a family

What is missing: the wiring from `output_schema` → `response_format` on the runtime side, and the post-execution validation on the tool side.

---

## 4. Requirements

### Functional Requirements

1. `BaseAgent` accepts `output_schema: type | Mapping[str, Any] | None = None` with default `None`; existing agents with no schema behave identically.
2. `ToolSpec` accepts `output_schema: type | Mapping[str, Any] | None = None` with default `None`; existing tool specs are unaffected.
3. `FunctionTool` accepts `output_schema` and threads it into its `ToolSpec`.
4. When `output_schema` is a Pydantic `BaseModel` subclass, the SDK resolves it to a JSON schema dict via `model_json_schema()`; when it is already a dict, a copy is used.
5. At each iteration of the agent loop, if `output_schema` is set and `OutputSchemaFormatter.build_response_format(provider, schema)` returns a non-None value, that value is placed into `call_options["response_format"]` before the runner is invoked.
6. `TextModelRunner.arun()` accepts an optional `response_format` kwarg and passes it via `replace(self._config, response_format=...)` so the provider adapter receives it.
7. Provider mappings for `response_format`:
   - **openai** family: `{"type": "json_schema", "name": "agent_output", "schema": <schema>, "strict": True}` (provider wraps under `text.format`)
   - **gemini** family: the raw schema dict (provider sets `responseMimeType` and `responseSchema` itself)
   - **openai-compatible** family (xai, deepseek, openrouter, glm, minimax): `{"type": "json_schema", "json_schema": {"name": "agent_output", "schema": <schema>, "strict": True}}`
   - **anthropic** family: `None` (not supported; no `response_format` is set)
8. After a tool executes successfully and its `ToolSpec.output_schema` is not None, the runtime validates `result.output` (a string) by parsing it as JSON and checking it against the schema. On mismatch, the runtime returns `ToolResult.error(tool_name, "tool call error: output shape mismatch: <reason>", metadata={"error": "output_schema_violation"})` in place of the original result.
9. `AgentResult` gains an optional `structured: Any = None` field. After the final IS_DONE response, if `output_schema` is set, the runtime attempts to parse `output` as JSON against the schema and populates `structured`; on failure it remains `None` (no error is raised at the agent level).
10. `fork()` preserves `output_schema`.

### Non-Functional Requirements
- Zero performance impact when `output_schema` is `None` (the fast path checks `is None` before any schema work)
- `OutputSchemaFormatter.resolve_schema()` calls `model_json_schema()` once and caches nothing — callers own caching if they need it
- No new required dependencies; Pydantic is already a declared dependency

---

## 5. High-Level Design

A new `OutputSchemaFormatter` class centralizes three responsibilities: resolving a schema (Pydantic type or raw dict) to a plain dict, building the provider-native `response_format` payload, and validating a string output against a schema. This keeps all provider-specific format knowledge in one place rather than scattered across `AgentRuntime` and the provider adapters.

On the agent side, `AgentRuntime` stores `output_schema` and calls `OutputSchemaFormatter.build_response_format(provider, schema)` once per iteration inside `_build_iteration_call_options`. The resulting dict is placed in `call_options["response_format"]`, which already flows through `BaseAgent._call_with_supported_kwargs` to `TextModelRunner.arun()` — after we add `response_format` to that signature. The runner then passes it to `replace(self._config, response_format=...)` so the existing provider adapters handle it without any changes.

On the tool side, `AgentRuntime.execute_tool_call` already has a centralized post-execution path. We add a five-line check after `_execute_tool`: if `spec.output_schema` is set and the result succeeded, parse `result.output` with `OutputSchemaFormatter.validate()`; on error, replace the result with a `ToolResult.error`.

```
[BaseAgent(output_schema=MyModel)]
        |
        v
[AgentRuntime._build_iteration_call_options()]
        |-- OutputSchemaFormatter.build_response_format(provider, schema)
        |-- call_options["response_format"] = <provider payload>
        |
        v
[TextModelRunner.arun(response_format=...)]
        |-- replace(config, response_format=...)
        |
        v
[OpenAIProvider / GeminiProvider / CompatibleProvider]
        |-- _attach_response_format(payload, config)  ← existing, unchanged

[AgentRuntime.execute_tool_call()] (tool path)
        |-- _execute_tool(tool, call)
        |-- OutputSchemaFormatter.validate(result.output, spec.output_schema)
        |-- on mismatch → ToolResult.error("tool call error: output shape mismatch: ...")
```

---

## 6. Detailed Design

### 6.1 `OutputSchemaFormatter`

**File:** `vidbyte/providers/output_schema.py`
**Type:** New file

#### What it does
Single class owning all output schema responsibilities: resolution, provider-native format construction, and output validation.

#### Interface / API
```python
class OutputSchemaFormatter:
    def resolve_schema(self, schema: type | Mapping[str, Any]) -> dict[str, Any]: ...
    def build_response_format(self, provider: str, schema: type | Mapping[str, Any]) -> Mapping[str, Any] | None: ...
    def validate(self, output: str, schema: type | Mapping[str, Any]) -> tuple[Any, str | None]: ...
```

#### Logic / Algorithm

**`resolve_schema`**
1. If `schema` is a subclass of Pydantic `BaseModel`, call `schema.model_json_schema()` and return a copy.
2. If `schema` is a `Mapping`, return a `dict` copy.
3. Otherwise raise `ConfigurationError`.

**`build_response_format`**
1. Call `resolve_schema(schema)` to get the plain dict.
2. Normalize provider string: `provider.lower()`.
3. Dispatch to a private builder by provider family:
   - `"openai"` or `"gpt"` in provider → `_openai_format(schema_dict)`
   - `"gemini"` or `"google"` in provider → `_gemini_format(schema_dict)`
   - `"anthropic"` or `"claude"` in provider → `None`
   - Otherwise (xai/compatible) → `_compatible_format(schema_dict)`
4. Return the built dict or `None`.

**Private builders:**
- `_openai_format(schema)` → `{"type": "json_schema", "name": "agent_output", "schema": schema, "strict": True}`
- `_gemini_format(schema)` → `schema` (raw dict; GeminiProvider already wraps it)
- `_compatible_format(schema)` → `{"type": "json_schema", "json_schema": {"name": "agent_output", "schema": schema, "strict": True}}`

**`validate`**
1. Parse `output` as JSON (`json.loads`); on `json.JSONDecodeError` return `(None, "output is not valid JSON: ...")`.
2. If `schema` is a Pydantic `BaseModel` subclass, call `schema.model_validate(parsed)`; on `ValidationError` return `(None, str(exc))`.
3. If `schema` is a dict, return `(parsed, None)` — dict schemas are treated as opaque (no deep validation).
4. On success return `(parsed_object, None)`.

#### Edge Cases & Error Handling
- Schema is neither Pydantic nor dict → `ConfigurationError` in `resolve_schema`
- Provider string is empty → falls through to compatible format (safe default)
- `output` is an empty string → `json.JSONDecodeError`, error returned

---

### 6.2 `ToolSpec` — add `output_schema` field

**File:** `vidbyte/lib/dataclasses/tools.py`
**Type:** Modified

#### What it does
Carries the optional schema declaration from tool definition through to runtime validation.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class ToolSpec:
    ...
    output_schema: type | Mapping[str, Any] | None = None
```

#### Logic / Algorithm
Additive field with default `None`. No logic change. All existing `ToolSpec(...)` constructors that omit it receive `None`.

#### Edge Cases & Error Handling
- `ToolSpec` is frozen; the field is set at construction time only.

---

### 6.3 `FunctionTool` — add `output_schema` param

**File:** `vidbyte/tools/function_tool.py`
**Type:** Modified

#### What it does
Exposes `output_schema` so function-based tools can declare their expected return shape.

#### Interface / API
```python
class FunctionTool(BaseTool):
    def __init__(self, func, *, name=None, description=None, permission=..., output_schema=None): ...
```

#### Logic / Algorithm
1. Accept `output_schema: type | Mapping[str, Any] | None = None` in `__init__`.
2. Store as `self._output_schema = output_schema`.
3. In `_build_spec()`, pass `output_schema=self._output_schema` to `ToolSpec(...)`.
4. `from_function` classmethod gains the same param.

#### Edge Cases & Error Handling
- No validation of `output_schema` at construction time; the runtime validates at execution time.

---

### 6.4 `BaseAgent` — add `output_schema` param

**File:** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does
Exposes `output_schema` in the public agent API, stores it, threads it into the runtime, and preserves it through `fork()`.

#### Interface / API
```python
class BaseAgent:
    def __init__(self, ..., output_schema: type | Mapping[str, Any] | None = None) -> None: ...
```

#### Logic / Algorithm
1. Accept `output_schema` as a keyword argument after all existing params.
2. Store `self.output_schema = output_schema`.
3. In `_runtime()`, pass `output_schema=self.output_schema` to the `runtime_cls(...)` constructor call.
4. In `fork()`, pass `output_schema=self.output_schema` when constructing the child agent.

#### Edge Cases & Error Handling
- `None` (default) is a no-op at every downstream call site.

---

### 6.5 `AgentRuntime` — inject `response_format`, validate tool outputs, populate `structured`

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does
Three additions: accept `output_schema` in `__init__`, attach the native format to each model call, validate tool outputs post-execution.

#### Interface / API
```python
class AgentRuntime:
    def __init__(self, ..., output_schema: type | Mapping[str, Any] | None = None) -> None: ...
```

#### Logic / Algorithm

**`__init__`**
1. Accept `output_schema` and store as `self.output_schema = output_schema`.
2. Construct `self._schema_formatter = OutputSchemaFormatter()`.

**`_build_iteration_call_options`**
After assembling `call_options`, append before returning:
```python
if self.output_schema is not None:
    fmt = self._schema_formatter.build_response_format(provider, self.output_schema)
    if fmt is not None:
        call_options.setdefault("response_format", fmt)
```
The `provider` argument is threaded in (already available in `_arun_once`).

Wait — `_build_iteration_call_options` doesn't currently receive `provider`. We add it as a parameter.

**`execute_tool_call`** (post-execution validation)
After `result = await self._execute_tool(tool, call)`, insert:
```python
spec = tool.spec()
if spec.output_schema is not None and result.status.value == "success":
    _, error = self._schema_formatter.validate(result.output, spec.output_schema)
    if error:
        result = ToolResult.error(
            call.tool_name,
            f"tool call error: output shape mismatch: {error}",
            metadata={"error": "output_schema_violation", "detail": error},
        )
```

**`_final_result`** (populate `structured` on agent output)
After building the `AgentResult`, if `self.output_schema` is not None:
```python
parsed, _ = self._schema_formatter.validate(output, self.output_schema)
return AgentResult(..., structured=parsed)
```

#### Edge Cases & Error Handling
- `output_schema is None` → all new code paths are skipped; zero behavioral change.
- Provider returns `None` from `build_response_format` (Anthropic) → `call_options` unmodified.
- Tool already returned `ToolStatus.ERROR` → no validation attempted (only validates on `success`).

---

### 6.6 `TextModelRunner` — accept `response_format` in `arun()`

**File:** `vidbyte/lib/runners/text.py`
**Type:** Modified

#### What it does
Allows `response_format` to flow from `call_options` through `_call_with_supported_kwargs` into the provider config.

#### Interface / API
```python
async def arun(self, prompt: str, *, system=None, metadata=None, tools=(), tool_choice=None, messages=(), response_format: Mapping[str, Any] | None = None) -> TextModelResponse: ...
```

#### Logic / Algorithm
1. Add `response_format: Mapping[str, Any] | None = None` to the signature.
2. In `replace(self._config, ...)`, include `response_format=response_format`.
3. `run()` mirrors the same addition to its signature and passes it to `arun()`.

#### Edge Cases & Error Handling
- `response_format=None` (default) → `replace(self._config, response_format=None)` which is the same as the current `None` default.

---

### 6.7 `AgentResult` — add `structured` field

**File:** `vidbyte/lib/dataclasses/strategies.py`
**Type:** Modified

#### What it does
Surfaces the parsed structured output object so callers don't have to re-parse `result.output`.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class AgentResult:
    output: str
    strategy_name: str
    calls: tuple[Any, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    structured: Any = None
```

#### Logic / Algorithm
Additive field. Existing `AgentResult(output=..., strategy_name=...)` constructors are unchanged.

#### Edge Cases & Error Handling
- `structured=None` when schema parsing failed or `output_schema` was not set.

---

### 6.8 `vidbyte/__init__.py` — export `OutputSchemaFormatter`

**File:** `vidbyte/__init__.py`
**Type:** Modified

#### What it does
Exposes `OutputSchemaFormatter` at the top-level so power users can call `build_response_format` or `validate` directly.

#### Logic / Algorithm
Add import and `__all__` entry for `OutputSchemaFormatter`.

---

## 7. Data Model Changes

### 7.1 `ToolSpec`

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: tuple[ToolParameter, ...] = ()
    permission: ToolPermission = ToolPermission.SAFE
    metadata: Mapping[str, Any] = field(default_factory=dict)
    input_schema: Mapping[str, Any] | None = None
    binds_to_primitive: str | None = None
    output_schema: type | Mapping[str, Any] | None = None  # NEW
```

**Migration strategy:** Additive field with default `None`. All existing `ToolSpec(...)` calls are backward-compatible.

### 7.2 `AgentResult`

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class AgentResult:
    output: str
    strategy_name: str
    calls: tuple[Any, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    structured: Any = None  # NEW
```

**Migration strategy:** Additive field with default `None`. All existing construction sites are backward-compatible.

---

## 8. API Changes

N/A — This feature has no REST API endpoints. All changes are to the Python SDK surface.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/providers/output_schema.py` | `OutputSchemaFormatter` class — schema resolution, provider format building, output validation |
| MODIFY | `vidbyte/lib/dataclasses/tools.py` | Add `output_schema` field to `ToolSpec` |
| MODIFY | `vidbyte/tools/function_tool.py` | Add `output_schema` param to `FunctionTool.__init__` and `from_function` |
| MODIFY | `vidbyte/agents/base.py` | Add `output_schema` param, store, fork-preserve, pass to runtime |
| MODIFY | `vidbyte/agents/runtime.py` | Accept `output_schema`, inject `response_format` per iteration, validate tool outputs |
| MODIFY | `vidbyte/lib/runners/text.py` | Add `response_format` param to `arun()` / `run()` |
| MODIFY | `vidbyte/lib/dataclasses/strategies.py` | Add `structured: Any = None` to `AgentResult` |
| MODIFY | `vidbyte/__init__.py` | Export `OutputSchemaFormatter` |

**Summary:** 1 file to create, 7 files to modify, 0 files to delete.

---

## 10. Testing Plan

N/A per task instructions — tests and verification scripts are out of scope for this workflow.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| pydantic | >=2,<3 (already declared) | `BaseModel.model_json_schema()` and `model_validate()` | None — already in `pyproject.toml` |
| json (stdlib) | — | Parse tool/agent output strings for validation | None |

---

## 12. Rollout & Deployment

- **Breaking change:** No. All new parameters default to `None`; existing code is unchanged.
- **Feature flags:** None.
- **Deployment order:** Single package — no multi-service coordination needed.
- **Rollback:** Drop the branch; `main` is untouched.

---

## 13. Open Questions

- [ ] Should `FunctionTool` auto-detect `output_schema` from the function's return type annotation (e.g. `-> MyModel`)? Deferred — explicit opt-in is safer for a first pass.
- [ ] Should `AgentResult.structured` also be populated from the IS_DONE tool `output` field (which comes from the isDone tool call argument, not the raw model text)? Currently yes — `_final_result` receives the IS_DONE output string and parses it.
- [ ] Should validation errors on tool output preserve the original result as metadata rather than replacing it? Current design replaces; could add `"original_output"` to metadata if useful.

---

## 14. Alternatives Considered

### Alternative 1: Keep `StructuredOutputMode` enum from PR #96
- **What:** Three modes (AUTO, NATIVE, PROMPT) giving users control over fallback behavior.
- **Why rejected:** Adds complexity the user explicitly rejected. The desired behavior is: native when available, nothing otherwise. A mode enum solves a problem the user doesn't have.

### Alternative 2: Prompt-injection fallback for unsupported providers
- **What:** When provider doesn't support native format, inject the schema as a JSON schema block in the system prompt.
- **Why rejected:** Prompt injection is fragile (model may ignore it), pollutes the system prompt, and gives false confidence. The user explicitly said not to do this.

### Alternative 3: Raise `ConfigurationError` when provider doesn't support native structured output
- **What:** Fail loudly if `output_schema` is set and the provider is Anthropic.
- **Why rejected:** Too restrictive. Users may want to set `output_schema` at the agent level and route to different providers at runtime; silently doing nothing is cleaner than failing at construction time when the provider may change.

### Alternative 4: Validate agent output and surface an error result on mismatch
- **What:** Apply the same mismatch-error behavior to agent output as to tool output.
- **Why rejected:** Tool outputs are produced by Python code — the schema is a hard contract. Agent outputs are produced by a model — the schema is a request. Failing the entire agent run on a bad JSON response is too disruptive; `structured=None` is the right signal.
