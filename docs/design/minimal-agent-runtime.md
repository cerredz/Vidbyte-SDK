# Design Doc: Minimal Agent Runtime

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-23
**Last Updated:** 2026-05-23

---

## 1. Overview

This feature adds a minimal internal `AgentRuntime` class under `vidbyte/agents/` and moves direct agent loop responsibilities out of `BaseAgent`. The runtime will build the agent context window, enforce optional max-iteration and provider-reported max-token budgets, execute agent-local tools through the existing `Tools` catalog and `PermissionPolicy`, append tool results and assistant text back into the provider message context, and continue running until the model calls the internal `isDone` tool or a configured budget stops execution.

---

## 2. Goals & Non-Goals

### Goals

- Add a new internal `AgentRuntime` class in `vidbyte/agents/runtime.py`.
- Keep the developer-facing `Agent` / `BaseAgent` surface simple; developers do not directly instantiate or manage `AgentRuntime`.
- Move direct runner loop logic, tool-call execution, permission checks, and context-building orchestration out of `BaseAgent`.
- Support optional runtime budgets for `max_iterations` and `max_tokens`.
- If `max_iterations` and `max_tokens` are not provided, continue until the model calls the internal `isDone` tool.
- Preserve existing agent-local tool support from PR #23: `Tools`, `ToolCall`, `ToolCallContext`, `ToolCallState`, `ToolsFormatter`, and `PermissionPolicy`.
- Keep tool execution generic for any `BaseTool`, `@tool` function, raw callable normalized by `Tools`, or MCP-bridged tool.
- Add tool results back into the ordered provider message context so the next model call can reason from observations.
- Return structured runtime metadata to `AgentMessage.metadata`, including iteration count, provider-reported token usage when available, tool-call count, tool-call states, and stop reason.
- Keep strategies compatible: strategy-backed agents still receive tools and a built `BaseAgentContext`.
- Use the existing `vidbyte/agents/` package, not a new singular `vidbyte/agent/` package, because the repo convention is plural.

### Non-Goals

- No full public API redesign that removes `runner`/`runners` from `BaseAgent`; this PR may mark them as internal/advanced in docs, but compatibility stays.
- No implementation of compaction behavior in this first runtime PR. The runtime may define config fields for future compaction thresholds, but it will not call compaction tools yet.
- No persistent memory, checkpoints, replay storage, event streaming, tracing sinks, or harness callbacks.
- No dynamic model self-evaluation loop beyond interpreting provider-native tool calls versus final text.
- No broad rewrite of strategy classes such as `ReActStrategy`, `CodeActStrategy`, or multi-agent orchestration.
- No live provider tests or network calls.
- No new package dependencies.
- No deletion of compatibility classes such as `ConfiguredAgentRunner`, `ToolExecutor`, or `ToolRegistry`.

---

## 3. Background & Context

- The local checkout is `main` and is behind `origin/main` by three commits. `origin/main` includes PR #23, "Agent Tool API Consolidation", which added `Agent = BaseAgent`, `Tools`, `@tool`, provider-native tool-call parsing, direct tool loops in `BaseAgent`, and tests in `tests/test_agent_tool_loop.py`.
- The local working tree already has an unrelated untracked design doc, `docs/design/pipelines.md`. The implementation phase must create an isolated worktree after approval and should not disturb unrelated local files.
- The SDK is a Python `>=3.11` package using `setuptools`, standard library `unittest`, and one runtime dependency, `pydantic>=2,<3`.
- The source layout centralizes public SDK modules under `vidbyte/`, shared dataclasses under `vidbyte/lib/dataclasses/`, provider helpers under `vidbyte/lib/`, and agent actor code under `vidbyte/agents/`.
- Current `origin/main` `BaseAgent` owns too many responsibilities: agent identity, runner configuration, modality routing, MCP attachment, tool catalog normalization, permission policy, context building, direct runner invocation, provider-native tool loop execution, tool-call lifecycle context, result wrapping, and sync/async convenience APIs.
- PR #23 already placed provider-native direct tool execution in `BaseAgent._run_with_tools()` and `_execute_agent_tool_call()`. This feature extracts that logic into a focused runtime class while keeping the behavior minimal.
- Existing context contracts live in `vidbyte/lib/dataclasses/context.py`. `BaseAgentContext` is kept intentionally narrow for agent execution: system prompt, tools, history, budget, and file paths.
- Existing tool contracts live in `vidbyte/lib/dataclasses/tools.py`, including `ToolCall`, `ToolResult`, `ToolCallContext`, and `ToolCallState`.
- Existing permissions use `PermissionPolicy.check(spec, call)` and deny `WRITE` / `EXECUTE` by default unless the agent receives a more permissive policy.
- Existing provider tool formatting and parsing live in `vidbyte/lib/tools/formatter.py` through `ToolsFormatter.format_tools(...)`, `parse_tool_calls(...)`, and `format_tool_result(...)`.

---

## 4. Requirements

### Functional Requirements

1. `vidbyte/agents/runtime.py` must define an internal `AgentRuntime` class.
2. `AgentRuntime` must be constructed by `BaseAgent`; SDK users should not need to instantiate it directly.
3. `AgentRuntime` must accept the agent identity, system prompt, tools catalog, permission policy, runner invocation callable, context builder inputs, and runtime config needed for one run.
4. `AgentRuntime` must build the `BaseAgentContext` used by direct model execution.
5. `AgentRuntime` must preserve existing context merge behavior: explicit per-call history first, then `agent.history`; caller context metadata merged with agent metadata; tool-call contexts included in `BaseAgentContext.tool_calls`.
6. `AgentRuntime` must format agent tools into provider schemas using `Tools.provider_schemas(provider)`.
7. `AgentRuntime` must invoke the selected model runner repeatedly until the model calls the internal `isDone` tool.
8. `AgentRuntime` must execute every parsed tool call through the agent-local `Tools` catalog.
9. `AgentRuntime` must check `PermissionPolicy` before validation and execution.
10. Permission-denied tool calls must not call the tool body.
11. Unknown tools, validation failures, permission denials, and tool exceptions must become `ToolResult.error(...)` values and `ToolCallContext` records.
12. Successful tool calls must become `ToolCallContext(state=ToolCallState.SUCCEEDED)` records.
13. Failed tool calls must use `ToolCallState.FAILED`; denied calls must use `ToolCallState.DENIED`.
14. Every local tool result must be formatted through `ToolsFormatter.format_tool_result(...)` and appended to the ordered provider message list for the next model call.
15. If `max_iterations` is provided, the runtime must stop before exceeding that number of model-call iterations.
16. If `max_tokens` is provided, the runtime must stop when provider-reported token usage is greater than or equal to that limit.
17. If neither `max_iterations` nor `max_tokens` is provided, the runtime must not apply artificial hard iteration/token limits and should continue until `isDone` is called.
18. Token usage must come from provider response metadata or raw usage payloads; the runtime must not invent local cost estimates.
19. The runtime must expose a machine-readable stop reason in result metadata.
20. `BaseAgent.generate_reply()` must delegate direct no-strategy execution to `AgentRuntime`.
21. Strategy-backed execution must remain compatible and continue to call `strategy.arun(..., runner=runner, context=agent_context, tools=agent_tools, ...)`.
22. Existing public `Agent`, `BaseAgent`, `Tools`, `tool`, and tool-call tests from PR #23 must continue to pass.
23. `BaseAgent` should keep `arun()` and `run()` aliases unchanged.
24. The runtime must return enough data for `BaseAgent` to append the final `AgentMessage` to history.
25. The runtime must not silently grant permissions beyond the configured `PermissionPolicy`.

### Non-Functional Requirements

- Maintainability: `BaseAgent` should become thinner by delegating direct execution details to `AgentRuntime`.
- Compatibility: existing tests and imports on `origin/main` should keep working.
- Security: default permission policy continues to deny `WRITE` and `EXECUTE` tools.
- Reliability: runtime budget stops should return a controlled `StrategyResult` rather than raising for normal budget exhaustion.
- Reliability: malformed provider tool-call payloads should follow existing `ToolsFormatter` behavior; this feature does not broaden parsing.
- Observability: final reply metadata must include at least `stop_reason`, `iteration_count`, `tokens_used`, `tool_call_count`, and `tool_call_states`.
- Performance: tool lookup remains dictionary-backed through `Tools._get(...)`; token usage extraction must be O(size of provider metadata/raw usage payloads).
- Testability: all runtime behavior must be tested with fake runners and fake tools; no live provider calls.
- Dependency control: no new third-party packages.

---

## 5. High-Level Design

The feature introduces `AgentRuntime` as the internal execution layer for direct, no-strategy agent runs. `BaseAgent` remains the developer-facing actor that owns identity, public construction, MCP attachment, tool catalog membership, modality selection, and history. When the agent needs to execute, it creates or uses an `AgentRuntime` to build context, call the selected runner, parse tool calls, execute tools, append tool observations, track budgets, and return a normalized `StrategyResult`.

The first version keeps the runtime deliberately small. It does not introduce a full policy stack, event bus, checkpoint store, verifier, or compaction engine. It only formalizes the loop that PR #23 already embedded inside `BaseAgent`: model call -> parse tool calls -> permission/validation/execution -> add tool results to messages -> repeat. The main new behavior is tracking `max_iterations` and `max_tokens` in one place and returning a clear stop reason.

The runtime owns context-window building for direct execution. `BaseAgent` will either move `_build_context(...)` into runtime or delegate to runtime through a small context input object. This keeps the runtime responsible for ordered context assembly while still letting strategy execution receive a compatible `BaseAgentContext`.

```text
Developer code
    |
    v
Agent / BaseAgent
    |  owns name, system prompt, tools, permission policy, history, MCP, modality
    |
    v
AgentRuntime
    |-- builds BaseAgentContext
    |-- formats tool schemas
    |-- calls internal model runner
    |-- parses provider tool calls
    |-- checks permissions
    |-- executes tools
    |-- appends tool results to provider messages
    |-- checks max_iterations / max_tokens
    v
StrategyResult -> AgentMessage
```

Key design decision: use the existing plural package `vidbyte/agents/`. The user asked for `vidbyte/agent`, but the repository already has `vidbyte/agents/base.py`, `vidbyte/agents/types.py`, `vidbyte/agents/registry.py`, and public exports from `vidbyte.agents`; adding a singular sibling package would split ownership and confuse imports.

---

## 6. Detailed Design

### 6.1 Agent Runtime Dataclasses

**File(s):** `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified

#### What it does

Adds minimal runtime-specific data contracts beside existing agent dataclasses. These contracts are internal-friendly but can be re-exported later if needed.

#### Interface / API

```python
class AgentStopReason(str, Enum):
    FINAL_RESPONSE = "final_response"
    MAX_ITERATIONS = "max_iterations"
    MAX_TOKENS = "max_tokens"
    TOOL_LOOP_LIMIT = "tool_loop_limit"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class AgentRuntimeConfig:
    max_iterations: int | None = None
    max_tokens: int | None = None
    compaction_trigger_tokens: int | None = None
    compaction_target_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class AgentRuntimeStats:
    iteration_count: int = 0
    tokens_used: int | None = None
    tool_call_count: int = 0
    stop_reason: AgentStopReason = AgentStopReason.FINAL_RESPONSE
```

#### Logic / Algorithm

1. Add `AgentStopReason` enum for runtime stop metadata.
2. Add `AgentRuntimeConfig` with optional `max_iterations`, `max_tokens`, and placeholder compaction thresholds.
3. Validate numeric config values in `__post_init__`: if provided, they must be greater than zero.
4. Add `AgentRuntimeStats` as the final metadata carrier for run accounting.
5. Re-export new types from `vidbyte/lib/dataclasses/__init__.py` if the repo's existing export pattern requires it.

#### Edge Cases & Error Handling

- `None` values mean unbounded for that dimension.
- `0` or negative values raise `ValueError` at config construction.
- Compaction fields are accepted but unused in this minimal PR; they are included to reserve the config shape requested by the user without implementing compaction yet.

---

### 6.2 AgentRuntime

**File(s):** `vidbyte/agents/runtime.py`
**Type:** New file

#### What it does

Defines the internal execution engine for direct agent runs. It builds context windows, calls the selected model runner, handles provider-native tool calls, executes tools safely, tracks optional iteration/token budgets, and returns `StrategyResult`.

#### Interface / API

```python
class AgentRuntime:
    def __init__(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        tools: Tools,
        permission_policy: PermissionPolicy,
        config: AgentRuntimeConfig | None = None,
    ) -> None: ...

    def build_context(
        self,
        message: str,
        *,
        base_context: StrategyContext | None,
        history: Sequence[AgentMessage],
        agent_history: Sequence[AgentMessage],
        agent_metadata: Mapping[str, Any],
        existing_tool_calls: Sequence[ToolCallContext],
        input_metadata: Mapping[str, Any] | None = None,
        modality: ModelModality | None = None,
    ) -> BaseAgentContext: ...

    async def arun(
        self,
        message: str,
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[[object, str, Mapping[str, Any]], Awaitable[object]],
        runner_output_text: Callable[[object], str],
        runner_output_metadata: Callable[[object], Mapping[str, Any]],
        options: Mapping[str, Any] | None = None,
    ) -> StrategyResult: ...
```

The exact callable signature can be adjusted during implementation to match existing `BaseAgent._invoke_runner(...)` helpers, but the runtime should not duplicate modality routing or runner selection.

#### Logic / Algorithm

1. Initialize runtime with agent identity, system prompt, `Tools` catalog, `PermissionPolicy`, and optional `AgentRuntimeConfig`.
2. `build_context(...)` reproduces existing `BaseAgent._build_context(...)` behavior:
   - Merge explicit `history` followed by persisted `agent_history`.
   - Merge caller context metadata followed by agent metadata and input metadata.
   - Add modality to metadata and strategy metadata when provided.
   - Include existing tool-call contexts.
   - Preserve file paths, responses, budget, artifacts, memory, and permissions from incoming context.
3. `arun(...)` prepares provider-native tool schemas with `self.tools.provider_schemas(provider)`.
4. It initializes ordered provider messages from `options.get("messages", ())`.
5. It starts `iteration_count` at zero and `tokens_used` as unknown until provider usage is available.
6. Before every model call, it checks whether `max_iterations` or `max_tokens` has already been reached.
7. It invokes the selected runner through the supplied `invoke_runner` helper.
8. It increments iteration count after every model call.
9. It updates token usage from response metadata or raw provider usage payloads when present.
10. It parses provider-native tool calls through `ToolsFormatter.parse_tool_calls(raw_result, provider)`.
11. If no tool calls are returned, it appends the model text as assistant history and continues the loop.
12. If tool calls are returned, it executes each call through `_execute_tool_call(...)`.
13. It appends every formatted tool result to ordered provider messages using `ToolsFormatter.format_tool_result(...)`.
14. It repeats until `isDone` or budget stop.
15. Budget stops return a `StrategyResult` with a concise output such as `"Agent runtime stopped after reaching max_iterations."` or `"Agent runtime stopped after reaching max_tokens."`.

#### Edge Cases & Error Handling

- Unknown tool name: create `ToolResult.error(..., metadata={"error": "unknown_tool"})`, add failed context, append tool result message, continue.
- Permission denied: create denied context and error result; do not execute the tool body.
- Validation failure: create failed context and error result; do not execute the tool body.
- Tool exception: catch and convert to failed context and `ToolResult.error(...)`.
- Empty tools catalog: no provider schemas are sent; runtime performs one or more model calls only if the model somehow returns tool calls, which will become unknown-tool errors.
- Unbounded config: if both `max_iterations` and `max_tokens` are `None`, the runtime does not enforce hard loop limits. The model must eventually call `isDone`. This matches the user requirement but leaves infinite-loop risk as an explicit known risk.
- Token usage is unknown when providers do not return usage metadata; in that case `max_tokens` cannot be enforced for that response.

---

### 6.3 BaseAgent Integration

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Refactors `BaseAgent` so direct execution delegates to `AgentRuntime`. `BaseAgent` remains responsible for public construction, modality selection, MCP attachment, history, forking, runner selection, and final `AgentMessage` creation.

#### Interface / API

```python
class BaseAgent(McpAttachableMixin):
    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        strategy: BaseStrategy | None = None,
        runner: object | None = None,
        runners: Mapping[ModelModality | str, object] | None = None,
        tools: Sequence[object] | Tools = (),
        permission_policy: PermissionPolicy | None = None,
        max_iterations: int | None = None,
        max_tokens: int | None = None,
        compaction_trigger_tokens: int | None = None,
        compaction_target_tokens: int | None = None,
        # existing parameters remain
    ) -> None: ...
```

Existing `max_tool_rounds` from PR #23 should either:

- remain as a deprecated compatibility alias mapped to `max_iterations`, or
- remain but be implemented by `AgentRuntimeConfig.max_iterations`.

The implementation should prefer `max_iterations` as the new runtime name and keep `max_tool_rounds` only to avoid breaking existing tests and callers.

#### Logic / Algorithm

1. Add optional runtime config parameters to `BaseAgent.__init__`.
2. Construct `self.runtime_config = AgentRuntimeConfig(...)`.
3. Construct or lazily construct `AgentRuntime` with agent name, system prompt, tools catalog, permission policy, and runtime config.
4. Replace `_build_context(...)` body with delegation to `self._runtime.build_context(...)`, or keep a compatibility wrapper that calls the runtime.
5. Replace `_run_with_tools(...)` and `_execute_agent_tool_call(...)` logic with delegation to `self._runtime.arun(...)`.
6. Preserve `_invoke_runner(...)`, `_runner_output_text(...)`, `_runner_provider(...)`, `_runner_output_metadata(...)`, and modality routing helpers in `BaseAgent`.
7. Preserve strategy path behavior: build context through runtime, then call `strategy.arun(...)`.
8. Extend final `AgentMessage.metadata` with runtime metadata returned in `StrategyResult.metadata`.
9. Ensure `fork(...)` copies runtime config into the child agent.
10. Ensure `add_tool(...)` refreshes or recreates the runtime's tool catalog if the runtime is stored on the instance.

#### Edge Cases & Error Handling

- If `runner` is `None` and no strategy exists, keep raising `AgentExecutionError("Agent without a strategy requires a runner.")`.
- If the selected runner is still `ConfiguredAgentRunner`, keep raising the existing executable-runner error.
- If `AgentRuntimeConfig` validation fails, surface the error during `BaseAgent` construction.
- Existing `max_tool_rounds=1` tests should still map to one allowed tool-call/model loop boundary.

---

### 6.4 Agent Package Exports

**File(s):** `vidbyte/agents/__init__.py`
**Type:** Modified

#### What it does

Optionally exports the runtime config and stop reason if the project wants them available for testing or advanced internal imports. `AgentRuntime` itself should not be promoted in root `vidbyte.__all__` in this minimal PR unless tests require it.

#### Interface / API

```python
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig, AgentRuntimeStats, AgentStopReason

__all__ = [
    # existing exports
    "AgentRuntimeConfig",
    "AgentRuntimeStats",
    "AgentStopReason",
]
```

#### Logic / Algorithm

1. Add dataclass exports only if implementation tests import them through `vidbyte.agents`.
2. Do not add `AgentRuntime` to root `vidbyte` exports.
3. Keep `Agent = BaseAgent` unchanged.

#### Edge Cases & Error Handling

- If exposing these types is judged too public during implementation, tests can import from `vidbyte.lib.dataclasses.agents` instead and this file does not need modification.

---

### 6.5 Root Package Exports

**File(s):** `vidbyte/__init__.py`
**Type:** Modified

#### What it does

No root export is strictly required. If `AgentRuntimeConfig` becomes a public optional config type, root exports may include it for ergonomics. The preferred minimal approach is not to expose `AgentRuntime` at root.

#### Interface / API

```python
# Preferred minimal root behavior:
# no AgentRuntime root export
```

#### Logic / Algorithm

1. Avoid making internal runtime classes a top-level public API.
2. Only update root exports if tests or existing package export conventions require the new dataclasses.

#### Edge Cases & Error Handling

- Avoid import cycles: `vidbyte.__init__` already imports many agent and tool classes. Keep runtime implementation imports local or acyclic.

---

### 6.6 Tests

**File(s):** `tests/test_agent_runtime.py`, `tests/test_agent_tool_loop.py`, `tests/test_agent_base.py`
**Type:** New file, Modified

#### What it does

Adds focused tests for `AgentRuntime` and updates existing agent tool-loop expectations if metadata names change.

#### Interface / API

```python
class AgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_executes_tool_call_and_continues_to_final_response(self) -> None: ...
    async def test_runtime_stops_at_max_iterations(self) -> None: ...
    async def test_runtime_stops_at_max_tokens(self) -> None: ...
    async def test_runtime_denies_disallowed_tool_permission(self) -> None: ...
    async def test_runtime_builds_context_with_history_metadata_and_tool_calls(self) -> None: ...
```

#### Logic / Algorithm

1. Use fake runners returning canned OpenAI-style raw payloads.
2. Use decorated `@tool` functions and small `BaseTool` subclasses.
3. Assert tool results are appended to the second runner call's `messages`.
4. Assert permission-denied tools are not executed.
5. Assert runtime metadata includes stop reason, iteration count, provider-reported token usage, and tool states.
6. Keep existing PR #23 `tests/test_agent_tool_loop.py` behavior green.

#### Edge Cases & Error Handling

- Fake runners must not perform network calls.
- Token budget tests should use deterministic long prompt/response text rather than provider usage objects only.
- If `max_tool_rounds` remains as compatibility alias, keep or update the existing max-tool-round test to assert equivalent `max_iterations` behavior.

---

### 6.7 Documentation

**File(s):** `README.md`
**Type:** Modified

#### What it does

Documents the high-level agent behavior without teaching developers to instantiate `AgentRuntime`. Documentation should describe optional agent runtime budgets as agent configuration and keep the runtime class framed as internal.

#### Interface / API

```python
agent = Agent(
    name="worker",
    system_prompt="Use tools to complete the task.",
    tools=[lookup],
    max_iterations=8,
    max_tokens=16_000,
)
```

#### Logic / Algorithm

1. Update agent/tool section to say direct agents run in an internal loop when tools are present.
2. Mention optional `max_iterations` and `max_tokens`.
3. State that omitted budgets allow the agent to continue until it calls `isDone`.
4. Avoid documenting `AgentRuntime` construction.

#### Edge Cases & Error Handling

- Do not add examples with real API keys.
- Do not imply exact token counts when runtime uses estimation/fallbacks.

---

## 7. Data Model Changes

### 7.1 `AgentStopReason`

**Change type:** New

```python
class AgentStopReason(str, Enum):
    FINAL_RESPONSE = "final_response"
    MAX_ITERATIONS = "max_iterations"
    MAX_TOKENS = "max_tokens"
    TOOL_LOOP_LIMIT = "tool_loop_limit"
    ERROR = "error"
```

**Migration strategy:** N/A - in-memory SDK enum only.

- Forward migration: runtime result metadata uses `stop_reason.value`.
- Rollback plan: remove enum and return previous ad hoc metadata such as `tool_round_limit_reached`.

### 7.2 `AgentRuntimeConfig`

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class AgentRuntimeConfig:
    max_iterations: int | None = None
    max_tokens: int | None = None
    compaction_trigger_tokens: int | None = None
    compaction_target_tokens: int | None = None
```

**Migration strategy:** N/A - in-memory SDK dataclass only.

- Forward migration: `BaseAgent.__init__` builds this config from optional keyword arguments.
- Rollback plan: remove the config and restore `BaseAgent.max_tool_rounds`.

### 7.3 `AgentRuntimeStats`

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class AgentRuntimeStats:
    iteration_count: int = 0
    tokens_used: int | None = None
    tool_call_count: int = 0
    stop_reason: AgentStopReason = AgentStopReason.FINAL_RESPONSE
```

**Migration strategy:** N/A - in-memory SDK dataclass only.

- Forward migration: `AgentRuntime` uses this shape internally to construct metadata.
- Rollback plan: remove stats dataclass and inline metadata dictionary construction.

---

## 8. API Changes

N/A - this SDK change does not add HTTP endpoints.

### 8.1 Python SDK Agent Construction

**Change type:** Modified

**Request:**

```python
from vidbyte import Agent, tool

@tool
def lookup(topic: str) -> str:
    """Look up a topic."""
    return f"found:{topic}"

agent = Agent(
    name="worker",
    system_prompt="Use tools to complete the task.",
    tools=[lookup],
    max_iterations=8,
    max_tokens=16_000,
)
reply = await agent.arun("Find the answer.")
```

**Response:**

```python
AgentMessage(
    sender="worker",
    recipient="orchestrator",
    content="...",
    metadata={
        "strategy": "direct_runner",
        "stop_reason": "final_response",
        "iteration_count": 2,
        "tokens_used": 1234,
        "tool_call_count": 1,
        "tool_call_states": ("succeeded",),
    },
)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Missing executable runner without strategy raises `AgentExecutionError`. |
| N/A | Invalid runtime budget values raise `ValueError` during agent construction. |
| N/A | Tool permission denial returns tool error context and continues the loop. |
| N/A | Max-iteration or max-token exhaustion returns a controlled `AgentMessage` with stop metadata. |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/minimal-agent-runtime.md` | Design doc for this feature |
| CREATE | `vidbyte/agents/runtime.py` | New internal runtime loop, context builder, budget tracking, and tool execution owner |
| CREATE | `tests/test_agent_runtime.py` | Focused runtime unit tests |
| MODIFY | `vidbyte/agents/base.py` | Delegate direct execution and context building to `AgentRuntime`; add runtime budget config |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add `AgentRuntimeConfig`, `AgentRuntimeStats`, and `AgentStopReason` |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Re-export new agent runtime dataclasses if following existing export convention |
| MODIFY | `vidbyte/agents/__init__.py` | Optionally export runtime config/stat/stop dataclasses, but not `AgentRuntime` itself |
| MODIFY | `vidbyte/__init__.py` | Optional root dataclass exports only if required by package conventions |
| MODIFY | `tests/test_agent_tool_loop.py` | Preserve PR #23 behavior while adapting max-tool-round expectations to runtime stop metadata |
| MODIFY | `tests/test_agent_base.py` | Verify `BaseAgent` delegates context/runtime behavior without regressing strategy path |
| MODIFY | `README.md` | Document optional agent runtime budgets without exposing `AgentRuntime` construction |

Summary: 3 files created, 8 files modified, 0 files deleted.

---

## 10. Testing Plan

### Unit Tests

- `tests/test_agent_runtime.py` -> `test_runtime_builds_context_with_agent_history_and_metadata`: verifies context construction preserves system prompt, history ordering, metadata merge, modality metadata, and existing tool calls.
- `tests/test_agent_runtime.py` -> `test_runtime_executes_tool_call_and_continues_to_final_response`: fake runner returns one OpenAI Responses tool call and then final text; runtime executes local tool and passes formatted tool result in the next `messages`.
- `tests/test_agent_runtime.py` -> `test_runtime_denies_write_tool_by_default`: WRITE tool is requested, permission policy denies it, tool body is not called, and denied context is returned.
- `tests/test_agent_runtime.py` -> `test_runtime_records_unknown_tool_as_failed_context`: model requests missing tool; runtime creates failed context and sends error result back to model.
- `tests/test_agent_runtime.py` -> `test_runtime_stops_at_max_iterations`: repeated tool-call responses stop with `stop_reason=max_iterations`.
- `tests/test_agent_runtime.py` -> `test_runtime_stops_at_max_tokens_from_provider_usage`: provider usage metadata crosses the token limit and stops with `stop_reason=max_tokens`.
- `tests/test_agent_runtime.py` -> `test_runtime_without_limits_continues_until_is_done`: no max iteration/token config; fake runner returns multiple tool calls then calls `isDone`.
- `tests/test_agent_tool_loop.py` -> preserve existing PR #23 tests for agent-owned tool execution, permission denial, unknown tools, and strategy path tool passing.
- `tests/test_agent_base.py` -> preserve card, fork, direct no-tool runner, and strategy context behavior.

### Integration Tests

- Run the full standard library unittest suite: `python -m unittest discover -s tests`.
- Run compile verification: `python -m compileall vidbyte`.
- No live provider, MCP subprocess, remote sandbox, or network integration is required.

### Manual / QA Test Cases

1. Create an `Agent` with a fake runner and one `@tool`, no runtime budgets, and verify it loops through two tool calls before final answer.
2. Create an `Agent` with `max_iterations=1` and a fake runner that keeps requesting tools; verify reply metadata reports `max_iterations`.
3. Create an `Agent` with `max_tokens` lower than provider-reported usage; verify the runtime stops before unbounded looping.
4. Create a WRITE-permission tool with default permissions; verify it is denied and not executed.
5. Run `python -c "from vidbyte import Agent, tool; print(Agent, callable(tool))"` after implementation.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python | `>=3.11` | Runtime implementation, dataclasses, enums, unittest | Existing requirement |
| pydantic | `>=2,<3` | Existing function-tool validation | Existing dependency only |
| Provider APIs | N/A | Not used in tests | No live calls; fake runner payloads may miss provider edge cases |

No new dependencies or external services are introduced.

---

## 12. Rollout & Deployment

- This is a package-only SDK change.
- No feature flag is required.
- The change should be backward-compatible for existing `Agent` / `BaseAgent` usage.
- Rollout sequence:
  1. After approval, create an isolated worktree from updated `main`.
  2. Commit this design doc first.
  3. Add runtime dataclasses.
  4. Add `vidbyte/agents/runtime.py`.
  5. Refactor `BaseAgent` direct execution to delegate to runtime.
  6. Add runtime tests and update affected agent tests.
  7. Update README.
  8. Run compile and unittest verification.
- Rollback procedure:
  1. Revert the feature branch merge commit.
  2. Restore `BaseAgent` direct `_run_with_tools(...)` and `_execute_agent_tool_call(...)` behavior from PR #23.
  3. Remove `AgentRuntime` and runtime tests.
  4. Remove runtime budget docs.

---

## 13. Open Questions

- [ ] Should `max_tool_rounds` remain as a deprecated public alias for `max_iterations`, or should it stay independent for one release?
- [ ] Should `AgentRuntimeConfig` be exported from `vidbyte.agents`, or stay under `vidbyte.lib.dataclasses.agents` only?
- [ ] Should `max_tokens` count cumulative provider-reported total tokens or only the most recent response usage when providers differ?
- [ ] Should a no-limit runtime have any hidden emergency guard against infinite loops, or should it strictly follow the user's requirement to continue until `isDone`?
- [ ] Should compaction threshold fields be added now as inert config, or deferred until the first real compaction implementation?

---

## 14. Alternatives Considered

### Alternative 1: Keep Runtime Logic In `BaseAgent`

- What: Add max-iteration and max-token handling directly to current `BaseAgent._run_with_tools(...)`.
- Why rejected: `BaseAgent` is already bloated after PR #23. Adding budgets and context-window ownership there makes the class harder to reason about and conflicts with the user's goal of a separate loop/running layer.

### Alternative 2: Add A New `vidbyte/agent/` Package

- What: Create singular `vidbyte/agent/runtime.py` as requested literally.
- Why rejected: The repository convention is already `vidbyte/agents/` for agent actor code. A singular sibling package would split ownership and create confusing import paths.

### Alternative 3: Expose `AgentRuntime` As Public API

- What: Document `AgentRuntime` and let SDK users instantiate it directly.
- Why rejected: The user explicitly wants the runner/runtime layer to be internal. Developers should configure agents, not wire execution engines.

### Alternative 4: Implement Full Policy Stack Now

- What: Add agenda management, cancellation hooks, compaction policy, verifier policy, trace event streams, and harness callbacks in the first runtime PR.
- Why rejected: The user asked to start with a very minimal design. This PR should only extract the loop, budgets, context window building, permissions, and tool execution.

### Alternative 5: Require `max_iterations` By Default

- What: Always require a finite runtime iteration cap.
- Why rejected: The user explicitly wants omission of `max_iterations` and `max_tokens` to mean the model continues until the problem is solved. The design preserves that behavior while naming the infinite-loop risk.
