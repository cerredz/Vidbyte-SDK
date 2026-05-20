# Design Doc: Custom Function Tools

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-20
**Last Updated:** 2026-05-20

---

## 1. Overview

Add a decorator-first custom tool API that lets SDK users turn ordinary Python functions into Vidbyte tools with `@vidbyte_tool`. The decorator will inspect a function's signature, docstring, and type hints, generate a tool spec and JSON Schema, validate runtime arguments through Pydantic, execute sync or async functions safely, and make the wrapped tool attachable to registries, strategies, agents, providers, and harnesses through a shared `ToolMixin.with_tools()` composition pattern.

---

## 2. Goals & Non-Goals

### Goals

- Expose `@vidbyte_tool` from the public SDK surface.
- Support async and sync Python functions with standard type hints and docstrings.
- Generate a `ToolSpec` from function name, docstring, signature, defaults, and type hints.
- Generate JSON Schema for model/provider function-calling APIs.
- Validate incoming tool-call arguments before user code receives them.
- Normalize return values into native `ToolResult` objects.
- Allow `ToolRegistry.register()` and `ToolRegistry(tools=[...])` to accept `BaseTool` instances, decorated functions, and undecorated callables.
- Add `ToolMixin.with_tools()` as a chainable way to attach tools to harnesses, strategies, agents, and provider-facing runners.
- Cascade harness-level tools into the active strategy at execution time.
- Preserve compatibility with the existing and planned `BaseTool`, `ToolRegistry`, `ToolExecutor`, `StrategyMixin`, ReAct, and CodeAct architecture.

### Non-Goals

- No remote tool hosting, MCP server implementation, or network tool marketplace.
- No automatic provider-side function-calling execution loop in this PR beyond exposing provider-ready schemas.
- No arbitrary code generation or dynamic tool creation by a model.
- No sandboxing for user function bodies beyond validation and executor error isolation.
- No UI for tool permissions or confirmations.
- No persistent registry or database-backed tool catalog.

---

## 3. Background & Context

- The current `main` branch of `vidbyte-sdk` is still a small namespace scaffold. `VidbyteSDK` exposes `harnesses`, `tools`, and `providers`, but `ToolsClient`, `HarnessClient`, and `ProvidersClient` are empty.
- Local untracked design docs already define the intended architecture for tools, strategies, harnesses, agents, and multi-agent orchestration. They consistently point toward `BaseTool`, `ToolSpec`, `ToolRegistry`, `ToolExecutor`, `StrategyMixin`, and composition over harness-specific execution flags.
- The `feat/agent-abstractions` worktree contains an implemented `BaseTool`, `ToolRegistry`, `ToolExecutor`, `ReActStrategy`, prompt registry, built-in mock tools, and basic harness classes. That implementation should be reused if it lands before this feature.
- The `ai/resolve-sdk-pr-2-comments` worktree contains provider runners, prompt/API strategies, filesystem tools, and a smaller `StrategyMixin.run_with_strategy()`, but does not include a full dynamic tool registry.
- The user request assumes Pydantic is already a core dependency. The audit found `pyproject.toml` currently has `dependencies = []` on `main` and the inspected PR #2 worktree. This design intentionally adds Pydantic because schema extraction and robust runtime validation are core requirements for decorator-based tools.

---

## 4. Requirements

### Functional Requirements

1. `vidbyte_tool` must be importable as `from vidbyte import vidbyte_tool` and `from vidbyte.tools import vidbyte_tool`.
2. Decorating a function must return a `FunctionTool` object that implements `BaseTool`.
3. The original wrapped callable must remain accessible for debugging and metadata through `FunctionTool.func`.
4. The default tool name must be the function name.
5. Users must be able to override tool name and description through `@vidbyte_tool(name=..., description=...)`.
6. The tool description must default to the first paragraph of the function docstring.
7. The decorator must inspect function parameters, type hints, defaults, and keyword-only parameters.
8. The decorator must reject unsupported signatures such as `*args` and `**kwargs` unless explicitly handled later.
9. The decorator must generate a Pydantic model for the function arguments.
10. The decorator must expose JSON Schema from the generated Pydantic model.
11. Missing required arguments, wrong types, and invalid values must be rejected before calling user code.
12. Sync functions must be executable from the async `BaseTool.execute()` path.
13. Async functions must be awaited directly.
14. Return values must be converted to `ToolResult`; strings should remain strings and other objects should be JSON-serialized when possible with a string fallback.
15. User exceptions must be caught by `ToolExecutor` and returned as structured error results.
16. `ToolRegistry.__init__()` must accept an optional `tools` iterable.
17. `ToolRegistry.register()` must accept `BaseTool`, `FunctionTool`, decorated functions, and raw callables.
18. Raw callable registration must auto-wrap the function with `FunctionTool`.
19. Duplicate tool names must raise or return a clear registry error rather than silently overwriting.
20. `ToolsClient.register()` and `ToolsClient.with_tools()` must provide convenient namespace-level registration.
21. `ToolMixin.with_tools()` must attach tools to an instance-local registry and return `self`.
22. `ToolMixin.tool_registry` must expose the instance-local registry.
23. `ToolMixin.tool_executor` must execute against the instance-local registry.
24. Harnesses that inherit `ToolMixin` must pass attached tools to their active strategy immediately before strategy execution.
25. Tool-using strategies such as ReAct and future CodeAct must inherit `ToolMixin` or accept a registry compatible with it.
26. Provider-facing runners or adapters must be able to read tool JSON Schemas for function-calling APIs without owning execution.
27. Tests must cover decorator schema generation, validation, execution, registry registration, and harness-to-strategy cascade.

### Non-Functional Requirements

- Security: validation must happen before user function invocation.
- Security: validation errors must not leak secrets or raw large payloads.
- Reliability: invalid decorated functions must fail at decoration or registration time with clear errors.
- Compatibility: Python `>=3.11`.
- Maintainability: public exports must use explicit `__all__`.
- Ergonomics: the common path should be one decorator and one `.with_tools([...])` call.
- Observability: `ToolResult.metadata` should identify the wrapped function module, sync/async mode, and validation model name without exposing sensitive arguments by default.
- Performance: Pydantic models are created once per decorated function, not per call.
- Thread safety: registry mutation should follow the locking behavior of the existing planned registry.

---

## 5. High-Level Design

The feature adds a function-to-tool adapter layer under `vidbyte.tools.decorators` and `vidbyte.tools.function_tool`. A decorated function becomes a `FunctionTool`, which is a normal SDK `BaseTool` backed by an inspected Python callable and a generated Pydantic argument model.

```text
User function
  -> @vidbyte_tool
  -> FunctionTool(BaseTool)
       |-- ToolSpec(name, description, parameters, input_schema)
       |-- Pydantic args model
       `-- execute(ToolCall) -> validate -> call func -> ToolResult

Harness.with_tools([...])
  -> ToolMixin local ToolRegistry
  -> run/execute cascade into attached strategy
  -> ReAct/CodeAct ToolExecutor
  -> user's function
```

`ToolRegistry` becomes the single normalization boundary. Any API that accepts tools can pass objects to `ToolRegistry.register_many()`, and the registry converts them to `BaseTool` instances by using `ensure_tool()`.

The cascade rule is deliberately one-way: harnesses may inject tools into strategies, but strategies do not mutate harness registries. This preserves instance-local tool scopes and avoids global mutable tool state.

---

## 6. Detailed Design

### 6.1 Function Tool Decorator

**File(s):** `vidbyte/tools/decorators.py`, `vidbyte/tools/function_tool.py`
**Type:** New file

#### What it does

Defines `vidbyte_tool` and the `FunctionTool` adapter that converts Python callables into `BaseTool` instances.

#### Interface / API

```python
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar, overload

P = ParamSpec("P")
R = TypeVar("R")

@overload
def vidbyte_tool(func: Callable[P, R]) -> FunctionTool[P, R]: ...

@overload
def vidbyte_tool(
    *,
    name: str | None = None,
    description: str | None = None,
    permission: ToolPermission = ToolPermission.SAFE,
) -> Callable[[Callable[P, R]], FunctionTool[P, R]]: ...

class FunctionTool(BaseTool):
    func: Callable[..., Any]
    args_model: type[BaseModel]

    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
```

#### Logic / Algorithm

1. Accept either `@vidbyte_tool` or `@vidbyte_tool(...)`.
2. Read `inspect.signature(func)` and `typing.get_type_hints(func)`.
3. Reject `*args` and `**kwargs`.
4. Build a Pydantic model with `pydantic.create_model()`.
5. Treat parameters without defaults as required.
6. Parse the first docstring paragraph for the default description.
7. Build `ToolSpec` with both human-readable parameters and `input_schema`.
8. On execution, validate `call.arguments` through `args_model.model_validate()`.
9. Invoke async functions with `await func(**validated_args)`.
10. Invoke sync functions with `asyncio.to_thread(func, **validated_args)` by default to avoid blocking the event loop.
11. Normalize the return value into `ToolResult`.

#### Edge Cases & Error Handling

- Missing type hints are allowed but treated as `Any`, with a metadata warning.
- Positional-only parameters are rejected because tool calls are dictionary based.
- Pydantic `ValidationError` converts to a tool error result with concise field messages.
- Empty docstrings fall back to `ToolSpec.description = "Custom function tool."`.

---

### 6.2 Tool Spec Schema Support

**File(s):** `vidbyte/tools/types.py`
**Type:** New file or Modified

#### What it does

Extends the tool spec model so tools can expose provider-ready JSON Schema in addition to prompt-rendered parameters.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: tuple[ToolParameter, ...] = ()
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    permission: ToolPermission = ToolPermission.SAFE
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

#### Logic / Algorithm

1. Existing built-in tools can keep using `ToolParameter`.
2. `FunctionTool` supplies both `ToolParameter` entries and `input_schema`.
3. Provider adapters can prefer `input_schema` when translating to OpenAI, Anthropic, Gemini, or xAI function/tool schemas.
4. `ToolSpec.to_prompt_str()` remains backward-compatible.

#### Edge Cases & Error Handling

- If a tool does not provide `input_schema`, adapters may derive a minimal schema from `parameters`.
- Schema metadata is immutable from public access.

---

### 6.3 Tool Normalization Helpers

**File(s):** `vidbyte/tools/adapters.py`
**Type:** New file

#### What it does

Centralizes conversion of arbitrary tool-like objects into `BaseTool` instances.

#### Interface / API

```python
ToolInput = BaseTool | FunctionTool | Callable[..., Any]

def ensure_tool(tool: ToolInput) -> BaseTool: ...
def ensure_tools(tools: Iterable[ToolInput]) -> tuple[BaseTool, ...]: ...
```

#### Logic / Algorithm

1. If `tool` is already a `BaseTool`, return it.
2. If `tool` is a `FunctionTool`, return it.
3. If `tool` is callable, wrap it with `FunctionTool.from_function(tool)`.
4. Otherwise raise `TypeError`.

#### Edge Cases & Error Handling

- Decorated `FunctionTool` objects must not be double-wrapped.
- Bound methods are supported if their exposed signature has no unresolved `self`.

---

### 6.4 Registry Enhancements

**File(s):** `vidbyte/tools/registry.py`
**Type:** New file or Modified

#### What it does

Makes the registry the canonical place to accept custom functions and native tool classes.

#### Interface / API

```python
class ToolRegistry:
    def __init__(self, tools: Iterable[ToolInput] | None = None) -> None: ...
    def register(self, tool: ToolInput) -> ToolRegistry: ...
    def register_many(self, tools: Iterable[ToolInput]) -> ToolRegistry: ...
    def merge(self, other: ToolRegistry) -> ToolRegistry: ...
```

#### Logic / Algorithm

1. Initialize the registry lock and storage.
2. If `tools` is supplied, call `register_many()`.
3. Normalize each entry with `ensure_tool()`.
4. Reject duplicate names.
5. Return `self` for chaining.

#### Edge Cases & Error Handling

- Duplicate names raise `ToolRegistryError`.
- Bad callables fail during registration with the function name included.
- `merge()` copies tools into the receiver without mutating the source.

---

### 6.5 Tool Executor Validation

**File(s):** `vidbyte/tools/executor.py`
**Type:** New file or Modified

#### What it does

Ensures decorated function tools participate in the same execution path as built-in tools.

#### Interface / API

```python
class ToolExecutor:
    async def execute(self, raw: str) -> ToolResult: ...
    async def execute_call(self, call: ToolCall) -> ToolResult: ...
```

#### Logic / Algorithm

1. Parse `Action:` and `Action Input:` text into `ToolCall`.
2. Look up the tool in the active registry.
3. Call `tool.validate_call(call)` for lightweight spec checks.
4. Call `await tool.execute(call)`.
5. Catch user function exceptions and return structured error results.

#### Edge Cases & Error Handling

- Invalid JSON returns a parse error rather than empty arguments.
- Validation failures from Pydantic return field-level messages.
- Return serialization failures fall back to `str(value)`.

---

### 6.6 Tool Mixin

**File(s):** `vidbyte/tools/mixins.py`
**Type:** New file

#### What it does

Adds chainable tool attachment to any SDK object that needs an instance-local tool scope.

#### Interface / API

```python
class ToolMixin:
    def with_tools(self, tools: Iterable[ToolInput] | ToolInput) -> Self: ...

    @property
    def tool_registry(self) -> ToolRegistry: ...

    @property
    def tool_executor(self) -> ToolExecutor: ...
```

#### Logic / Algorithm

1. Lazily create `self._tool_registry`.
2. Lazily create `self._tool_executor` bound to that registry.
3. Normalize single tool inputs into a one-item list.
4. Register tools and return `self`.
5. Provide an internal `_copy_tools_to(target)` helper for harness-to-strategy cascade.

#### Edge Cases & Error Handling

- Multiple `with_tools()` calls append tools to the same instance registry.
- Duplicate names on the same instance fail clearly.
- Object instances do not share registries unless explicitly passed the same registry.

---

### 6.7 Harness Integration

**File(s):** `vidbyte/harnesses/base.py`, `vidbyte/harnesses/__init__.py`, `vidbyte/harnesses/client.py`
**Type:** New file or Modified

#### What it does

Gives base harnesses `with_tools()` and cascades tools into their active strategy before execution.

#### Interface / API

```python
class BaseHarness(StrategyMixin, ToolMixin):
    async def arun(self, prompt: str, *, runner: object | None = None, **options: object) -> Any:
        strategy = self._require_strategy()
        self._cascade_tools_to_strategy(strategy)
        return await maybe_await(strategy.arun_or_run(prompt, runner=runner, **options))
```

#### Logic / Algorithm

1. Harness owns its local tool registry.
2. Before `run()` or `arun()` delegates to a strategy, it checks whether tools exist.
3. If the strategy supports `with_tools()`, call it with the harness registry contents.
4. If the strategy does not support tools, ignore by default or fail when `require_tool_support=True`.

#### Edge Cases & Error Handling

- Non-tool strategies continue to run without tool injection unless strict mode is requested.
- Tool cascade should not re-register duplicates on repeated harness runs; it must track already-injected tool names or merge idempotently.

---

### 6.8 Strategy Integration

**File(s):** `vidbyte/strategies/base.py`, `vidbyte/strategies/react.py`, `vidbyte/strategies/codeact.py`, `vidbyte/strategies/__init__.py`
**Type:** New file or Modified

#### What it does

Makes tool-using strategies receive custom function tools through the same `ToolMixin` contract.

#### Interface / API

```python
class ReActStrategy(BaseStrategy, ToolMixin):
    async def arun(...):
        prompt_tools = self.tool_registry.specs_as_prompt_str()
        ...
        result = await self.tool_executor.execute(model_output)
```

#### Logic / Algorithm

1. ReAct renders active tool specs into its system prompt.
2. When the model emits an action block, ReAct uses the strategy-local executor.
3. CodeAct can follow the same pattern once sandbox design exists.
4. Strategy constructors may still accept a registry for explicit dependency injection.

#### Edge Cases & Error Handling

- Strategy-level tools override or merge with harness-level tools according to registry duplicate rules.
- If no tools exist, ReAct renders a no-tools instruction rather than crashing.

---

### 6.9 Provider Schema Integration

**File(s):** `vidbyte/providers/base.py`, `vidbyte/providers/openai.py`, `vidbyte/providers/anthropic.py`, `vidbyte/providers/gemini.py`, `vidbyte/providers/xai.py`
**Type:** New file or Modified

#### What it does

Allows provider adapters to translate Vidbyte tool specs into provider-native function/tool schemas without executing those tools.

#### Interface / API

```python
def tool_spec_to_provider_schema(spec: ToolSpec, provider: ModelProvider) -> Mapping[str, Any]: ...
```

#### Logic / Algorithm

1. Read `ToolSpec.input_schema`.
2. Convert to the provider's expected field names.
3. Keep execution local through `ToolExecutor`; providers only receive schemas and model instructions.

#### Edge Cases & Error Handling

- Providers with no function-calling support ignore schemas.
- Unsupported schema features should be stripped or rejected with clear errors.

---

### 6.10 Public Exports And Documentation

**File(s):** `vidbyte/__init__.py`, `vidbyte/tools/__init__.py`, `README.md`, `skills/vidbyte-sdk/SKILL.md`
**Type:** Modified

#### What it does

Makes the feature discoverable and documents the intended user path.

#### Interface / API

```python
from vidbyte import vidbyte_tool
from vidbyte.strategies import ReActStrategy

@vidbyte_tool
async def fetch_user_metrics(user_id: int, metric_type: str = "engagement") -> str:
    """Fetches real-time performance metrics for a specific user ID."""
    return f"Metrics for {user_id}: 94%"

evaluator = MyEvaluator().with_strategy(ReActStrategy()).with_tools([fetch_user_metrics])
```

#### Logic / Algorithm

1. Export `vidbyte_tool`, `FunctionTool`, `ToolMixin`, and registry helpers.
2. Add README examples for decorator use, registry use, and harness chaining.
3. Update SDK skill guidance to allow decorator-based custom tools after this approved design.

#### Edge Cases & Error Handling

- Documentation examples must not include real secrets or private endpoints.

---

## 7. Data Model Changes

### 7.1 Function Tool Runtime Model

**Change type:** New

```python
class FunctionTool(BaseTool):
    func: Callable[..., Any]
    args_model: type[pydantic.BaseModel]
    _spec: ToolSpec
```

**Migration strategy:** N/A - in-memory SDK wrapper type only.

### 7.2 Tool Spec Schema Fields

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: tuple[ToolParameter, ...]
    input_schema: Mapping[str, Any]
    permission: ToolPermission
    metadata: Mapping[str, Any]
```

**Migration strategy:** Existing tool specs can use default values for the new fields.

### 7.3 Registry Input Type

**Change type:** New

```python
ToolInput = BaseTool | FunctionTool | Callable[..., Any]
```

**Migration strategy:** N/A - type alias for accepted inputs.

---

## 8. API Changes

N/A - this SDK change does not add HTTP endpoints.

Python SDK public API additions:

```python
from vidbyte import vidbyte_tool
from vidbyte.tools import FunctionTool, ToolMixin, ToolRegistry, ensure_tool

registry = ToolRegistry(tools=[fetch_user_metrics])
registry.register(fetch_user_metrics)

harness.with_tools([fetch_user_metrics])
strategy.with_tools([fetch_user_metrics])
```

Modified Python SDK APIs:

```python
class ToolRegistry:
    def __init__(self, tools: Iterable[ToolInput] | None = None) -> None: ...
    def register(self, tool: ToolInput) -> ToolRegistry: ...

class ToolsClient:
    def register(self, tool: ToolInput) -> ToolsClient: ...
    def with_tools(self, tools: Iterable[ToolInput] | ToolInput) -> ToolsClient: ...
```

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/custom-function-tools.md` | Design doc for this feature |
| MODIFY | `pyproject.toml` | Add Pydantic runtime dependency |
| MODIFY | `README.md` | Document decorator, registry, and harness examples |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Update SDK structure guidance for approved custom function tools |
| MODIFY | `vidbyte/__init__.py` | Export `vidbyte_tool` and key tool APIs |
| MODIFY | `vidbyte/tools/__init__.py` | Export decorator, function tool, mixin, registry helpers, and types |
| MODIFY | `vidbyte/tools/client.py` | Add registry initialization, register helpers, and `with_tools()` convenience |
| CREATE | `vidbyte/tools/decorators.py` | Public `@vidbyte_tool` decorator |
| CREATE | `vidbyte/tools/function_tool.py` | `FunctionTool` callable adapter |
| CREATE | `vidbyte/tools/adapters.py` | `ensure_tool()` and `ensure_tools()` normalization helpers |
| CREATE | `vidbyte/tools/mixins.py` | Chainable `ToolMixin.with_tools()` and local registry/executor access |
| MODIFY | `vidbyte/tools/types.py` | Add JSON Schema, permission, metadata, and serialization support to tool specs/results |
| MODIFY | `vidbyte/tools/base.py` | Ensure `BaseTool` validation contract supports function tools |
| MODIFY | `vidbyte/tools/registry.py` | Accept raw functions and optional inline tool collections |
| MODIFY | `vidbyte/tools/executor.py` | Add `execute_call()`, stricter JSON parse errors, and validation result handling |
| MODIFY | `vidbyte/harnesses/__init__.py` | Export tool-aware base harness APIs |
| MODIFY | `vidbyte/harnesses/base.py` | Inherit `ToolMixin` and cascade tools to active strategies |
| MODIFY | `vidbyte/harnesses/client.py` | Expose helper constructors or base classes for tool-aware harnesses |
| MODIFY | `vidbyte/strategies/__init__.py` | Export tool-aware strategies when present |
| MODIFY | `vidbyte/strategies/base.py` | Document or inherit tool-aware strategy behavior where appropriate |
| MODIFY | `vidbyte/strategies/mixins.py` | Coordinate strategy and tool composition helpers |
| MODIFY | `vidbyte/strategies/react.py` | Use strategy-local tool registry/executor |
| CREATE | `vidbyte/strategies/codeact.py` | Placeholder tool-aware strategy integration point if CodeAct exists in the branch being implemented |
| MODIFY | `vidbyte/providers/base.py` | Add provider schema translation helper contract |
| MODIFY | `vidbyte/providers/openai.py` | Translate tool schemas for OpenAI-compatible calls when runner support exists |
| MODIFY | `vidbyte/providers/anthropic.py` | Translate tool schemas for Anthropic calls when runner support exists |
| MODIFY | `vidbyte/providers/gemini.py` | Translate tool schemas for Gemini calls when runner support exists |
| MODIFY | `vidbyte/providers/xai.py` | Translate tool schemas for xAI/OpenAI-compatible calls when runner support exists |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Export custom tool and registry errors |
| MODIFY | `vidbyte/lib/errors/base.py` | Add `ToolRegistrationError` and `ToolValidationError` |
| CREATE | `tests/test_custom_function_tools.py` | Decorator, schema, validation, sync/async execution, and result normalization tests |
| CREATE | `tests/test_tool_registry_custom_inputs.py` | Registry registration for decorated functions, raw callables, and duplicate errors |
| CREATE | `tests/test_tool_mixin.py` | Instance-local registries, chaining, duplicate behavior, and executor binding tests |
| CREATE | `tests/test_harness_tool_cascade.py` | Harness-level `.with_tools()` cascade into strategy execution tests |
| CREATE | `tests/test_provider_tool_schema_translation.py` | Provider schema conversion tests using generated function schemas |

Summary: 11 files created, 24 files modified, 0 files deleted.

---

## 10. Testing Plan

### Unit Tests

- `tests/test_custom_function_tools.py` -> verifies `@vidbyte_tool` with async functions, sync functions, docstrings, defaults, optional parameters, missing type hints, bad signatures, Pydantic validation errors, JSON Schema output, and return normalization.
- `tests/test_tool_registry_custom_inputs.py` -> verifies `ToolRegistry(tools=[...])`, `register()` with decorated functions, `register()` with raw callables, duplicate name rejection, and invalid object errors.
- `tests/test_tool_mixin.py` -> verifies `.with_tools()` chaining, single-tool and list inputs, local registry isolation between instances, executor binding, and duplicate handling.
- `tests/test_harness_tool_cascade.py` -> verifies a tool-aware harness passes tools into a ReAct-style fake strategy immediately before execution and does not duplicate tools across repeated runs.
- `tests/test_provider_tool_schema_translation.py` -> verifies generated schemas convert to OpenAI, Anthropic, Gemini, and xAI-compatible shapes through fake provider adapters.

### Integration Tests

- Use a fake ReAct strategy with `ToolMixin` and `ToolExecutor` to parse `Action: fetch_user_metrics` and execute a decorated async function.
- Use a fake harness inheriting `StrategyMixin` and `ToolMixin` to verify `.with_strategy(...).with_tools([...])` works as requested.
- No live provider calls, external APIs, or database access are required.

### Manual / QA Test Cases

1. Run `python -m compileall vidbyte`.
2. Run `python -m unittest discover -s tests`.
3. Define a local decorated async function, register it in `ToolRegistry(tools=[func])`, and confirm `registry.specs_as_prompt_str()` includes the docstring description.
4. Execute `Action: fetch_user_metrics` with `{"user_id": 42}` and confirm the wrapped function receives an integer.
5. Execute the same action with `{"user_id": "bad"}` and confirm the validation error is returned before function invocation.
6. Chain `MyEvaluator().with_strategy(ReActStrategy()).with_tools([fetch_user_metrics])` and confirm the strategy sees the tool spec.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib | Python >=3.11 | `inspect`, `typing`, `asyncio`, `json`, `dataclasses`, tests | Limited schema generation without Pydantic |
| Pydantic | `>=2,<3` | Runtime argument models, validation, and JSON Schema generation | Adds the SDK's first runtime dependency; must be accepted explicitly |

No external network service is required.

---

## 12. Rollout & Deployment

- This is a package-only SDK change; no deployed service is updated.
- This is additive for the current scaffold, but it adds a new runtime dependency on Pydantic.
- Rollout sequence:
  1. Commit this design doc first in the feature worktree.
  2. Add Pydantic to `pyproject.toml`.
  3. Implement function tool decorator and adapter.
  4. Extend tool spec/types, registry, and executor.
  5. Add `ToolMixin` and wire harness/strategy cascade.
  6. Add provider schema translation helpers where provider adapters exist.
  7. Add tests and README examples.
- Rollback is reverting the feature branch merge commit.
- If the `feat/agent-abstractions` or PR #2 branches land first, implementation should reuse their concrete `BaseTool`, `ToolRegistry`, `ToolExecutor`, `StrategyMixin`, and provider classes instead of duplicating them. Any API drift must be recorded as a design-doc deviation before PR creation.

---

## 13. Open Questions

- [ ] Is adding Pydantic `>=2,<3` acceptable, given the current audited `pyproject.toml` has no runtime dependencies?
- [ ] Should sync custom functions run in `asyncio.to_thread()` by default, or should users opt into threaded execution for predictability?
- [ ] Should duplicate tool names always raise, or should `with_tools(..., replace=True)` be added for overrides?
- [ ] Should `ToolMixin.with_tools()` accept registries directly, or only individual tools and callables?
- [ ] Should provider schema translation land in this PR, or should this PR expose `ToolSpec.input_schema` and leave provider adapter wiring to the provider-runner PR?
- [ ] Should decorated tools support Pydantic field metadata through `typing.Annotated` in the first implementation?

---

## 14. Alternatives Considered

### Alternative 1: Require users to subclass `BaseTool`

- What: Make every custom tool a class with `spec()` and `execute()`.
- Why rejected: It is too much ceremony for the requested use case. The decorator path lets a normal Python function become a tool instantly while still producing a native `BaseTool` object internally.

### Alternative 2: Use only `inspect` and stdlib validation

- What: Build simple validation from signatures and type hints without dependencies.
- Why rejected: The feature explicitly needs JSON Schema extraction and robust argument validation. Recreating Pydantic would be lower quality and harder to maintain.

### Alternative 3: Store tools in one global registry

- What: Use a singleton tool registry shared by every harness and strategy.
- Why rejected: Custom tools often carry environment-specific access. Instance-local registries prevent accidental cross-run leakage and make tests deterministic.

### Alternative 4: Let harnesses execute tools directly

- What: Harnesses parse action text and invoke tools themselves.
- Why rejected: Tool execution belongs in `ToolExecutor` and tool-using strategies. Harnesses should compose and pass tools down, not own agent-loop mechanics.

### Alternative 5: Provider-native function calling only

- What: Send schemas to providers and rely on provider tool-calling flows for everything.
- Why rejected: The SDK also needs local strategy loops like ReAct and CodeAct. Provider schemas are useful, but execution should remain under Vidbyte's registry/executor boundary.
