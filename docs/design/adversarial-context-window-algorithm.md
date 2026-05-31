# Design Doc: Adversarial Context Window Algorithm

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-31
**Last Updated:** 2026-05-31

---

## 1. Overview

This feature adds an `adversarial_reflection` context-window algorithm to the Vidbyte SDK. The algorithm keeps the main agent's normal system prompt, tools, and agentic loop intact, but every configured number of runtime iterations it runs an internal adversarial critic tool and injects the bounded critique into later context as a tool-like observation. This gives a single agent a scheduled adversarial pressure check without introducing a multi-agent debate strategy or exposing unsafe provider-level tool-result messages without matching provider tool calls.

---

## 2. Goals & Non-Goals

### Goals

- Add a public `AdversarialReflectionAlgorithm` configuration object.
- Add `ContextWindow.preset.adversarial_reflection` and string resolution through `ContextWindow.resolve_algorithm("adversarial_reflection")`.
- Add a runtime adapter that schedules adversarial critique after every `interval_iterations` normal agent-loop iterations.
- Inject each critique into the model-visible context window as a `ToolCallContext`, rendered like existing SDK tool-call context.
- Add a real SDK tool, `AdversarialAgentTool`, under `vidbyte/tools/`, capable of wrapping an adversarial agent or async critique callable.
- Add prompt assets under `vidbyte/prompts/prompts/adversarial_reflection/` for the adversarial system prompt and critique prompt.
- Preserve the normal agent runtime contracts for tools, permissions, middleware, tracing, provider formatting, and final `AgentResult` metadata.
- Add tests for public API wiring, prompt catalog loading, runtime scheduling, tool execution, context injection, validation, and failure handling.
- Update README usage documentation for the new algorithm and tool.

### Non-Goals

- Do not implement a two-agent debate strategy.
- Do not replace the main agent's system prompt after the critique step.
- Do not expose the adversarial tool as a normal model-callable tool by default.
- Do not append provider-native `"role": "tool"` messages unless a provider model actually requested a matching tool call.
- Do not add network calls, service-specific Vidbyte logic, or proprietary scoring logic.
- Do not change prompt override semantics to support file paths.
- Do not change the default `ContextWindow.preset.default` behavior.

---

## 3. Background & Context

- The README describes context-window algorithms as an `Agent` option through `algorithm=ContextWindow.preset.<name>`.
- `skills/vidbyte-sdk/adding-context-window-algorithms.md` requires a complete algorithm to include public config, preset registration, runtime dispatcher wiring, runtime implementation, prompt assets, tests, and docs.
- Existing runtime algorithms are `reflexion` and `multi_provider_agentic_grader`.
- `reflexion` is closest in behavior because it injects model-generated critique into later attempts, but it works at trial boundaries by calling `AgentRuntime._arun_once(...)`.
- This feature needs iteration-boundary scheduling inside a single direct runtime loop, so `AgentRuntime` needs a small algorithm-neutral hook rather than duplicating the whole tool loop in the new runtime adapter.
- Existing context rendering already includes `BaseContext.tool_calls` in `BaseContext.build_context_body()` as `Tool calls:\n<name>: args=... output=...`, which matches the desired tool-like context exposure.
- Existing `ToolsFormatter.format_tool_result(...)` emits provider-native tool-result messages. Those messages should not be used for scheduled critiques because provider APIs usually expect a preceding provider tool call with a matching ID.
- The SDK uses Python 3.11, dataclasses, `unittest`, enum-backed prompt assets, and package data configured in `pyproject.toml` to include prompt JSON and Markdown files.

---

## 4. Requirements

### Functional Requirements

1. Developers can select the feature with `algorithm=ContextWindow.preset.adversarial_reflection`.
2. Developers can customize cadence with `AdversarialReflectionAlgorithm(interval_iterations=n)`.
3. Developers can customize critique bounds with `max_critique_chars`.
4. Developers can limit scheduled critique count with `max_critiques`.
5. Developers can provide a custom `AdversarialAgentTool`.
6. When no custom tool is supplied, the runtime creates an internal `AdversarialAgentTool` backed by the same runner invocation path and prompt catalog.
7. The adversarial stage runs after each completed normal runtime iteration whose count is divisible by `interval_iterations`.
8. The adversarial stage is skipped after a final `isDone`, max-iteration stop, max-token stop, middleware abort, or any completed terminal result.
9. Each critique is appended to the future context window as a `ToolCallContext` with tool name `adversarial_critique`.
10. The injected critique is model-visible through `BaseAgentContext.tool_calls`, not through provider-native tool-role messages.
11. The main agent retains the original regular system prompt, ordinary tools, and agentic-loop prompt.
12. The adversarial tool is internal and scheduled by default, not exposed in the model-visible tool schema.
13. Prompt bodies are loaded from `vidbyte/prompts/prompts/adversarial_reflection/`.
14. Prompt enum members are available through `Prompts().get(Prompt.ADVERSARIAL_REFLECTION_...)`.
15. Direct prompt imports are exported through `vidbyte.prompts`.
16. Final `AgentResult.metadata` includes `context_window_algorithm: "adversarial_reflection"`.
17. Final metadata includes an `adversarial_reflection` object with interval, critique count, bounded critique texts, and checkpoint summaries.
18. Existing result metadata such as stop reason, iteration count, tool call count, tool calls, token usage, and middleware metadata is preserved.
19. Invalid numeric configuration values fail at construction time with `ConfigurationError`.
20. Empty prompt override strings fail at construction time with `ConfigurationError`.
21. Custom prompt templates must contain all required placeholders and fail at construction time otherwise.

### Non-Functional Requirements

- Performance: the feature adds at most one extra model/tool execution every `interval_iterations`; bounded critique text prevents unbounded context growth.
- Scalability: algorithm state is per-run and should not mutate agent defaults, global prompt registries, or shared tool catalogs.
- Security: the scheduled adversarial tool defaults to `ToolPermission.SAFE`; permission checks still run for custom tools.
- Observability: scheduled critique metadata must make the trace auditable without storing unbounded raw provider responses.
- Reliability / error tolerance: failed adversarial tool execution must not crash the normal run by default; it should inject a bounded error observation and continue unless middleware aborts the run.

---

## 5. High-Level Design

The implementation will add a new context-window algorithm named `adversarial_reflection`. The public configuration lives under `vidbyte/context/algorithms/`, the runtime adapter lives under `vidbyte/agents/algorithms/`, and the prompt assets live under `vidbyte/prompts/prompts/adversarial_reflection/`. The runtime adapter delegates normal model/tool execution to `AgentRuntime._arun_once(...)`, using a new algorithm-neutral iteration hook so it can run scheduled critique without copying the direct runtime loop.

The adversarial critique itself is represented as a real SDK tool, `AdversarialAgentTool`, under `vidbyte/tools/`. The tool can wrap a `BaseAgent` or an async critique callable. For the preset path, the runtime adapter builds a per-run internal tool backed by `AgentRuntime._invoke_with_middleware(...)` and the new prompt assets. For custom tool paths, the adapter executes the supplied tool through a runtime helper that applies permission checks, validation, tracing, and middleware.

The scheduled critique output is appended as a `ToolCallContext` to the current `BaseAgentContext.tool_calls`. Because `_build_iteration_call_options(...)` rebuilds the system/context string before every model call, the next normal iteration sees the adversarial critique in the context body under the existing "Tool calls" section. This avoids invalid provider message sequencing while preserving the user-facing mental model of "a tool just reported what is going wrong."

```text
Agent.run(...)
  -> AgentRuntime.arun(...)
     -> AgentRuntimeContextAlgorithms detects adversarial_reflection
        -> AdversarialReflectionRuntimeAlgorithm.arun(...)
           -> AgentRuntime._arun_once(..., iteration_hook=...)
              -> normal model/tool iteration
              -> every n iterations: scheduled AdversarialAgentTool call
              -> append critique as ToolCallContext into BaseAgentContext
              -> next model call sees critique in context body
```

---

## 6. Detailed Design

### 6.1 Public Algorithm Config

**File(s):** `vidbyte/context/algorithms/adversarial_reflection.py`
**Type:** New file

#### What it does

Defines the immutable public configuration for adversarial reflection, validates developer inputs, loads prompt defaults, renders critique prompts, and bounds critique text.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class AdversarialReflectionAlgorithm:
    interval_iterations: int = 3
    max_critiques: int | None = 3
    max_critique_chars: int = 2000
    adversarial_tool: AdversarialAgentTool | None = None
    adversarial_system_prompt: str | None = None
    adversarial_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def render_adversarial_prompt(self, *, task: str, trajectory: str, iteration_count: int, critique_count: int) -> str: ...
    def adversarial_system_prompt_text(self) -> str: ...
    def capture_critique(self, output: str) -> str: ...
    def should_run_critique(self, *, iteration_count: int, critique_count: int, terminal: bool) -> bool: ...
```

#### Logic / Algorithm

1. Validate `interval_iterations > 0`.
2. Validate `max_critiques is None or max_critiques >= 0`.
3. Validate `max_critique_chars > 0` and below a fixed safeguard limit.
4. Validate prompt override strings are non-empty when provided.
5. Validate `adversarial_prompt` contains `{task}`, `{trajectory}`, `{iteration_count}`, and `{critique_count}`.
6. Validate metadata keys are strings.
7. Render default prompts through `Prompts().get(...)`.
8. Strip and truncate critique output before storing or injecting it.
9. Return `False` from `should_run_critique(...)` when terminal, below interval, not divisible by interval, or critique budget is exhausted.

#### Edge Cases & Error Handling

- `interval_iterations=0` raises `ConfigurationError`.
- `max_critiques=0` is valid and disables scheduling.
- Empty critique output is converted into a short diagnostic message rather than injecting an empty string.
- Overlong critique output is truncated with a suffix that fits inside `max_critique_chars`.
- Missing prompt placeholders raise `ConfigurationError`.

### 6.2 Context Algorithm Dataclass Wiring

**File(s):** `vidbyte/context/algorithms/tool_results.py`, `vidbyte/context/algorithms/__init__.py`
**Type:** Modified

#### What it does

Adds `adversarial_reflection` as the third mutually exclusive runtime algorithm field on `ContextWindowAlgorithm` and exports the public config class.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class ContextWindowAlgorithm:
    name: str
    tool_result_admission: ToolResultAdmission = ToolResultAdmission.RAW
    max_tool_result_chars: int = 600
    reflexion: ReflexionAlgorithm | None = None
    multi_provider_agentic_grader: MultiProviderAgenticGraderAlgorithm | None = None
    adversarial_reflection: AdversarialReflectionAlgorithm | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

#### Logic / Algorithm

1. Import `AdversarialReflectionAlgorithm`.
2. Include `self.adversarial_reflection` in the "at most one runtime algorithm" validation.
3. Export the class from `vidbyte.context.algorithms`.

#### Edge Cases & Error Handling

- Configuring `reflexion` and `adversarial_reflection` together raises the same single-runtime-algorithm error.
- Tool-result admission presets continue to work without setting a runtime algorithm.

### 6.3 Preset Registration

**File(s):** `vidbyte/context/presets.py`
**Type:** Modified

#### What it does

Adds the public preset property used by `ContextWindow.preset.adversarial_reflection` and by string resolution.

#### Interface / API

```python
@property
def adversarial_reflection(self) -> ContextWindowAlgorithm: ...
```

#### Logic / Algorithm

1. Import `AdversarialReflectionAlgorithm`.
2. Add a property that returns `ContextWindowAlgorithm(name="adversarial_reflection", adversarial_reflection=AdversarialReflectionAlgorithm())`.
3. Rely on existing `getattr(preset_registry, algorithm)` string resolution.

#### Edge Cases & Error Handling

- Unknown names still raise `ValueError`.
- Existing preset names are unchanged.

### 6.4 Prompt Assets

**File(s):** `vidbyte/prompts/prompts/adversarial_reflection/adversarial_reflection.json`, `vidbyte/prompts/prompts/adversarial_reflection/adversarial_system_prompt.md`, `vidbyte/prompts/prompts/adversarial_reflection/adversarial_prompt.md`, `vidbyte/lib/enums/prompts.py`, `tests/test_prompts_interface.py`
**Type:** New files and modified files

#### What it does

Adds Markdown-backed prompt assets for the adversarial critique stage and enum keys for catalog lookup.

#### Interface / API

```python
class Prompt(str, Enum):
    ADVERSARIAL_REFLECTION_ADVERSARIAL_SYSTEM_PROMPT = "adversarial_reflection.adversarial_system_prompt"
    ADVERSARIAL_REFLECTION_ADVERSARIAL_PROMPT = "adversarial_reflection.adversarial_prompt"
```

#### Logic / Algorithm

1. Add JSON descriptor with `name`, `description`, `key`, and `prompts`.
2. Add two Markdown files.
3. Add two enum members.
4. Rely on `Prompts` dynamic import-name generation to expose `adversarial_reflection_adversarial_system_prompt` and `adversarial_reflection_adversarial_prompt`.
5. Add prompt tests that verify enum lookup and direct import equality.

#### Edge Cases & Error Handling

- Missing Markdown files should fail existing prompt catalog validation.
- Enum values without assets should fail existing prompt catalog validation.
- Prompt body must be non-empty.

### 6.5 Adversarial Agent Tool

**File(s):** `vidbyte/tools/adversarial_agent_tool.py`, `vidbyte/tools/__init__.py`, `vidbyte/__init__.py`
**Type:** New file and modified files

#### What it does

Defines a real SDK `BaseTool` that executes an adversarial critique through either a wrapped `BaseAgent` or an async critique callable. The context-window algorithm can schedule this tool internally, and developers can also instantiate it directly for custom algorithm configuration.

#### Interface / API

```python
CritiqueCallable = Callable[[Mapping[str, Any]], Awaitable[str] | str]

class AdversarialAgentTool(BaseTool):
    def __init__(self, *, agent: BaseAgent | None = None, critique: CritiqueCallable | None = None, name: str = "adversarial_critique", description: str | None = None, max_output_chars: int = 2000) -> None: ...
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
```

#### Logic / Algorithm

1. Validate that exactly one of `agent` or `critique` is provided.
2. Validate `name`, `description`, and `max_output_chars`.
3. Expose a `SAFE` tool spec with required parameters `task`, `trajectory`, `iteration_count`, and `critique_count`.
4. When wrapping an agent, serialize the adversarial request and call `agent.fork().generate_reply(...)`.
5. When wrapping a callable, call it with a mapping of validated call arguments.
6. Bound output before returning `ToolResult.success(...)`.
7. Return `ToolResult.error(...)` for execution failures.

#### Edge Cases & Error Handling

- Missing required parameters use existing `BaseTool.validate_call(...)`.
- Non-string callable output is converted to string before bounding.
- Callable exceptions are caught and returned as `ToolResult.error(...)`.
- Empty critique output returns an error result rather than a blank success.

### 6.6 AgentRuntime Iteration Hook

**File(s):** `vidbyte/agents/runtime.py`, `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified

#### What it does

Adds an algorithm-neutral hook to `_arun_once(...)` so context-window algorithms can observe completed iterations and return context updates without duplicating the direct runtime loop.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class AgentRuntimeIterationState:
    message: str
    context: BaseAgentContext
    provider: str
    iteration_count: int
    model_call_count: int
    tool_call_count: int
    tokens_used: int | None
    call_contexts: tuple[ToolCallContext, ...]
    model_response: object | None = None

@dataclass(frozen=True, slots=True)
class AgentRuntimeIterationUpdate:
    context: BaseAgentContext | None = None
    tool_contexts: tuple[ToolCallContext, ...] = ()

async def _arun_once(..., iteration_hook: AgentRuntimeIterationHook | None = None) -> AgentResult: ...
async def execute_scheduled_tool_call(...): ...
```

#### Logic / Algorithm

1. Keep existing `_arun_once(...)` behavior unchanged when no hook is supplied.
2. After a normal iteration completes and after normal `after_iteration` middleware succeeds, call the hook with a snapshot of runtime state.
3. If the hook returns an updated context, reassign the local `context` before the next model call.
4. If the hook returns scheduled `ToolCallContext` objects, append them to local `call_contexts` so metadata remains auditable.
5. Add `execute_scheduled_tool_call(...)` to run a passed `BaseTool` with permission checks, validation, tracing, and before/after tool middleware.
6. Do not append scheduled tool output to provider-native `messages`; it is exposed through the rebuilt context system string on the next iteration.

#### Edge Cases & Error Handling

- Hook exceptions are converted into an `AgentResult` with `AgentStopReason.ERROR` only if not handled by the algorithm.
- Hook returns `None` means continue with no context change.
- Scheduled tool failures produce `ToolCallContext(state=FAILED)` and a bounded error output.
- Middleware abort during scheduled tool execution stops the run through a normal `AgentResult`.

### 6.7 Runtime Algorithm Adapter

**File(s):** `vidbyte/agents/algorithms/adversarial_reflection.py`, `vidbyte/agents/algorithms/__init__.py`, `vidbyte/agents/context_algorithms.py`
**Type:** New file and modified files

#### What it does

Implements the actual scheduled adversarial critique runtime and wires it into the context algorithm dispatcher.

#### Interface / API

```python
class AdversarialReflectionRuntimeAlgorithm:
    name = "adversarial_reflection"
    def __init__(self, runtime: AgentRuntime, algorithm: AdversarialReflectionAlgorithm) -> None: ...
    async def arun(self, message: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], runner_output_metadata: Callable[[object], Mapping[str, Any]], metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult: ...
```

#### Logic / Algorithm

1. Initialize per-run critique state.
2. Build an iteration hook that checks `algorithm.should_run_critique(...)`.
3. Render a bounded trajectory string from task, current context, current tool-call contexts, and latest model output.
4. Resolve the scheduled tool: use `algorithm.adversarial_tool` if provided; otherwise create an internal `AdversarialAgentTool` backed by `runtime._invoke_with_middleware(...)`.
5. Execute the scheduled tool through `runtime.execute_scheduled_tool_call(...)`.
6. Capture and bound the critique result.
7. Append the critique as a `ToolCallContext` to a replaced `BaseAgentContext`.
8. Return the context update to `_arun_once(...)`.
9. Attach final `adversarial_reflection` metadata to the returned `AgentResult`.

#### Edge Cases & Error Handling

- No critique runs when `max_critiques=0`.
- No critique runs after terminal result.
- If an adversarial tool returns error, the error is injected as a diagnostic observation and recorded in metadata.
- Empty or whitespace-only trajectory still renders a valid prompt.
- Existing metadata is preserved when algorithm metadata is added.

### 6.8 Public Exports

**File(s):** `vidbyte/context/__init__.py`, `vidbyte/tools/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Exposes `AdversarialReflectionAlgorithm` and `AdversarialAgentTool` from stable public import surfaces.

#### Interface / API

```python
from vidbyte import AdversarialReflectionAlgorithm, AdversarialAgentTool
from vidbyte.context import AdversarialReflectionAlgorithm
from vidbyte.tools import AdversarialAgentTool
```

#### Logic / Algorithm

1. Import the new classes.
2. Add names to `__all__`.
3. Preserve existing exports.

#### Edge Cases & Error Handling

- Importing `vidbyte` should not construct model clients or run prompt loading beyond existing behavior.
- Existing public imports continue to work.

### 6.9 Documentation

**File(s):** `README.md`
**Type:** Modified

#### What it does

Adds a short usage example under Context Management showing the preset and optional custom tool construction.

#### Interface / API

```python
from vidbyte import AdversarialAgentTool, AdversarialReflectionAlgorithm, ContextWindow, ContextWindowAlgorithm
```

#### Logic / Algorithm

1. Document simple preset usage.
2. Document custom interval usage.
3. Document custom `AdversarialAgentTool` usage.
4. Explain that scheduled critique is internal by default and injected as tool-like context.

#### Edge Cases & Error Handling

- README should avoid promising multi-agent debate behavior.
- README should state that raw provider tool messages are not appended without matching provider tool calls.

---

## 7. Data Model Changes

### 7.1 `AdversarialReflectionAlgorithm`

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class AdversarialReflectionAlgorithm:
    interval_iterations: int
    max_critiques: int | None
    max_critique_chars: int
    adversarial_tool: AdversarialAgentTool | None
    adversarial_system_prompt: str | None
    adversarial_prompt: str | None
    metadata: Mapping[str, Any]
```

**Migration strategy:** N/A - additive SDK data type, no persistent storage.

### 7.2 `ContextWindowAlgorithm`

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class ContextWindowAlgorithm:
    adversarial_reflection: AdversarialReflectionAlgorithm | None = None
```

**Migration strategy:** N/A - additive optional field with default `None`.

### 7.3 Runtime Iteration Hook Dataclasses

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class AgentRuntimeIterationState: ...

@dataclass(frozen=True, slots=True)
class AgentRuntimeIterationUpdate: ...
```

**Migration strategy:** N/A - internal additive runtime contracts.

### 7.4 Prompt Enum Members

**Change type:** Modified

```python
ADVERSARIAL_REFLECTION_ADVERSARIAL_SYSTEM_PROMPT = "adversarial_reflection.adversarial_system_prompt"
ADVERSARIAL_REFLECTION_ADVERSARIAL_PROMPT = "adversarial_reflection.adversarial_prompt"
```

**Migration strategy:** N/A - additive enum values with matching assets.

---

## 8. API Changes

### 8.1 Public Python SDK Imports

**Change type:** New

**Request:**

```python
from vidbyte import AdversarialAgentTool, AdversarialReflectionAlgorithm, ContextWindow
```

**Response:**

```python
algorithm = ContextWindow.preset.adversarial_reflection
custom = AdversarialReflectionAlgorithm(interval_iterations=2)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Python SDK raises `ConfigurationError` for invalid algorithm or tool configuration. |

### 8.2 Prompt Catalog API

**Change type:** Modified

**Request:**

```python
Prompts().get(Prompt.ADVERSARIAL_REFLECTION_ADVERSARIAL_PROMPT)
```

**Response:**

```json
{
  "value": "Markdown prompt text"
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Existing `Prompts().get()` raises `TypeError` for raw string keys. |
| N/A | Existing catalog validation raises `ConfigurationError` for missing assets. |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/adversarial-context-window-algorithm.md` | Design source of truth for the feature |
| CREATE | `vidbyte/context/algorithms/adversarial_reflection.py` | Public algorithm configuration |
| CREATE | `vidbyte/agents/algorithms/adversarial_reflection.py` | Runtime adapter for scheduled critique |
| CREATE | `vidbyte/tools/adversarial_agent_tool.py` | Real SDK tool for adversarial agent critique |
| CREATE | `vidbyte/prompts/prompts/adversarial_reflection/adversarial_reflection.json` | Prompt family descriptor |
| CREATE | `vidbyte/prompts/prompts/adversarial_reflection/adversarial_system_prompt.md` | Adversarial stage system prompt |
| CREATE | `vidbyte/prompts/prompts/adversarial_reflection/adversarial_prompt.md` | Adversarial critique prompt template |
| CREATE | `tests/test_adversarial_reflection_algorithm.py` | Public API and runtime behavior tests |
| CREATE | `tests/test_adversarial_agent_tool.py` | Tool behavior and validation tests |
| CREATE | `scripts/test-adversarial-context-window-algorithm.py` | Required verification script for all design test cases |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add internal iteration hook state/update dataclasses |
| MODIFY | `vidbyte/agents/runtime.py` | Add iteration hook and scheduled tool execution helper |
| MODIFY | `vidbyte/agents/context_algorithms.py` | Detect and dispatch adversarial reflection |
| MODIFY | `vidbyte/agents/algorithms/__init__.py` | Export runtime adapter |
| MODIFY | `vidbyte/context/algorithms/tool_results.py` | Add `adversarial_reflection` algorithm field |
| MODIFY | `vidbyte/context/algorithms/__init__.py` | Export public algorithm config |
| MODIFY | `vidbyte/context/presets.py` | Add preset |
| MODIFY | `vidbyte/context/__init__.py` | Export public algorithm config |
| MODIFY | `vidbyte/tools/__init__.py` | Export `AdversarialAgentTool` |
| MODIFY | `vidbyte/__init__.py` | Export root public API |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add prompt enum keys |
| MODIFY | `tests/test_prompts_interface.py` | Assert new prompt exports |
| MODIFY | `README.md` | Document usage |

---

## 10. Testing Plan

### Unit Tests

- `tests/test_adversarial_reflection_algorithm.py` -> `[Edge Case] test_preset_exposes_adversarial_reflection_algorithm`: verifies preset name, config instance, and string resolution.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Hidden Failure] test_context_window_algorithm_rejects_multiple_runtime_algorithms`: verifies `reflexion` plus `adversarial_reflection` raises.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Edge Case] test_algorithm_rejects_zero_interval`: verifies `ConfigurationError`.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Edge Case] test_algorithm_allows_zero_max_critiques`: verifies construction succeeds and scheduling is disabled.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Edge Case] test_algorithm_rejects_negative_max_critiques`: verifies `ConfigurationError`.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Edge Case] test_algorithm_rejects_zero_max_critique_chars`: verifies `ConfigurationError`.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Silent Failure] test_capture_critique_truncates_within_configured_bound`: verifies suffix accounting does not exceed the configured max.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Silent Failure] test_should_run_critique_uses_exact_interval_not_off_by_one`: verifies iteration 2 does not run for interval 3 and iteration 3 does.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Hidden Assumption] test_should_run_critique_skips_terminal_iteration`: verifies terminal flag suppresses scheduling.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Hidden Assumption] test_custom_prompt_requires_all_placeholders`: verifies missing placeholders fail at construction.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Hidden Assumption] test_metadata_keys_must_be_strings`: verifies non-string metadata keys fail.
- `tests/test_adversarial_agent_tool.py` -> `[Edge Case] test_tool_requires_exactly_one_executor`: verifies both missing and double executor configs fail.
- `tests/test_adversarial_agent_tool.py` -> `[Edge Case] test_tool_rejects_empty_name`: verifies invalid tool name fails.
- `tests/test_adversarial_agent_tool.py` -> `[Edge Case] test_tool_rejects_zero_max_output_chars`: verifies invalid bound fails.
- `tests/test_adversarial_agent_tool.py` -> `[Hidden Failure] test_tool_callable_exception_returns_error_result`: verifies exceptions become `ToolResult.error`.
- `tests/test_adversarial_agent_tool.py` -> `[Silent Failure] test_tool_bounds_callable_output`: verifies overlong callable output is truncated and status remains success.
- `tests/test_adversarial_agent_tool.py` -> `[Hidden Assumption] test_tool_rejects_empty_callable_output`: verifies blank critique does not become blank success.
- `tests/test_adversarial_agent_tool.py` -> `[Hidden Assumption] test_tool_spec_is_safe_and_internal_metadata_is_set`: verifies permission and metadata.
- `tests/test_prompts_interface.py` -> `[Hidden Failure] test_adversarial_reflection_prompts_are_markdown_backed`: verifies enum lookup returns Markdown text.
- `tests/test_prompts_interface.py` -> `[Silent Failure] test_adversarial_reflection_direct_imports_match_catalog`: verifies direct imports match `Prompts().get(...)`.

### Integration Tests

- `tests/test_adversarial_reflection_algorithm.py` -> `[Hidden Failure] test_dispatcher_detects_and_returns_adversarial_runtime`: verifies dispatcher detection and adapter return.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Hidden Failure] test_runtime_injects_scheduled_critique_into_later_context`: fake runner reaches iteration 3, scheduled critique runs, next model call sees `adversarial_critique` in `system`.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Silent Failure] test_runtime_does_not_emit_provider_tool_result_message_for_scheduled_critique`: fake runner call kwargs do not include scheduled provider-native tool-role messages.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Silent Failure] test_runtime_preserves_regular_system_prompt_and_agentic_loop`: verifies scheduled critique does not replace original system prompt.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Silent Failure] test_runtime_metadata_preserves_normal_runtime_fields`: verifies stop reason, iteration count, token usage, middleware metadata, and algorithm metadata all exist.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Edge Case] test_runtime_with_max_critiques_zero_never_calls_tool`: verifies no scheduled tool call.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Edge Case] test_runtime_with_interval_one_runs_after_first_nonterminal_iteration`: verifies smallest positive interval.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Hidden Failure] test_runtime_records_failed_adversarial_tool_and_continues`: custom tool returns error, normal loop continues, metadata records failure.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Hidden Failure] test_scheduled_tool_permission_denial_records_denied_context`: custom tool requiring denied permission produces denied `ToolCallContext`.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Hidden Assumption] test_runtime_does_not_mutate_original_context`: verifies original context object remains unchanged after scheduled injection.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Hidden Assumption] test_runtime_uses_fresh_options_per_iteration`: verifies options mutation does not leak scheduled critique into caller-provided options.
- `tests/test_adversarial_reflection_algorithm.py` -> `[Hidden Assumption] test_runtime_skips_critique_after_is_done`: verifies final iteration does not schedule a trailing critique.

External dependencies are mocked with fake runners, fake agents, and fake tools. No real provider calls are made.

### Manual / QA Test Cases

1. Given an agent configured with `ContextWindow.preset.adversarial_reflection`, when a fake runner loops for more than three iterations, then the fourth model call includes `adversarial_critique` in context body.
2. Given `AdversarialReflectionAlgorithm(interval_iterations=1, max_critiques=1)`, when the agent runs multiple iterations, then exactly one critique is injected.
3. Given a custom `AdversarialAgentTool`, when it returns a critique paragraph, then the normal agent sees that paragraph as tool-like context.
4. Given invalid constructor values, when the class is instantiated in a Python REPL, then `ConfigurationError` is raised before runtime execution.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python | `>=3.11` | SDK runtime | Existing project requirement |
| `pydantic` | `>=2,<3` | Existing SDK dependency | No new usage planned |
| Provider runners | Existing SDK runner abstraction | Optional adversarial critique execution | Tests must mock all calls |
| Prompt catalog | Existing `Prompts` and `Prompt` enum | Load adversarial prompt assets | Missing enum or asset fails catalog validation |

---

## 12. Rollout & Deployment

- Feature flags: none.
- Breaking change: no, all public API changes are additive.
- Migration path: existing agents continue to use `ContextWindow.preset.default` unless developers opt in.
- Deployment order: standard SDK package release after tests pass.
- Rollback procedure: remove the new preset and exports or configure agents back to existing presets. Since there is no persistence or migration, rollback is code-only.

---

## 13. Open Questions

- [ ] Should `AdversarialAgentTool` be exported from root `vidbyte` or only from `vidbyte.tools`? This design exports both for consistency with other primary public contracts.
- [ ] Should failed adversarial tool calls inject an error observation by default, or only record metadata? This design injects a bounded error observation so the main model knows critique failed.
- [ ] Should a future option expose the adversarial tool in the normal model-visible tool catalog? This design keeps it internal by default and does not add the option in this PR.
- [ ] Should `max_critiques` default to `3` or `None`? This design uses `3` to bound cost out of the box.

---

## 14. Alternatives Considered

### Alternative 1: Literal Provider Tool Result Messages

- What: Append scheduled critiques to provider `messages` using `ToolsFormatter.format_tool_result(...)`.
- Why rejected: Provider APIs often require a matching previous tool call ID. Scheduled critique is not requested by the model, so this risks malformed provider message sequences.

### Alternative 2: Replace The System Prompt Every N Iterations

- What: Temporarily replace the worker system prompt with an adversarial prompt, then restore it.
- Why rejected: The clarified requirement is to expose the adversarial output as tool-like context while preserving the regular system prompt and agentic loop.

### Alternative 3: Duplicate The Full Agent Runtime Loop In The Algorithm

- What: Copy `_arun_once(...)` into `AdversarialReflectionRuntimeAlgorithm` and add scheduling inline.
- Why rejected: This would drift from middleware, permission, tool parsing, tracing, and provider formatting behavior. A generic iteration hook keeps the runtime contract centralized.

### Alternative 4: Implement As A Strategy

- What: Build a strategy that calls the worker and critic as separate stages.
- Why rejected: The README and skill file define this behavior as a context-window algorithm attached through `ContextWindow.preset.<name>`, not a strategy or harness.

