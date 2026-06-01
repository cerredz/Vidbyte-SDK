# Design Doc: Typed Output Schema

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-01
**Last Updated:** 2026-06-01

---

## 1. Overview

Every output surface in the SDK — `ToolResult.output`, `AgentResult.output`, `AgentMessage.content` — is a plain `str`. Consumers re-parse that string to recover structure the producer already had. This feature introduces a first-class typed output layer: tool authors and agent authors declare an `output_schema` once; the SDK runtime validates the actual output against that schema, and returns a `structured` field alongside the string that downstream stages can consume directly without re-parsing.

---

## 2. Goals & Non-Goals

### Goals
- Add `output_schema: type | Mapping[str, Any] | None` to `ToolSpec` and `AgentSpec` / `BaseAgent`
- Add `structured: Any = None` to `ToolResult` and `AgentResult` — populated by the runtime when a schema is declared and validation passes
- Validate tool output immediately after `execute()` returns in both `ToolExecutor` and `AgentRuntime`
- Validate agent final output (both `IS_DONE` and `FINAL_RESPONSE` stop paths) when a schema is declared
- Inject a JSON schema hint into the agent system prompt when `output_schema` is set so the model knows the expected shape
- Accept both Pydantic `BaseModel` subclasses (validated via `TypeAdapter`) and raw JSON Schema dicts (validated via JSON parseability + Pydantic TypeAdapter where possible)
- Preserve full backward compatibility — all existing code that constructs `ToolResult`, `AgentResult`, and `ToolSpec` without `output_schema` continues to work unchanged

### Non-Goals
- Provider-native constrained decoding (`response_format` / tool_choice forcing) — this is a follow-up feature; V1 is declaration + validation + prompt injection
- Automatic retry on schema validation failure — callers can handle validation errors via middleware or by checking `result.structured is None`
- Modifying `AgentMessage.content` — out of scope for this PR
- Adding `jsonschema` as a dependency — raw dict schemas are validated for JSON parseability only; full JSON Schema keyword validation requires a follow-up that adds `jsonschema` as an optional dep
- Modifying pipelines (`AgentResult` flows through pipelines unchanged; pipeline stages can inspect `structured`)

---

## 3. Background & Context

The SDK passes text across every seam. A tool that queries a database and gets `{"rows": [...], "count": 5}` serializes it to a string. The caller that receives `ToolResult.output` must re-parse it to get structure back. There is no contract on the shape — any mismatch is a runtime surprise, not a declaration-time one. The same problem exists for agent final answers: callers parse the string response and hope it matches what they expect.

Adding `output_schema` and `structured` solves this at the declaration layer. It does not require changes to how tools are implemented (they continue returning `ToolResult.success(name, json_str)`), but it makes the runtime responsible for parsing, validating, and surfacing structure.

The existing `ToolSpec.input_schema` field (already present for MCP-compatible tools) provides the precedent pattern — we mirror it on the output side.

Pydantic is already a `pyproject.toml` dependency (`pydantic>=2,<3`), so the Pydantic validation path adds no new requirements.

---

## 4. Requirements

### Functional Requirements

1. `ToolSpec` must accept `output_schema: type | Mapping[str, Any] | None = None`
2. `ToolResult` must carry `structured: Any = None`, populated after successful validation
3. `AgentResult` must carry `structured: Any = None`, populated after successful validation
4. `AgentSpec` must accept `output_schema: type | Mapping[str, Any] | None = None`
5. `BaseAgent.__init__` must accept `output_schema` and store it
6. When `ToolSpec.output_schema` is set and the tool returns `ToolStatus.SUCCESS`, the runtime must parse `result.output` as JSON and validate it against the schema before returning to the caller
7. If validation fails, the runtime must return `ToolResult.error` with a `"output_schema_violation"` error key — it must NOT silently return an invalid result
8. When `BaseAgent.output_schema` is set, the agent system prompt must include a JSON schema hint block describing the required output shape
9. When the agent produces a final result (IS_DONE or FINAL_RESPONSE), the runtime must validate `output` against `output_schema` and populate `AgentResult.structured`
10. Agent schema validation failure must set `AgentResult.structured = None` and add a `"output_schema_error"` key to `AgentResult.metadata` — it must NOT raise an exception (agent results always return)
11. `ToolResult.success()` and `ToolResult.error()` classmethods must work unchanged — `structured` defaults to `None` when not supplied
12. `AgentRuntime._with_middleware_metadata` must preserve `structured` when rebuilding `AgentResult`
13. `BaseAgent.fork()` must forward `output_schema` to child agents

### Non-Functional Requirements
- No new required dependencies beyond existing `pydantic>=2`
- All existing tests must continue to pass unmodified
- Validation overhead must be negligible relative to I/O — it is a JSON parse + Pydantic model validate, O(n) in output size
- The `structured` field must serialize cleanly (it holds either a Pydantic model instance or a dict/primitive — both JSON-serializable)

---

## 5. High-Level Design

The feature adds three logical layers: **declaration**, **validation**, and **propagation**.

**Declaration** lives in the dataclass layer (`ToolSpec`, `AgentSpec`, `AgentResult`, `ToolResult`). A new utility module `vidbyte/tools/output_schema.py` owns schema resolution (Pydantic type → JSON Schema dict) and validation logic.

**Validation** for tools is in `ToolExecutor.execute_call` and `AgentRuntime._execute_tool` / `execute_tool_call` — both call `OutputSchemaValidator.validate(result.output, spec.output_schema)` immediately after `execute()` returns. Validation for agents is in `AgentRuntime._final_result` and the IS_DONE tool call handling path.

**Propagation** ensures `structured` is never dropped when the runtime reconstructs result objects (middleware metadata attachment, result passing through `_finish_result`).

```
[Tool.execute() → str output]
        ↓
[AgentRuntime.execute_tool_call]
        ↓
[OutputSchemaValidator.validate(output, spec.output_schema)]
        ↓
[ToolResult(output=str, structured=T | None)]
        ↓
[Caller reads result.structured directly — no re-parsing]

[Agent loop → final answer str]
        ↓
[AgentRuntime._final_result]
        ↓
[OutputSchemaValidator.validate(output, output_schema)]
        ↓
[AgentResult(output=str, structured=T | None)]
```

---

## 6. Detailed Design

### 6.1 `OutputSchemaValidator`

**File:** `vidbyte/tools/output_schema.py`
**Type:** New file

#### What it does
Owns schema resolution (accept Pydantic type or JSON Schema dict, return a canonical schema), validation (parse JSON string, validate against schema), and system prompt hint generation.

#### Interface / API
```python
class OutputSchemaValidator:
    @staticmethod
    def resolve(schema: type | Mapping[str, Any]) -> Mapping[str, Any]:
        # Returns JSON Schema dict from Pydantic type or raw dict.

    @staticmethod
    def validate(output: str, schema: type | Mapping[str, Any]) -> tuple[Any, str | None]:
        # Returns (parsed_value, None) on success or (None, error_message) on failure.

    @staticmethod
    def schema_prompt_hint(schema: type | Mapping[str, Any]) -> str:
        # Returns a system prompt fragment instructing the model to produce the schema.
```

#### Logic / Algorithm
1. `resolve(schema)`:
   - If `schema` is a `type` with `model_json_schema` attr → call `schema.model_json_schema()` and return
   - Otherwise → `dict(schema)`

2. `validate(output, schema)`:
   - `json.loads(output)` — on `JSONDecodeError`, return `(None, "Output is not valid JSON: ...")`
   - If `schema` is a `type` with `model_validate` attr → `schema.model_validate(parsed)` — on `ValidationError`, return `(None, "Output does not match schema: ...")`; on success return `(validated_model_instance, None)`
   - Otherwise → return `(parsed, None)` (JSON parseability is the contract for raw dict schemas in V1)

3. `schema_prompt_hint(schema)`:
   - `resolved = resolve(schema)`
   - Return a formatted string block: `"Your final response MUST be valid JSON conforming to this schema:\n```json\n{json.dumps(resolved, indent=2)}\n```"`

#### Edge Cases & Error Handling
- If `output` is empty string → `json.loads("")` raises `JSONDecodeError` → returns `(None, "Output is not valid JSON: ...")`
- If `schema` is neither a Pydantic type nor a dict → `dict(schema)` will fail; callers are expected to pass valid schemas; this is a programmer error, not a runtime error
- Pydantic `ValidationError` is caught and returned as a string — never raised to callers

---

### 6.2 `ToolSpec` — add `output_schema`

**File:** `vidbyte/lib/dataclasses/tools.py`
**Type:** Modified

#### What it does
Declares the expected output shape for a tool alongside its existing input schema.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: tuple[ToolParameter, ...] = ()
    permission: ToolPermission = ToolPermission.SAFE
    metadata: Mapping[str, Any] = field(default_factory=dict)
    input_schema: Mapping[str, Any] | None = None
    output_schema: type | Mapping[str, Any] | None = None  # NEW
    binds_to_primitive: str | None = None
```

#### Edge Cases & Error Handling
- `output_schema` is not validated at construction time — invalid schema values are caught at validation time in the executor

---

### 6.3 `ToolResult` — add `structured`

**File:** `vidbyte/lib/dataclasses/tools.py`
**Type:** Modified

#### What it does
Carries the parsed and validated typed value alongside the raw string output.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_name: str
    status: ToolStatus
    output: str
    structured: Any = None   # NEW — None when no schema or validation failed
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

The `success()`, `error()`, and `failure()` classmethods are unchanged — they omit `structured` and it defaults to `None`.

#### Edge Cases & Error Handling
- `structured` is `None` for all error results, all results from tools without `output_schema`, and all results where validation failed
- `dataclasses.replace(result, structured=parsed)` is used by the executor to populate this field — frozen dataclasses support `replace()`

---

### 6.4 `AgentResult` — add `structured`

**File:** `vidbyte/lib/dataclasses/strategies.py`
**Type:** Modified

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class AgentResult:
    output: str
    strategy_name: str
    structured: Any = None   # NEW
    calls: tuple[Any, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

---

### 6.5 `AgentSpec` — add `output_schema`

**File:** `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class AgentSpec:
    name: str
    system_prompt: str
    description: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    context_items: tuple[ContextItem, ...] = ()
    context_manager: ContextManager | None = None
    algorithm: ContextWindowAlgorithm | str | None = None
    output_schema: type | Mapping[str, Any] | None = None  # NEW
```

---

### 6.6 `ToolExecutor` — add output schema validation

**File:** `vidbyte/tools/executor.py`
**Type:** Modified

#### What it does
Validates the tool's string output against `spec.output_schema` immediately after `tool.execute(call)` returns successfully.

#### Logic / Algorithm
1. After `result = await tool.execute(call)` succeeds
2. If `spec.output_schema` is not None and `result.status == ToolStatus.SUCCESS`:
   - Call `OutputSchemaValidator.validate(result.output, spec.output_schema)`
   - If error: return `ToolResult.error(spec.name, f"Output schema violation: {error}", metadata={"error": "output_schema_violation"})`
   - If success: `result = dataclasses.replace(result, structured=parsed)`
3. Return `result`

#### Edge Cases & Error Handling
- Schema violation returns `ToolResult.error`, not raises — consistent with existing error handling in the executor
- Tools without `output_schema` are unaffected (fast path: `if spec.output_schema is None: return result`)

---

### 6.7 `AgentRuntime` — output schema for tools and agents

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does
Stores `output_schema`, injects schema hint into the system prompt, validates tool results, and validates/populates `structured` on the final `AgentResult`.

#### Interface / API — constructor change
```python
def __init__(self, *, agent_name, system_prompt, tools, permission_policy,
             config=None, tracer=None, middleware=(), run_id=None,
             algorithm=None, context_manager=None,
             output_schema: type | Mapping[str, Any] | None = None) -> None:
    ...
    self.output_schema = output_schema
```

#### Logic / Algorithm — system prompt injection
`_build_system_string` appends the schema hint when `output_schema` is set:
```python
def _build_system_string(self, context):
    # existing assembly of fixed + primitives_zone + body
    ...
    if self.output_schema is not None:
        hint = OutputSchemaValidator.schema_prompt_hint(self.output_schema)
        result = f"{result}\n\n{hint}" if result else hint
    return result
```

#### Logic / Algorithm — tool output validation
`_execute_tool` calls the tool; after the result is returned, `execute_tool_call` applies schema validation:
```python
result = await self._execute_tool(tool, call)
spec = tool.spec()
if spec.output_schema is not None and result.status.value == "success":
    parsed, error = OutputSchemaValidator.validate(result.output, spec.output_schema)
    if error:
        result = ToolResult.error(call.tool_name, f"Output schema violation: {error}",
                                  metadata={"error": "output_schema_violation"})
    else:
        result = dataclasses.replace(result, structured=parsed)
```

#### Logic / Algorithm — agent final result validation
`_final_result` validates `output` against `self.output_schema`:
```python
def _final_result(self, output, *, runner_metadata, contexts, iteration_count, tokens_used, stop_reason):
    structured = None
    schema_error = None
    if self.output_schema is not None:
        parsed, error = OutputSchemaValidator.validate(output, self.output_schema)
        if error is None:
            structured = parsed
        else:
            schema_error = error
    metadata = {
        **self._runtime_metadata(...),
        **runner_metadata,
    }
    if schema_error:
        metadata["output_schema_error"] = schema_error
    return AgentResult(output=output, strategy_name="direct_runner",
                       structured=structured, metadata=metadata)
```

#### Logic / Algorithm — preserve `structured` in `_with_middleware_metadata`
```python
def _with_middleware_metadata(self, result):
    metadata = dict(result.metadata)
    metadata["middleware"] = self.middleware.metadata()
    return AgentResult(output=result.output, strategy_name=result.strategy_name,
                       structured=result.structured,   # NEW — was missing
                       calls=result.calls, metadata=metadata)
```

#### Edge Cases & Error Handling
- Agent validation failure does NOT raise; it sets `structured=None` and logs the error in `metadata["output_schema_error"]`
- When `output_schema is None` (the common case), no validation is performed — zero overhead

---

### 6.8 `BaseAgent` — accept and store `output_schema`

**File:** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does
Accepts `output_schema` in `__init__`, stores it, passes it to `_runtime()`, and forwards it in `fork()`.

#### Logic / Algorithm
1. Add `output_schema: type | Mapping[str, Any] | None = None` parameter to `__init__`
2. Store as `self.output_schema = output_schema`
3. In `_runtime()`, pass `output_schema=self.output_schema` to `AgentRuntime`
4. In `fork()`, pass `output_schema=self.output_schema` when constructing the child (unless caller overrides it)

---

## 7. Data Model Changes

### 7.1 `ToolSpec` — new field

```python
output_schema: type | Mapping[str, Any] | None = None
```

**Migration strategy:** Additive field with default `None`. No migration needed — all existing `ToolSpec` construction omits it and gets `None`.

### 7.2 `ToolResult` — new field

```python
structured: Any = None
```

**Migration strategy:** Additive field with default `None`. Classmethods `success()`, `error()`, `failure()` unchanged.

### 7.3 `AgentResult` — new field

```python
structured: Any = None
```

**Migration strategy:** Additive field with default `None`. All existing `AgentResult(output=..., strategy_name=...)` construction unchanged.

### 7.4 `AgentSpec` — new field

```python
output_schema: type | Mapping[str, Any] | None = None
```

**Migration strategy:** Additive.

---

## 8. API Changes

N/A — this is an internal SDK feature with no HTTP API endpoints.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/tools/output_schema.py` | New schema resolution and validation utility |
| MODIFY | `vidbyte/lib/dataclasses/tools.py` | Add `output_schema` to `ToolSpec`; add `structured` to `ToolResult` |
| MODIFY | `vidbyte/lib/dataclasses/strategies.py` | Add `structured` to `AgentResult` |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add `output_schema` to `AgentSpec` |
| MODIFY | `vidbyte/tools/executor.py` | Add output schema validation in `execute_call` |
| MODIFY | `vidbyte/agents/runtime.py` | Store `output_schema`; inject system prompt hint; validate tool + agent outputs; preserve `structured` in `_with_middleware_metadata` |
| MODIFY | `vidbyte/agents/base.py` | Accept `output_schema`; store; pass to `_runtime()`; update `fork()` |
| MODIFY | `vidbyte/tools/__init__.py` | Export `OutputSchemaValidator` |
| CREATE | `docs/design/typed-output-schema.md` | This design doc |
| CREATE | `scripts/test-typed-output-schema.py` | Verification script for all test cases |

---

## 10. Testing Plan

### Unit Tests

**OutputSchemaValidator**
- `resolve()` with Pydantic BaseModel type returns its `model_json_schema()` dict — [Hidden Assumption: Pydantic is present and the type has the method]
- `resolve()` with a raw dict returns a copy of that dict — [Edge Case]
- `validate()` with valid JSON and a Pydantic model returns `(model_instance, None)` — [Happy path]
- `validate()` with invalid JSON string returns `(None, error_message)` — [Edge Case]
- `validate()` with empty string returns `(None, error_message)` — [Edge Case]
- `validate()` with JSON that fails Pydantic validation returns `(None, error_message)` — [Hidden Failure: model validates wrong shape silently]
- `validate()` with valid JSON and a raw dict schema returns `(parsed_dict, None)` — [Happy path]
- `schema_prompt_hint()` returns a string containing the serialized schema — [Silent Failure: hint is empty or malformed]

**ToolSpec**
- `ToolSpec` constructed without `output_schema` defaults to `None` — [Hidden Assumption: backward compat]
- `ToolSpec` constructed with Pydantic type as `output_schema` stores it — [Happy path]
- `ToolSpec` constructed with dict as `output_schema` stores it — [Happy path]

**ToolResult**
- `ToolResult.success()` without `structured` produces `structured=None` — [Hidden Assumption: backward compat]
- `ToolResult` with explicit `structured` stores it — [Happy path]
- `dataclasses.replace(result, structured=value)` works on frozen ToolResult — [Hidden Failure: frozen dataclass may reject replace]

**AgentResult**
- `AgentResult(output=..., strategy_name=...)` without `structured` produces `structured=None` — [Hidden Assumption: backward compat]

**ToolExecutor — output schema validation**
- Tool with `output_schema` set and valid JSON output → `result.structured` is populated — [Happy path]
- Tool with `output_schema` set and non-JSON output → returns `ToolResult.error` with `"output_schema_violation"` metadata — [Hidden Failure: invalid output passes through silently]
- Tool with `output_schema` set and JSON that fails Pydantic validation → returns `ToolResult.error` — [Hidden Failure]
- Tool with `output_schema=None` and any output → `result.structured` is `None`, no error — [Hidden Assumption: schema is optional]
- Tool with `output_schema` set but returning `ToolStatus.ERROR` → no validation attempted, `structured` is `None` — [Edge Case: failed tools should not be validated]

**AgentRuntime — tool output validation**
- Same cases as ToolExecutor above, but exercised through `AgentRuntime.execute_tool_call` — [Hidden Assumption: both code paths must stay in sync]

**AgentRuntime — system prompt injection**
- When `output_schema` is set, `_build_system_string` includes the hint block — [Silent Failure: hint is silently omitted]
- When `output_schema` is `None`, `_build_system_string` output is identical to current behavior — [Hidden Assumption: no regression]

**AgentRuntime — final result validation**
- When `output_schema` is set and output is valid JSON matching schema, `AgentResult.structured` is populated — [Happy path]
- When `output_schema` is set and output is not valid JSON, `AgentResult.structured` is `None` and `metadata` contains `"output_schema_error"` — [Hidden Failure: error lost in metadata]
- When `output_schema` is `None`, `AgentResult.structured` is `None` and no `"output_schema_error"` key — [Hidden Assumption]

**AgentRuntime — `_with_middleware_metadata`**
- `_with_middleware_metadata` preserves `result.structured` when rebuilding the result — [Silent Failure: structured is dropped on every run due to missing field]

**BaseAgent**
- `BaseAgent` constructed without `output_schema` defaults to `None` — [Hidden Assumption: backward compat]
- `BaseAgent.fork()` preserves `output_schema` in child — [Silent Failure: schema silently lost on fork]

### Integration Tests

- Full agent run (via direct runner mocked) with `output_schema` set → `AgentResult.structured` matches expected shape
- Full tool execute round-trip with `output_schema` → `ToolResult.structured` populated
- Agent with `output_schema` but whose model returns non-conformant JSON → `structured=None`, `metadata["output_schema_error"]` set, run does not raise
- Existing tool tests (EchoTool, ToolExecutor tests) pass unchanged — no regressions — [Hidden Assumption: additive change doesn't break existing call sites]

### Manual / QA Test Cases

1. Given a `BaseTool` with `output_schema=MyPydanticModel` and `execute()` returning `json.dumps(valid_data)`, when called through `ToolExecutor`, then `result.structured` is a `MyPydanticModel` instance — [Happy path]
2. Given a `BaseTool` with `output_schema` and `execute()` returning `"not json"`, when called, then `result.status == ToolStatus.ERROR` and `result.metadata["error"] == "output_schema_violation"` — [Hidden Failure]
3. Given a `BaseAgent` with `output_schema={"type": "object"}`, when inspecting the system prompt, then it contains the schema hint block — [Silent Failure: hint omitted]
4. Given a `BaseAgent` with `output_schema` whose model output is valid JSON, when run completes, then `agent_result.structured` is not None — [Happy path]
5. Given `BaseAgent.fork()` on an agent with `output_schema` set, then `child.output_schema` equals `parent.output_schema` — [Silent Failure: schema lost on fork]

---

## 11. Dependencies & External Services

| Dependency | Version | Purpose | Risk |
|------------|---------|---------|------|
| `pydantic` | `>=2,<3` (existing) | Schema resolution via `model_json_schema()`, validation via `model_validate()` and `TypeAdapter` | None — already in deps |

Note: Full JSON Schema keyword validation for raw dict schemas (e.g., validating `minimum`, `pattern`, `required` constraints) requires `jsonschema`. V1 only guarantees JSON parseability for raw dict schemas. Add `jsonschema` as an optional dep in a follow-up if full JSON Schema enforcement is needed.

---

## 12. Rollout & Deployment

- No breaking changes — all new fields have defaults of `None`; all existing tests pass unchanged
- No feature flags — the feature is opt-in by setting `output_schema` on `ToolSpec` or `BaseAgent`
- No deployment order requirements — single library PR
- Rollback: revert the PR; no migrations to undo

---

## 13. Open Questions

- [ ] Should agent schema validation failure produce a hard error (raise) rather than a soft one (metadata key)? Currently it's soft — the agent always returns a result. A hard-error mode could be a separate `strict_output_schema: bool = False` parameter.
- [ ] Should `fork()` allow overriding `output_schema`? Currently it forwards the parent's. Adding it as an explicit `fork()` parameter is a follow-up.
- [ ] V2 follow-up: provider-native constrained decoding — inject `vidbyte_structured_output` as a forced tool call for Anthropic, set `response_format` for OpenAI/Gemini. This eliminates the need for prompt injection and makes the schema structurally enforced at the token level.

---

## 14. Alternatives Considered

### Alternative 1: Provider-native constrained decoding in V1
- **What:** For Anthropic, inject a synthetic `vidbyte_structured_output` tool and force `tool_choice`; for OpenAI/Gemini, set `response_format`. The model cannot emit tokens violating the schema.
- **Why rejected for V1:** This only works for single-shot agents (no intermediate tool calls) unless tool_choice injection is deferred to the final iteration. Detecting "final iteration" requires redesigning the agentic loop. Agent prompt injection + validation delivers immediate value without the complexity. Provider-native enforcement is scoped as a V2 follow-up.

### Alternative 2: Separate `TypedToolResult[T]` generic class
- **What:** Introduce a `TypedToolResult(Generic[T])` distinct from `ToolResult`, returned only when schema is set.
- **Why rejected:** Breaks the existing type contract — every caller expects `ToolResult`. A `structured: Any` field on the existing class is additive and requires no changes in call sites.

### Alternative 3: Require `jsonschema` as a dependency for raw dict schemas
- **What:** Add `jsonschema` to `pyproject.toml` and validate raw dict schemas fully (all JSON Schema keywords).
- **Why rejected for V1:** Adds a new required dependency. Pydantic is already available and covers the primary use case (typed Python models). `jsonschema` can be added as an optional dep in a follow-up when raw dict schema validation fidelity is needed.
