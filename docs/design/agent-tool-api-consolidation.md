# Design Doc: Agent Tool API Consolidation

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-23
**Last Updated:** 2026-05-23

---

## 1. Overview

This feature consolidates the Vidbyte SDK tool surface around agent-owned tools instead of user-managed registries and executors. Users will create or import tools, pass them directly into `BaseAgent` or the ergonomic `Agent` alias, and let the agent format tool schemas for the selected provider, detect model tool-call requests, execute the matching local tool, and preserve structured context about every tool call. The old `ToolRegistry` and `ToolExecutor` imports remain as compatibility shims, but README and public guidance move to `Tools(...)`, `@tool`, and `Agent(..., tools=[...])`.

---

## 2. Goals & Non-Goals

### Goals

- Rename the public decorator from `@vidbyte_tool` to `@tool`, while keeping `vidbyte_tool` as a backward-compatible alias.
- Add a public `Tools` class that describes available tools, their descriptions, and input schemas.
- Make `Tools` the preferred replacement for public `ToolRegistry` usage.
- Let users pass built-in tools, MCP bridged tools, `@tool` functions, raw Python callables, or `Tools` instances directly to agents.
- Move normal tool execution into the agent execution path instead of teaching users to instantiate `ToolExecutor`.
- Keep provider-specific tool schema conversion in `ToolsFormatter`, but extend it so the agent can format a full `Tools` catalog and parse provider-native tool-call payloads.
- Add structured tool-call context records for requested, denied, failed, and successful tool calls.
- Preserve existing tests and compatibility imports where reasonable so this is not a hard breaking change.
- Update README and SDK skill guidance so user-facing docs prefer agents/harnesses and do not promote concrete runner classes, `ToolRegistry`, or `ToolExecutor`.

### Non-Goals

- No removal of existing `BaseTool`, `FunctionTool`, `ToolSpec`, `ToolCall`, or `ToolResult` contracts.
- No removal of `ToolRegistry` or `ToolExecutor` source files in this PR; they remain compatibility surfaces.
- No full text/image/video modality routing implementation in this PR. The existing `docs/design/agent-modality-routing.md` covers that separate change.
- No live provider tests or real model calls.
- No new provider endpoints, billing behavior, credentials model, or remote service.
- No new persistent database, migrations, or configuration files.
- No UI for tool permissions or human approval.
- No broad rewrite of all strategies to become provider-native tool loops.

---

## 3. Background & Context

The current checkout is `main`, behind `origin/main` by three commits, with untracked design docs already present: `docs/design/agent-modality-routing.md` and `docs/design/prompt-description-enhancement.md`. The design-doc workflow requires pulling `main` after approval, so these untracked files may block Phase 3 if they overlap files from `origin/main`.

The repo is a Python `>=3.11` package using `setuptools` and one runtime dependency, `pydantic>=2,<3`. Tests use standard library `unittest`. The source layout keeps public SDK modules under `vidbyte/`, shared dataclasses under `vidbyte/lib/dataclasses/`, provider-neutral helpers under `vidbyte/lib/`, and public namespace clients under `vidbyte/*/client.py`.

The current tool surface has overlapping concepts:

- `vidbyte/tools/base.py` defines `BaseTool` and `ToolLike`.
- `vidbyte/tools/function_tool.py` adapts Python functions into `BaseTool` with Pydantic validation.
- `vidbyte/tools/decorators.py` exposes `vidbyte_tool`.
- `vidbyte/tools/registry.py` stores tools by name and renders specs.
- `vidbyte/tools/executor.py` performs lookup, permission checks, validation, and old `Action:` text parsing.
- `vidbyte/tools/client.py` exposes `sdk.tools.registry`, `sdk.tools.executor`, and `sdk.tools.register(...)`.
- `vidbyte/lib/tools/formatter.py` converts one `ToolSpec` to OpenAI, Anthropic, Grok/xAI, or Gemini schema shapes and parses single provider tool-call objects.
- `BaseAgent` accepts `tools` but mostly passes them into strategies; it does not yet own a provider-native tool-call loop.
- MCP attachment currently mutates `agent.tools` as a list of bridged `BaseTool` instances.

Existing design docs conflict with the new desired direction. `advanced-tool-ecosystem.md` and current README teach registry/executor usage, while `skills/vidbyte-sdk/SKILL.md` also says tools are injected into agents or strategies and global mutable tool state should be avoided. This feature resolves the public mental model in favor of agent-local tools.

Provider adapters already accept tool schemas through `TextModelConfig.tools`. However, current normalized text runners return `TextModelResponse.text` and providers can fail when a response contains only tool-use blocks and no final text. This feature must make tool-call-only responses parseable in tests without requiring live API calls.

---

## 4. Requirements

### Functional Requirements

1. `from vidbyte import tool` and `from vidbyte.tools import tool` must import the new decorator.
2. `vidbyte_tool` must remain importable as a compatibility alias of `tool`.
3. `Tools(tools=[...])` must accept `BaseTool` instances, `FunctionTool` instances, decorated functions, raw Python callables, and nested `Tools` instances.
4. `Tools.specs()` must return all `ToolSpec` objects in deterministic insertion order.
5. `Tools.describe()` must return human-readable model/developer-facing tool instructions including descriptions and input schemas.
6. `Tools.provider_schemas(provider_or_model)` must use `ToolsFormatter` to produce provider-native tool declarations.
7. `Tools` must reject duplicate tool names unless an explicit replacement path is used internally for compatibility.
8. Public docs must not require users to call `ToolRegistry.register(...)` or instantiate `ToolExecutor`.
9. `ToolRegistry` must remain importable for existing code and tests, but should delegate to or wrap `Tools`.
10. `ToolExecutor` must remain importable for existing code and tests, but should be treated as compatibility infrastructure, not public guidance.
11. `BaseAgent.__init__()` must normalize its `tools` argument into a `Tools` catalog while preserving sequence-like access needed by existing MCP tests and agent cards.
12. `BaseAgent.add_tool()` must add a tool to the agent-local catalog and return `self`.
13. MCP attachment must add bridged tools through the agent-compatible tool path without relying on public registry usage.
14. Direct runner execution through `BaseAgent.generate_reply()` must pass provider-formatted tool schemas when tools exist and the selected runner supports tool arguments.
15. Agent strategy execution must continue passing tools into strategies for compatibility.
16. When a model response includes provider-native tool calls, the agent must parse them through `ToolsFormatter`, execute matching local tools under a permission policy, record context, and call the model again with tool results until a final answer or max round limit.
17. The agent tool loop must support a configurable `max_tool_rounds` defaulting to a small finite value.
18. Unknown tool names must return structured tool-call context and be sent back to the model as a tool error result rather than crashing the agent.
19. Permission denials must not call the tool body and must be recorded as denied tool-call context.
20. Validation errors must not call user tool functions and must be recorded as failed tool-call context.
21. Successful tool calls must record arguments, result, provider/model metadata when available, and call identifiers when the provider supplies them.
22. `ToolCallContext` records must be available on `BaseAgentContext.tool_calls` and in reply metadata.
23. `ToolsFormatter` must parse common OpenAI Responses, OpenAI-compatible chat, Anthropic, and Gemini tool-call shapes from canned raw provider payloads.
24. `ToolsFormatter` must format tool-result messages for the same provider families well enough for agent loop tests with fake runners.
25. `TextModelRunner.run()` must accept per-call tools, tool choice, messages, and metadata without requiring users to construct `TextModelConfig` directly.
26. Provider text adapters must not fail solely because a response contains tool calls and no final text.
27. README examples must teach `Agent(..., tools=[...])` or `BaseAgent(..., tools=[...])`, not direct runner construction.
28. `vidbyte.__all__` must include `tool`, `Tools`, and the existing compatibility names where retained.
29. Existing runner classes may remain importable from `vidbyte.lib.runners`, but user-facing docs must mark them internal/advanced.

### Non-Functional Requirements

- Compatibility: existing public imports for `ToolRegistry`, `ToolExecutor`, and `vidbyte_tool` should continue to work.
- Security: default permission policy must continue to deny `WRITE` and `EXECUTE` tools unless explicitly configured.
- Security: tool arguments may be stored in context, but metadata must avoid adding secrets beyond what callers already passed into the local process.
- Reliability: tool loops must have a max-round guard to prevent infinite model/tool recursion.
- Reliability: malformed provider tool-call payloads become structured failures instead of unhandled exceptions when possible.
- Testability: all provider tool-call behavior must be tested with fake runners and canned raw payloads; no live provider calls.
- Maintainability: dataclasses remain under `vidbyte/lib/dataclasses/`; package-local type modules re-export stable contracts.
- Performance: tool lookup must be dictionary-backed and deterministic; schema generation should reuse existing `ToolSpec` objects.
- Observability: final `AgentMessage.metadata` must include tool-call count and statuses.

---

## 5. High-Level Design

The public API becomes agent-local:

```python
from vidbyte import Agent, tool
from vidbyte.tools.builtins.code_search import GrepTool

@tool
def get_metric(user_id: int) -> dict[str, int]:
    """Fetch a metric for a user."""
    return {"user_id": user_id}

agent = Agent(
    name="analyst",
    system_prompt="Use tools when useful.",
    runner=my_runner,
    tools=[GrepTool(root_dir="."), get_metric],
)

reply = await agent.arun("Inspect the code.")
```

Internally, `BaseAgent` converts `tools=[...]` into a `Tools` catalog. The catalog is the model-facing and developer-facing description surface. It can render specs, descriptions, and provider schemas. The agent uses private lookup on that same catalog to execute model-requested tools, but users do not need to manage registration or execution objects.

```text
User code
  |
  v
Agent(..., tools=[built_in, @tool function, MCP tool])
  |
  v
Tools catalog
  |-- specs / describe / provider_schemas
  `-- private lookup for agent execution
  |
  v
BaseAgent.generate_reply()
  |-- ToolsFormatter formats provider schemas
  |-- runner returns text or raw tool calls
  |-- ToolsFormatter parses provider tool calls
  |-- agent validates / authorizes / executes local tool
  |-- ToolCallContext records each call
  `-- runner receives tool results and produces final answer
```

Compatibility classes stay in place. `ToolRegistry` becomes a thin compatibility wrapper around `Tools` with `register(...)`, `register_many(...)`, and `specs_as_prompt_str()` preserved. `ToolExecutor` stays available for old ReAct-style `Action:` parsing and existing tests, but new docs and agent code do not ask users to instantiate it.

The provider-native loop is deliberately bounded. It supports text model runners only in this PR, because image/video tool-calling is not established in the current SDK. The separate agent modality design can later route text/image/video runners behind the same public `Agent` API.

---

## 6. Detailed Design

### 6.1 Public Tool Decorator Rename

**File(s):** `vidbyte/tools/decorators.py`, `vidbyte/tools/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Adds `tool` as the preferred decorator name while preserving `vidbyte_tool`.

#### Interface / API

```python
from collections.abc import Callable
from typing import Any, overload

@overload
def tool(func: Callable[..., Any]) -> FunctionTool: ...

@overload
def tool(
    *,
    name: str | None = None,
    description: str | None = None,
    permission: ToolPermission = ToolPermission.SAFE,
) -> Callable[[Callable[..., Any]], FunctionTool]: ...

vidbyte_tool = tool
```

#### Logic / Algorithm

1. Move the current implementation body from `vidbyte_tool(...)` into `tool(...)`.
2. Assign `vidbyte_tool = tool` after the function definition.
3. Export both names from `vidbyte.tools` and root `vidbyte`.
4. Update docs and new tests to use `@tool`.

#### Edge Cases & Error Handling

- Existing decorated functions using `@vidbyte_tool` continue to return `FunctionTool`.
- Bad signatures still raise through existing `FunctionTool.from_function(...)` behavior.

---

### 6.2 `Tools` Catalog

**File(s):** `vidbyte/tools/catalog.py`, `vidbyte/tools/registry.py`, `vidbyte/tools/client.py`, `vidbyte/tools/__init__.py`
**Type:** New file, Modified

#### What it does

Defines the new public tool catalog and makes old registry usage delegate to it.

#### Interface / API

```python
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

class Tools(Sequence[BaseTool]):
    def __init__(self, tools: Iterable[ToolInput | "Tools"] | None = None) -> None: ...
    def specs(self) -> tuple[ToolSpec, ...]: ...
    def describe(self) -> str: ...
    def provider_schemas(self, provider_or_model: str) -> tuple[dict[str, Any], ...]: ...
    def all(self) -> tuple[BaseTool, ...]: ...
    def names(self) -> tuple[str, ...]: ...
    def add(self, tool: ToolInput, *, replace: bool = False) -> "Tools": ...
    def extend(self, tools: Iterable[ToolInput], *, replace: bool = False) -> "Tools": ...
    def _get(self, name: str) -> BaseTool: ...

class ToolRegistry:
    def register(self, tool: ToolInput, *, replace: bool = False) -> None: ...
    def register_many(self, tools: Iterable[ToolInput], *, replace: bool = False) -> None: ...
    def get(self, name: str) -> BaseTool: ...
    def specs_as_prompt_str(self) -> str: ...
```

#### Logic / Algorithm

1. `Tools.__init__()` flattens nested `Tools` instances and normalizes each item with `ensure_tool(...)`.
2. Store tools in insertion order and keep a private name dictionary.
3. Reject duplicates by default with `ToolRegistrationError`.
4. `add(...)` and `extend(...)` return new `Tools` instances so the preferred public catalog is immutable from the caller perspective.
5. `ToolRegistry` keeps mutable compatibility methods by replacing its internal catalog state.
6. `ToolsClient` exposes `catalog = Tools()` and compatibility `registry` / `executor` properties for older examples.

#### Edge Cases & Error Handling

- Duplicate tool names raise `ToolRegistrationError`.
- Invalid tool inputs raise `TypeError` from `ensure_tool(...)`.
- `Tools([]).describe()` returns a clear "No tools available." message.
- Compatibility `ToolRegistry.get(...)` keeps raising `ToolRegistryError` for missing tools.

---

### 6.3 Tool Context Dataclasses

**File(s):** `vidbyte/lib/dataclasses/tools.py`, `vidbyte/tools/types.py`, `vidbyte/lib/dataclasses/context.py`
**Type:** Modified

#### What it does

Adds structured context for agent-owned tool-call lifecycles.

#### Interface / API

```python
from dataclasses import dataclass, field
from typing import Any, Mapping

class ToolCallState(str, Enum):
    REQUESTED = "requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"

@dataclass(frozen=True, slots=True)
class ToolCallContext:
    tool_name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    state: ToolCallState = ToolCallState.REQUESTED
    call_id: str | None = None
    result: ToolResult | None = None
    provider: str | None = None
    model: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

#### Logic / Algorithm

1. Add `ToolCallState` and `ToolCallContext` beside the existing tool dataclasses.
2. Re-export them from `vidbyte.tools.types` and `vidbyte.tools`.
3. Update `BaseAgentContext.tool_calls` typing, if needed, to allow `ToolCallContext` while preserving tuple defaults.
4. Agent execution appends one final context object per attempted tool call.

#### Edge Cases & Error Handling

- Unknown tool calls are represented with `state=FAILED` and a `ToolResult.error(...)`.
- Permission denials are represented with `state=DENIED` and no tool body execution.
- Context objects are immutable to avoid accidental mutation across strategy/agent boundaries.

---

### 6.4 Tools Formatter Expansion

**File(s):** `vidbyte/lib/tools/formatter.py`, `vidbyte/providers/base.py`, `tests/test_provider_tool_schema_translation.py`
**Type:** Modified

#### What it does

Extends `ToolsFormatter` from single-spec schema conversion into the central agent helper for schema formatting, provider detection, tool-call parsing, and tool-result message formatting.

#### Interface / API

```python
class ToolsFormatter:
    @staticmethod
    def provider_from_model(provider_or_model: str | None) -> str: ...

    @staticmethod
    def format_tools(tools: Tools | Iterable[ToolSpec], provider_or_model: str) -> tuple[dict[str, Any], ...]: ...

    @staticmethod
    def parse_tool_calls(raw: object, provider_or_model: str) -> tuple[ToolCall, ...]: ...

    @staticmethod
    def format_tool_result(call: ToolCall, result: ToolResult, provider_or_model: str) -> Mapping[str, Any]: ...
```

#### Logic / Algorithm

1. Keep existing `to_openai_tool`, `to_anthropic_tool`, `to_grok_tool`, and `to_gemini_tool`.
2. Prefer `ToolSpec.input_schema` when present; fall back to `_parameters_schema(...)`.
3. Infer provider family from explicit provider strings or common model/provider prefixes.
4. Parse OpenAI Responses `output` items with `type == "function_call"`.
5. Parse OpenAI-compatible chat `choices[0].message.tool_calls`.
6. Parse Anthropic `content` blocks with `type == "tool_use"`.
7. Parse Gemini content parts containing `functionCall` or `function_call`.
8. Preserve provider call ids in `ToolCall.metadata` if `ToolCall` is extended, or in `ToolCallContext` if `ToolCall` remains minimal.
9. Format tool results into provider-specific message dictionaries for the next model call.

#### Edge Cases & Error Handling

- Empty or unknown raw payloads return an empty tuple of tool calls.
- Malformed argument JSON creates a `ToolCall` with empty arguments and parse metadata where possible, or is skipped if no tool name exists.
- Provider-specific unsupported shapes are not guessed; tests cover only documented common shapes.

---

### 6.5 Text Runner Per-Call Tool Options

**File(s):** `vidbyte/lib/runners/text.py`, `vidbyte/providers/openai.py`, `vidbyte/providers/anthropic.py`, `vidbyte/providers/gemini.py`, `vidbyte/providers/compatible.py`
**Type:** Modified

#### What it does

Allows the agent to supply tool schemas and evolving message history at call time without exposing runner construction in user docs.

#### Interface / API

```python
class TextModelRunner:
    def run(
        self,
        prompt: str,
        *,
        system: str | None = None,
        metadata: Mapping[str, object] | None = None,
        tools: Iterable[Mapping[str, Any]] = (),
        tool_choice: str | Mapping[str, Any] | None = None,
        messages: Iterable[Mapping[str, Any]] = (),
    ) -> TextModelResponse: ...
```

#### Logic / Algorithm

1. Preserve existing `run(prompt, system=..., metadata=...)` compatibility.
2. Use `dataclasses.replace(...)` on the runner's `TextModelConfig` to add per-call `tools`, `tool_choice`, `messages`, and metadata.
3. Pass that temporary config into the existing provider call.
4. Provider response extractors return empty text instead of raising when the raw payload contains provider-native tool calls.
5. Final text responses keep current normalization.

#### Edge Cases & Error Handling

- Existing tests that call `TextModelRunner.run("Say OK")` remain valid.
- Tool-call-only responses do not become final answers; the agent loop inspects raw payloads first.
- Provider configuration and API key validation remain unchanged.

---

### 6.6 Agent Tool Loop

**File(s):** `vidbyte/agents/base.py`, `vidbyte/agents/mixins.py`, `vidbyte/agents/__init__.py`
**Type:** Modified

#### What it does

Makes `BaseAgent` the owner of tool injection, provider schema formatting, local tool execution, and tool-call context.

#### Interface / API

```python
class BaseAgent:
    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        runner: object | None = None,
        tools: Sequence[object] | Tools = (),
        permission_policy: PermissionPolicy | None = None,
        max_tool_rounds: int = 3,
        ...
    ) -> None: ...

    async def arun(self, message: str, **options: Any) -> AgentMessage: ...
    def run(self, message: str, **options: Any) -> AgentMessage: ...

Agent = BaseAgent
```

#### Logic / Algorithm

1. Normalize constructor tools to a `Tools` catalog.
2. Store `permission_policy` with the same default as current `ToolExecutor`.
3. Keep `self.tools` sequence-compatible for existing `len(agent.tools)` and `agent.tools[0]` tests.
4. `add_tool(...)` replaces `self.tools` with `self.tools.add(tool)`.
5. MCP mixin uses `add_tool(...)` when present; fallback behavior remains for non-agent classes that expose a mutable list.
6. `generate_reply(...)` builds context with existing history and prior tool context.
7. If a strategy is configured, preserve current strategy flow and pass `tools=self.tools.all()` for compatibility.
8. If no strategy is configured, direct runner execution enters `_run_with_tools(...)`.
9. `_run_with_tools(...)` formats schemas with `ToolsFormatter.format_tools(...)`.
10. It calls the runner with `tools=...`, `messages=...`, and existing `system` options when supported.
11. It parses raw tool calls from runner results.
12. For each call, it resolves the tool from `Tools`, applies permission policy, validates arguments, executes the tool, and records `ToolCallContext`.
13. It formats tool results into provider message history and repeats until no tool calls appear or `max_tool_rounds` is reached.
14. If max rounds are exhausted, return an `AgentMessage` with an explanatory error-style final content and metadata noting truncation.
15. Final reply metadata includes `strategy`, `tool_call_count`, and `tool_call_states`.

#### Edge Cases & Error Handling

- Runners that do not accept `tools` or `messages` fall back to current `_call_runner_once(...)` behavior using signature inspection or caught `TypeError` only when safe.
- Missing runner without strategy keeps raising `AgentExecutionError`.
- Unknown tool names are converted into tool result messages for the model instead of raising.
- Tool execution exceptions become failed `ToolResult` records.
- Tool loops are not run for image/video runners in this PR.

---

### 6.7 Compatibility Executor

**File(s):** `vidbyte/tools/executor.py`, `tests/test_tool_core.py`, `tests/test_security_executor.py`
**Type:** Modified

#### What it does

Keeps old `ToolExecutor` behavior working while allowing it to depend on `Tools` rather than a separate registry implementation.

#### Interface / API

```python
class ToolExecutor:
    def __init__(self, registry: ToolRegistry | Tools, *, permission_policy: PermissionPolicy | None = None) -> None: ...
    async def execute_call(self, call: ToolCall) -> ToolResult: ...
    async def execute(self, text: str) -> ToolResult: ...
```

#### Logic / Algorithm

1. Accept either `ToolRegistry` or `Tools`.
2. Resolve tools through `get(...)` when available or private `Tools._get(...)`.
3. Keep permission and validation behavior unchanged.
4. Improve invalid `Action Input` handling only if tests are updated to expect it.

#### Edge Cases & Error Handling

- Existing tests for denied WRITE tools continue to pass.
- Compatibility executor remains undocumented in new README examples.

---

### 6.8 Public Documentation And SDK Skill

**File(s):** `README.md`, `skills/vidbyte-sdk/SKILL.md`, `docs/design/advanced-tool-ecosystem.md`, `docs/design/custom-function-tools.md`
**Type:** Modified

#### What it does

Updates the public mental model and contributor guidance.

#### Interface / API

```python
from vidbyte import Agent, tool
from vidbyte.tools import Tools

@tool
def lookup(topic: str) -> str:
    """Look up a topic."""
    return topic

agent = Agent(name="worker", system_prompt="Use tools when needed.", runner=my_runner, tools=[lookup])
```

#### Logic / Algorithm

1. README replaces `sdk.tools.register(...)` examples with agent-local tools.
2. README describes `Tools(...)` as a catalog/inspection helper.
3. README marks `ToolRegistry` and `ToolExecutor` as compatibility/advanced internals if mentioned at all.
4. README avoids direct construction examples for `TextModelRunner`, `ImageModelRunner`, and `VideoModelRunner`.
5. SDK skill guidance changes from registry/executor-first to agent-injected tools.
6. Existing design docs are amended only where they would otherwise contradict the new approved direction.

#### Edge Cases & Error Handling

- Documentation examples must not include real API keys.
- Internal architecture docs may still mention runner classes and compatibility wrappers, but they must not present them as the preferred user entry point.

---

### 6.9 Tests

**File(s):** `tests/test_tools_catalog.py`, `tests/test_agent_tool_loop.py`, existing tool/provider/agent tests
**Type:** New file, Modified

#### What it does

Adds focused coverage for the new public API and the agent-owned tool loop.

#### Interface / API

```python
class ToolsCatalogTests(unittest.TestCase): ...
class AgentToolLoopTests(unittest.IsolatedAsyncioTestCase): ...
```

#### Logic / Algorithm

1. Test `@tool` and `@vidbyte_tool` both produce equivalent `FunctionTool` objects.
2. Test `Tools([...]).specs()`, `.describe()`, `.provider_schemas(...)`, `.names()`, indexing, and duplicate rejection.
3. Test compatibility `ToolRegistry` still supports `register(...)` and `get(...)`.
4. Test `BaseAgent(..., tools=[...])` exposes tool names in `card()`.
5. Test direct runner tool loop with a fake OpenAI-style raw response requesting a tool, followed by final text.
6. Test unknown tool call records failed context and sends an error result back to the fake runner.
7. Test WRITE tool denial does not execute and records denied context.
8. Test strategy path still receives tools.
9. Test `ToolsFormatter.parse_tool_calls(...)` for OpenAI Responses, OpenAI-compatible chat, Anthropic, and Gemini canned payloads.
10. Run existing full unittest suite to catch public export regressions.

#### Edge Cases & Error Handling

- Tests use fake runners only.
- Tests assert bounded max tool rounds.
- Tests do not depend on live provider SDKs or network access.

---

## 7. Data Model Changes

### 7.1 `ToolCallState`

**Change type:** New

```python
class ToolCallState(str, Enum):
    REQUESTED = "requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"
```

**Migration strategy:** N/A - in-memory SDK enum only.

- Forward migration: agent tool loops use this enum in `ToolCallContext`.
- Rollback plan: remove the enum and keep older `ToolCall` / `ToolResult` only.

### 7.2 `ToolCallContext`

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class ToolCallContext:
    tool_name: str
    arguments: Mapping[str, Any]
    state: ToolCallState
    call_id: str | None
    result: ToolResult | None
    provider: str | None
    model: str | None
    metadata: Mapping[str, Any]
```

**Migration strategy:** N/A - in-memory SDK dataclass only.

- Forward migration: `BaseAgentContext.tool_calls` may contain these context records.
- Rollback plan: reply metadata can return to simple counts without preserving structured records.

### 7.3 `Tools`

**Change type:** New

```python
class Tools(Sequence[BaseTool]):
    ...
```

**Migration strategy:** Existing `ToolRegistry` remains a compatibility wrapper. New code should use `Tools` or pass tools directly into agents.

---

## 8. API Changes

N/A - this SDK change does not add HTTP endpoints. It modifies Python package APIs.

### 8.1 Python SDK API: Tool Creation

**Change type:** Modified

**Request:**

```python
from vidbyte import tool

@tool
def lookup(topic: str) -> str:
    """Look up a topic."""
    return topic
```

**Response:**

```python
lookup.spec().name == "lookup"
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Unsupported callable signatures raise `TypeError`. |
| N/A | Invalid runtime arguments return `ToolResult.error(...)`. |

### 8.2 Python SDK API: Tool Catalog

**Change type:** New

**Request:**

```python
from vidbyte.tools import Tools

catalog = Tools([lookup])
schemas = catalog.provider_schemas("openai")
description = catalog.describe()
```

**Response:**

```python
tuple[dict, ...]
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Duplicate tool names raise `ToolRegistrationError`. |
| N/A | Invalid tool objects raise `TypeError`. |

### 8.3 Python SDK API: Agent Tool Injection

**Change type:** Modified

**Request:**

```python
from vidbyte import Agent

agent = Agent(
    name="worker",
    system_prompt="Use tools when useful.",
    runner=my_runner,
    tools=[lookup],
)
reply = await agent.arun("Use lookup if needed.")
```

**Response:**

```python
AgentMessage(
    content="...",
    metadata={
        "strategy": "direct_runner",
        "tool_call_count": 1,
        "tool_call_states": ("succeeded",),
    },
)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Missing runner without strategy raises `AgentExecutionError`. |
| N/A | Max tool rounds reached returns a bounded final response with metadata. |
| N/A | Tool execution failures are recorded and returned to the model as tool results. |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agent-tool-api-consolidation.md` | Design doc for this feature |
| CREATE | `vidbyte/tools/catalog.py` | New public `Tools` catalog replacing registry-first guidance |
| CREATE | `tests/test_tools_catalog.py` | Tests for `Tools`, `@tool`, provider schemas, and compatibility behavior |
| CREATE | `tests/test_agent_tool_loop.py` | Tests for agent-owned provider-native tool execution and context |
| MODIFY | `README.md` | Document agent-local tools, `@tool`, `Tools`, and runner/docs boundary |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Update contributor guidance for agent-injected tools and compatibility wrappers |
| MODIFY | `docs/design/advanced-tool-ecosystem.md` | Mark registry/executor as compatibility/internal after this consolidation |
| MODIFY | `docs/design/custom-function-tools.md` | Update decorator name and agent-local tool guidance |
| MODIFY | `vidbyte/__init__.py` | Export `Agent`, `tool`, `Tools`, and tool context contracts |
| MODIFY | `vidbyte/agents/__init__.py` | Export ergonomic `Agent` alias if added |
| MODIFY | `vidbyte/agents/base.py` | Normalize tools into `Tools`, add direct tool loop, tool context, and run aliases |
| MODIFY | `vidbyte/agents/mixins.py` | Add MCP tools through agent-compatible tool APIs |
| MODIFY | `vidbyte/lib/dataclasses/tools.py` | Add `ToolCallState` and `ToolCallContext` |
| MODIFY | `vidbyte/lib/dataclasses/context.py` | Accept structured tool-call context in agent contexts if typing needs adjustment |
| MODIFY | `vidbyte/lib/tools/formatter.py` | Add catalog formatting, provider-family detection, tool-call parsing, and result message formatting |
| MODIFY | `vidbyte/lib/runners/text.py` | Accept per-call tool schemas, tool choice, messages, and metadata |
| MODIFY | `vidbyte/providers/base.py` | Delegate provider schema translation to `ToolsFormatter` behavior where possible |
| MODIFY | `vidbyte/providers/openai.py` | Preserve tool-call-only responses without requiring final text |
| MODIFY | `vidbyte/providers/anthropic.py` | Preserve tool-call-only responses without requiring final text |
| MODIFY | `vidbyte/providers/gemini.py` | Preserve tool-call-only responses without requiring final text |
| MODIFY | `vidbyte/providers/compatible.py` | Preserve tool-call-only responses without requiring final text |
| MODIFY | `vidbyte/tools/__init__.py` | Export `Tools`, `tool`, and context contracts; keep compatibility exports |
| MODIFY | `vidbyte/tools/adapters.py` | Accept nested `Tools` where useful and keep callable normalization centralized |
| MODIFY | `vidbyte/tools/client.py` | Prefer `Tools` catalog while preserving `registry` / `executor` compatibility |
| MODIFY | `vidbyte/tools/decorators.py` | Rename primary decorator to `tool` and keep `vidbyte_tool` alias |
| MODIFY | `vidbyte/tools/executor.py` | Accept `Tools` and keep old executor behavior as compatibility |
| MODIFY | `vidbyte/tools/registry.py` | Make `ToolRegistry` a compatibility wrapper around `Tools` |
| MODIFY | `vidbyte/tools/types.py` | Re-export new tool context dataclasses |
| MODIFY | `tests/test_agent_base.py` | Update expectations for `Tools` sequence behavior and metadata if needed |
| MODIFY | `tests/test_custom_function_tools.py` | Add `@tool` coverage while keeping `vidbyte_tool` compatibility |
| MODIFY | `tests/test_mcp_attachment.py` | Update expectations if `agent.tools` becomes `Tools` sequence-compatible |
| MODIFY | `tests/test_provider_tool_schema_translation.py` | Cover `ToolsFormatter` and catalog schema paths |
| MODIFY | `tests/test_security_executor.py` | Ensure compatibility executor behavior still passes with `Tools` |
| MODIFY | `tests/test_tool_core.py` | Update registry/executor tests for compatibility wrapper |
| MODIFY | `tests/test_tool_registry_custom_inputs.py` | Keep old registry tests or migrate assertions to compatibility semantics |
| MODIFY | `tests/test_tool_mixin.py` | Adjust mixin tests if it stores `Tools` catalogs |

Summary: 4 files created, 32 files modified, 0 files deleted.

---

## 10. Testing Plan

### Unit Tests

- `tests/test_tools_catalog.py` -> `test_tool_decorator_alias_matches_vidbyte_tool`: verifies both decorators create equivalent `FunctionTool` objects.
- `tests/test_tools_catalog.py` -> `test_catalog_describes_specs_and_names`: verifies `Tools.specs()`, `names()`, indexing, and `describe()`.
- `tests/test_tools_catalog.py` -> `test_catalog_rejects_duplicate_names`: duplicate names raise `ToolRegistrationError`.
- `tests/test_tools_catalog.py` -> `test_catalog_formats_provider_schemas`: OpenAI, Anthropic, Gemini, and xAI-compatible schemas are generated from one catalog.
- `tests/test_tools_catalog.py` -> `test_tool_registry_compatibility`: old `ToolRegistry.register(...)`, `get(...)`, and `specs_as_prompt_str()` keep working.
- `tests/test_agent_tool_loop.py` -> `test_agent_executes_openai_response_tool_call_then_final_answer`: fake runner returns one OpenAI Responses tool call, agent executes local tool, second runner call returns final text.
- `tests/test_agent_tool_loop.py` -> `test_agent_records_unknown_tool_failure_context`: unknown tool call becomes failed `ToolCallContext`.
- `tests/test_agent_tool_loop.py` -> `test_agent_denies_write_tool_by_default`: denied WRITE tool does not execute.
- `tests/test_agent_tool_loop.py` -> `test_agent_stops_at_max_tool_rounds`: repeated fake tool calls stop at the configured bound.
- `tests/test_agent_tool_loop.py` -> `test_strategy_path_still_receives_tools`: strategy flow remains compatible.
- `tests/test_provider_tool_schema_translation.py` -> parse canned tool calls for OpenAI Responses, OpenAI-compatible chat, Anthropic, and Gemini.
- Existing `test_security_executor.py`, `test_tool_core.py`, `test_tool_registry_custom_inputs.py`, and `test_custom_function_tools.py` continue to verify compatibility paths.

### Integration Tests

- Run the full standard library unittest suite because root exports, agent execution, provider formatting, and MCP tool attachment are all touched.
- Use only fake runners/transports and temporary local tools.
- No live provider, MCP subprocess, or network integration is required.

### Manual / QA Test Cases

1. Run `python -m compileall vidbyte`.
2. Run `python -m unittest discover -s tests`.
3. Run `python -c "from vidbyte import Agent, Tools, tool; print(Agent.__name__, Tools.__name__, callable(tool))"`.
4. Run a small fake-runner script where the first model response requests a decorated `lookup` tool and the second returns final text.
5. Search docs for old public patterns:

```bash
rg "sdk\\.tools\\.register|ToolRegistry\\(|ToolExecutor\\(|TextModelRunner\\(|ImageModelRunner\\(|VideoModelRunner\\(" README.md skills docs
```

Remaining matches should be compatibility notes or internal architecture references, not recommended quickstart examples.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python | `>=3.11` | SDK runtime and tests | Existing requirement |
| setuptools | `>=68` | Build backend | Existing requirement |
| pydantic | `>=2,<3` | Existing function-tool validation and JSON Schema generation | No new dependency risk |
| OpenAI/Anthropic/Gemini/xAI APIs | Existing provider adapters only | Shape compatibility for tool schemas and canned raw payload parsing | No live calls in tests; raw shapes may need future provider updates |

No new package dependencies or external services are introduced.

---

## 12. Rollout & Deployment

- This is a package-only SDK change.
- It is intended to be backward-compatible for existing imports, while changing the recommended public mental model.
- No feature flags are needed.
- Rollout sequence:
  1. Commit this design doc first in the approved worktree.
  2. Implement `Tools` and decorator rename with compatibility aliases.
  3. Add tool context dataclasses and formatter expansion.
  4. Add text-runner per-call tool options.
  5. Add the direct `BaseAgent` tool loop and MCP attachment adjustments.
  6. Update docs and SDK skill guidance.
  7. Add and update tests.
  8. Run compile and unittest verification.
- Rollback procedure:
  1. Revert the feature branch merge commit.
  2. Restore README and skill guidance to the prior registry/executor examples.
  3. Remove new `Tools` and agent tool-loop tests.
  4. Keep existing registry/executor files untouched if a partial rollback is needed.

---

## 13. Open Questions

- [ ] Should `Agent = BaseAgent` be added at root for ergonomics, or should docs continue to use `BaseAgent` only?
- [ ] Should `Tools.add(...)` be public if the class is primarily instructional, or should mutation-like behavior exist only on compatibility `ToolRegistry` and agent methods?
- [ ] Should `ToolCall` itself gain `call_id` and metadata, or should provider call ids live only in `ToolCallContext`?
- [ ] Should tool result messages target OpenAI Responses format first, or OpenAI-compatible chat format first when the provider is ambiguous?
- [ ] Should direct strategy execution eventually reuse the agent tool loop, or should this PR keep strategies compatibility-only?
- [ ] Before Phase 3, how should the existing untracked design docs be handled if `git pull origin main` refuses to proceed?

---

## 14. Alternatives Considered

### Alternative 1: Delete `ToolRegistry` And `ToolExecutor`

- What: Remove both classes from exports and source so only `Tools` and agents remain.
- Why rejected: Existing tests and likely downstream code import them. Keeping compatibility wrappers lets the SDK change public guidance without turning this into a large breaking change.

### Alternative 2: Make `Tools` Purely A String Renderer

- What: Let `Tools` only render descriptions and schemas, while the agent stores a separate private lookup dictionary.
- Why rejected: That duplicates state and risks schema/execution drift. The better compromise is a catalog whose public methods are descriptive while the agent uses private lookup internally.

### Alternative 3: Keep Tool Execution In Strategies

- What: Continue having ReAct/CodeAct parse action text and execute tools, leaving `BaseAgent` as a pass-through.
- Why rejected: The requested SDK paradigm is that users give tools to the agent and the agent decides whether to use them. Provider-native tool calling also belongs closer to model execution than to individual prompt strategies.

### Alternative 4: Implement Full Modality Routing In The Same PR

- What: Combine this tool API consolidation with `BaseAgent` text/image/video modality routing.
- Why rejected: That is already captured in `docs/design/agent-modality-routing.md` and touches runner selection broadly. Combining it with provider-native tool loops would make one PR too wide and harder to verify.

### Alternative 5: Provider-Native Tool Calling Only

- What: Do not support local ReAct-style compatibility or old executor parsing; only send schemas to providers and parse provider-native calls.
- Why rejected: The current SDK already has local tools, strategies, and tests around action-block execution. Compatibility matters while the public API migrates to agent-owned tools.
