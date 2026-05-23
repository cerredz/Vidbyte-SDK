# Design Doc: Agent and Strategy `as_tool()` Wrappers

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-23
**Last Updated:** 2026-05-23

---

## 1. Overview

This feature adds `as_tool()` methods to `BaseAgent` and `BaseStrategy`, enabling any configured agent or strategy to be exposed as a first-class `BaseTool` and registered into another agent's `Tools` catalog. `AgentTool` wraps the full agent lifecycle (`generate_reply()`), while `StrategyTool` wraps the strategy pipeline directly (`strategy.arun()`), bypassing agent-level concerns. The two classes share the same `BaseTool` contract but differ in input schema and execution depth, making them composable building blocks for multi-agent systems.

---

## 2. Goals & Non-Goals

### Goals
- Implement `AgentTool(BaseTool)` that wraps a `BaseAgent` and exposes it as a tool with input `{message, recipient?, modality?}` — mirroring `generate_reply()`'s serializable parameters.
- Implement `StrategyTool(BaseTool)` that wraps a `BaseAgent` with a strategy and exposes the strategy pipeline with input `{prompt}` only — mirroring `strategy.arun()`'s natural interface.
- Add `BaseAgent.as_tool()` returning an `AgentTool` for the calling agent instance.
- Add `BaseStrategy.as_tool(agent)` returning a `StrategyTool` bound to the given agent's runner and tools.
- Add `description: ClassVar[str]` to `BaseStrategy` so strategies can self-describe in tool specs.
- Guarantee invocation isolation: each `AgentTool.execute()` call `fork()`s a fresh agent so history never leaks across tool calls.
- Export `AgentTool` and `StrategyTool` from `vidbyte/tools/__init__.py`.

### Non-Goals
- `HarnessClient.as_tool()` — the harness has no execution interface yet; this is deferred.
- Context propagation (run_id, permissions, StrategyContext) from outer agent to inner agent through the tool call boundary.
- Cycle detection for recursive agent-as-tool compositions.
- MCP server forwarding across forked agents.
- Provider-override parameter on `as_tool()` — provider is already baked into the agent's `runner_config` at construction time.

---

## 3. Background & Context

The SDK's `Tools` catalog (`vidbyte/tools/catalog.py`) accepts any `BaseTool` and emits provider-native schemas. `BaseAgent` already participates as a tool *consumer*, but there is no mechanism for an agent to act as a tool *provider*. Agents and strategies are configured, stateful, async executors — structurally identical to what the tool interface demands. Exposing them as `BaseTool` instances allows parent agents to invoke sub-agents through the standard tool-call flow, enabling multi-agent delegation without any custom orchestration plumbing.

The two tool classes serve different granularity needs:
- **`AgentTool`**: uses the full agent lifecycle — history isolation via `fork()`, MCP connection, modality detection, permission policy, tool rounds. Input uses agent terminology (`message`).
- **`StrategyTool`**: uses the strategy pipeline only — no history, no MCP, no modality detection. Input uses strategy terminology (`prompt`). Useful when only the reasoning step matters, not the full agent actor.

---

## 4. Requirements

### Functional Requirements
1. `AgentTool` must implement `spec()` returning a `ToolSpec` with `name` = agent name, `description` = agent description, and three parameters: `message` (required string), `recipient` (optional string, default `"orchestrator"`), `modality` (optional string, default `"auto"`).
2. `AgentTool.execute(call)` must call `self._agent.fork().generate_reply(message, recipient=recipient, modality=modality_or_none)` and return `ToolResult.success` with `reply.content` as output.
3. `AgentTool.execute(call)` must return `ToolResult.failure` (not raise) on any exception from the inner agent.
4. `StrategyTool` must implement `spec()` returning a `ToolSpec` with one parameter: `prompt` (required string).
5. `StrategyTool.__init__` must raise `AgentExecutionError` if the agent has no strategy (`agent.strategy is None`).
6. `StrategyTool.execute(call)` must call `agent.strategy.arun(prompt, runner=resolved_runner, tools=agent._agent_tool_items)` and return `ToolResult.success` with `result.output`.
7. `StrategyTool.execute(call)` must return `ToolResult.failure` on any exception.
8. `BaseAgent.as_tool(*, name=None, description=None)` must return an `AgentTool` wrapping `self`.
9. `BaseStrategy.as_tool(agent, *, name=None, description=None)` must return a `StrategyTool` wrapping `agent`.
10. Both `as_tool()` methods must use lazy imports to avoid circular import issues.
11. Both tool classes must be importable from `vidbyte.tools`.

### Non-Functional Requirements
- No runtime circular imports introduced.
- No existing tests broken.
- All new code passes `pyproject.toml`-configured linters (ruff/mypy if configured).
- Lazy imports used in `as_tool()` methods on `BaseAgent` and `BaseStrategy` to avoid import-time side effects.

---

## 5. High-Level Design

`AgentTool` and `StrategyTool` are two new `BaseTool` subclasses living in `vidbyte/tools/`. Each wraps a `BaseAgent` reference. The key architectural decision is that both tools are instances wrapping a pre-configured agent — they are not factories that construct agents from scratch on each call.

**`AgentTool`** calls `generate_reply()` through a `fork()` of the backing agent, which runs the complete agent lifecycle: system prompt, MCP connection, strategy (if any), tool rounds, modality detection, and permission checks. The fork ensures history isolation — each tool invocation gets a clean agent state. Output is `AgentMessage.content`.

**`StrategyTool`** calls `strategy.arun()` directly on the agent's strategy, bypassing history, MCP, modality detection, and permission policy. It resolves the runner via the agent's `_runner_for_modality(ModelModality.TEXT)` at `execute()` time, passing the agent's tool items to the strategy. Output is `StrategyResult.output`.

The `as_tool()` methods use lazy imports (`from vidbyte.tools.agent_tool import AgentTool` inside the function body) to break what would otherwise be a circular import chain: `vidbyte.tools.__init__` → `agent_tool.py` → `vidbyte.agents.base` → `vidbyte.tools.catalog` (already cached). This is safe but using lazy imports in the method bodies is cleaner.

```
Parent Agent
  │
  │  tool_call("child_agent_tool", {"message": "..."})
  ▼
AgentTool.execute()
  │
  │  agent.fork().generate_reply(message, ...)
  ▼
Forked Child Agent
  │  (full lifecycle: MCP, strategy, tools, permission)
  ▼
AgentMessage.content  →  ToolResult.success(output=content)

---

Parent Agent
  │
  │  tool_call("child_strategy_tool", {"prompt": "..."})
  ▼
StrategyTool.execute()
  │
  │  agent.strategy.arun(prompt, runner=resolved, tools=...)
  ▼
StrategyResult.output  →  ToolResult.success(output=output)
```

---

## 6. Detailed Design

### 6.1 `AgentTool`

**File:** `vidbyte/tools/agent_tool.py`
**Type:** New file

#### What it does
Wraps a `BaseAgent` instance as a `BaseTool`. Exposes the agent's full execution lifecycle as a tool call, using `fork()` for invocation isolation.

#### Interface / API
```python
class AgentTool(BaseTool):
    def __init__(
        self,
        agent: BaseAgent,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> None: ...

    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
```

Tool call parameters (exposed in `ToolSpec`):

| Parameter | Type | Required | Default | Mapping |
|-----------|------|----------|---------|---------|
| `message` | string | yes | — | `generate_reply(message=...)` |
| `recipient` | string | no | `"orchestrator"` | `generate_reply(recipient=...)` |
| `modality` | string | no | `"auto"` | `generate_reply(modality=...)`, `None` when `"auto"` |

#### Logic / Algorithm
1. `__init__`: store agent ref; resolve `name` (arg or `agent.name`), `description` (arg or `agent.description`); build `ToolSpec` with the three parameters above.
2. `spec()`: return the pre-built `ToolSpec`.
3. `execute(call)`:
   a. Extract `message = str(call.arguments["message"])`.
   b. Extract `recipient = str(call.arguments.get("recipient", "orchestrator"))`.
   c. Extract `modality_raw = call.arguments.get("modality", "auto")`; resolve to `None` if `"auto"` or falsy (lets agent use its configured default).
   d. Call `await self._agent.fork().generate_reply(message, recipient=recipient, modality=modality_or_none)`.
   e. Return `ToolResult.success(self._name, reply.content, metadata={...})`.
   f. On any exception: return `ToolResult.failure(self._name, str(exc), metadata={"error_type": type(exc).__name__})`.

#### Edge Cases & Error Handling
- Agent with no runner: `generate_reply()` will raise `AgentExecutionError`; caught and returned as `ToolResult.failure`.
- Agent with `ConfiguredAgentRunner` only: same — failure at `generate_reply()` time.
- MCP servers: `fork()` does not copy MCP handles; inner agent will re-connect if `_pending_mcp_configs` are present. Accepted limitation — documented in non-goals.
- `modality="auto"` is translated to `None` so the forked agent uses its own configured default.

---

### 6.2 `StrategyTool`

**File:** `vidbyte/tools/strategy_tool.py`
**Type:** New file

#### What it does
Wraps a `BaseAgent`'s strategy as a `BaseTool`. Bypasses the full agent lifecycle and calls the strategy's `arun()` directly with the agent's runner and tools.

#### Interface / API
```python
class StrategyTool(BaseTool):
    def __init__(
        self,
        agent: BaseAgent,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> None: ...

    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
```

Tool call parameters (exposed in `ToolSpec`):

| Parameter | Type | Required | Default | Mapping |
|-----------|------|----------|---------|---------|
| `prompt` | string | yes | — | `strategy.arun(prompt=...)` |

#### Logic / Algorithm
1. `__init__`:
   a. Raise `AgentExecutionError` if `agent.strategy is None`.
   b. Store `self._agent = agent` and `self._strategy = agent.strategy`.
   c. Resolve `name` (arg, or `f"{agent.name}_strategy"`).
   d. Resolve `description` (arg, then `getattr(agent.strategy, "description", "")`, then `f"Run the {agent.strategy.strategy_name} strategy."` as final fallback).
   e. Build `ToolSpec` with single required `prompt` parameter.
2. `spec()`: return the pre-built `ToolSpec`.
3. `execute(call)`:
   a. Extract `prompt = str(call.arguments["prompt"])`.
   b. Resolve runner: call `self._agent._runner_for_modality(ModelModality.TEXT)`. If result is `None` or is `ConfiguredAgentRunner`, return `ToolResult.failure` immediately.
   c. Call `await self._strategy.arun(prompt, runner=runner, tools=self._agent._agent_tool_items)`.
   d. Return `ToolResult.success(self._name, result.output, metadata={...})`.
   e. On any exception: return `ToolResult.failure(self._name, str(exc), ...)`.

#### Edge Cases & Error Handling
- No strategy: raises `AgentExecutionError` at construction — fast failure, no silent errors at call time.
- No real runner (`ConfiguredAgentRunner` or `None`): returns `ToolResult.failure` at execute time with a clear message.
- Strategy raises `StrategyExecutionError`: caught and returned as `ToolResult.failure`.
- Strategy with its own runner (`self._strategy._runner` set): `_resolve_runner()` inside the strategy will prefer the strategy's own runner — acceptable, the agent's runner is still passed as a fallback.

---

### 6.3 `BaseAgent.as_tool()`

**File:** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does
Instance method returning an `AgentTool` that wraps `self`. Uses a lazy import to avoid circular imports.

#### Interface / API
```python
def as_tool(
    self,
    *,
    name: str | None = None,
    description: str | None = None,
) -> "AgentTool":
    from vidbyte.tools.agent_tool import AgentTool
    return AgentTool(self, name=name, description=description)
```

Added to the `TYPE_CHECKING` block at the top of the file:
```python
if TYPE_CHECKING:
    from vidbyte.tools.agent_tool import AgentTool
```

---

### 6.4 `BaseStrategy.as_tool()`

**File:** `vidbyte/strategies/base.py`
**Type:** Modified

#### What it does
Instance method returning a `StrategyTool` that wraps the calling strategy bound to the given agent. Validates the strategy belongs to the agent (or simply delegates — the `StrategyTool` constructor validates that `agent.strategy is not None`).

#### Interface / API
```python
def as_tool(
    self,
    agent: "BaseAgent",
    *,
    name: str | None = None,
    description: str | None = None,
) -> "StrategyTool":
    from vidbyte.tools.strategy_tool import StrategyTool
    return StrategyTool(agent, name=name, description=description)
```

Also add `description: ClassVar[str] = ""` to `BaseStrategy` so subclasses can self-describe.

Added to the `TYPE_CHECKING` block:
```python
if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent
    from vidbyte.tools.strategy_tool import StrategyTool
```

---

### 6.5 `vidbyte/tools/__init__.py`

**File:** `vidbyte/tools/__init__.py`
**Type:** Modified

Add exports:
```python
from vidbyte.tools.agent_tool import AgentTool
from vidbyte.tools.strategy_tool import StrategyTool
```

And add both to `__all__`.

**Circular import safety:** `vidbyte/agents/base.py` imports directly from `vidbyte.tools.catalog`, `vidbyte.tools.security`, `vidbyte.tools.types` — never from `vidbyte.tools` (the package `__init__`). So when `vidbyte/tools/__init__.py` imports `agent_tool.py` which imports `vidbyte.agents.base`, the chain resolves cleanly because `base.py`'s own imports hit already-cached submodules.

---

## 7. Data Model Changes

N/A — No schema, database, or dataclass changes beyond the `description: ClassVar[str] = ""` class variable on `BaseStrategy`, which is a purely additive, backwards-compatible change.

---

## 8. API Changes

N/A — This feature adds Python class methods and new `BaseTool` subclasses. No HTTP endpoints are added or modified.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/tools/agent_tool.py` | New `AgentTool(BaseTool)` wrapping `BaseAgent` |
| CREATE | `vidbyte/tools/strategy_tool.py` | New `StrategyTool(BaseTool)` wrapping `BaseAgent` + strategy |
| MODIFY | `vidbyte/agents/base.py` | Add `as_tool()` method + `TYPE_CHECKING` guard |
| MODIFY | `vidbyte/strategies/base.py` | Add `description` ClassVar + `as_tool(agent)` method + `TYPE_CHECKING` guard |
| MODIFY | `vidbyte/tools/__init__.py` | Export `AgentTool` and `StrategyTool` |
| CREATE | `tests/test_agent_tool.py` | Unit tests for `AgentTool` and `BaseAgent.as_tool()` |
| CREATE | `tests/test_strategy_tool.py` | Unit tests for `StrategyTool` and `BaseStrategy.as_tool()` |

**Total: 3 new files, 3 modified files.**

---

## 10. Testing Plan

### Unit Tests — `tests/test_agent_tool.py`

All tests use `IsolatedAsyncioTestCase`. A `FakeRunner` returns a simple `text` attribute response without calling any real model API.

- `test_spec_has_correct_name_and_description` — `AgentTool(agent).spec().name` equals `agent.name`; description propagated correctly.
- `test_spec_has_three_parameters` — `spec().parameters` has exactly `message`, `recipient`, `modality`; `message` is required, others are not.
- `test_execute_returns_agent_reply_content` — execute with `{"message": "hello"}` returns `ToolResult` with `status == SUCCESS` and `output == reply.content`.
- `test_execute_passes_recipient_to_generate_reply` — verify `recipient` arg flows through (check `ToolResult.metadata["recipient"]` or agent reply).
- `test_execute_auto_modality_passes_none` — `modality="auto"` is passed as `None` to `generate_reply`.
- `test_execute_returns_failure_on_agent_error` — agent raises; result has `status == ERROR`.
- `test_execute_isolates_history_across_calls` — two sequential execute calls; original agent history unchanged.
- `test_as_tool_returns_agent_tool_instance` — `agent.as_tool()` returns `AgentTool`.
- `test_as_tool_name_override` — `agent.as_tool(name="custom")` produces tool with `spec().name == "custom"`.
- `test_as_tool_description_override` — `agent.as_tool(description="custom desc")` sets description.

### Unit Tests — `tests/test_strategy_tool.py`

- `test_spec_has_single_prompt_parameter` — `StrategyTool(agent).spec().parameters` has exactly one parameter named `prompt`, required.
- `test_spec_name_defaults_to_agent_name_strategy` — `spec().name == f"{agent.name}_strategy"`.
- `test_init_raises_when_agent_has_no_strategy` — `StrategyTool(agent_without_strategy)` raises `AgentExecutionError`.
- `test_execute_returns_strategy_output` — execute with `{"prompt": "hello"}` returns `ToolResult.success` with `output == strategy_result.output`.
- `test_execute_returns_failure_on_strategy_error` — strategy raises; result has `status == ERROR`.
- `test_execute_returns_failure_when_no_runner` — agent with `ConfiguredAgentRunner` only; result has `status == ERROR`.
- `test_as_tool_returns_strategy_tool_instance` — `agent.strategy.as_tool(agent)` returns `StrategyTool`.
- `test_as_tool_name_override` — name override propagated.
- `test_strategy_description_used_in_spec` — `BaseStrategy` with `description = "My desc"` produces spec with that description.

### Manual / QA Test Cases
1. Given a configured parent agent with a real runner, when `child_agent.as_tool()` is added via `parent.add_tool(child_agent.as_tool())`, then the parent can invoke the child agent by name in a tool call round.
2. Given a parent agent, when `child_agent.as_tool()` is called twice with the same child agent, each invocation should produce a `ToolResult` independently without bleeding history from the first call.
3. Given an agent with a `ChainOfThoughtStrategy`, when `agent.strategy.as_tool(agent)` is registered and invoked, the strategy's reasoning pipeline runs and returns the final output.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `vidbyte.agents.base.BaseAgent` | internal | Wrapped by both tool classes | Import order must be respected |
| `vidbyte.tools.base.BaseTool` | internal | Parent class for both tool classes | No risk |
| `vidbyte.lib.enums.ModelModality` | internal | Runner resolution in `StrategyTool` | No risk |
| `vidbyte.lib.errors.AgentExecutionError` | internal | Raised by `StrategyTool.__init__` | No risk |

---

## 12. Rollout & Deployment

- No feature flags required — purely additive.
- No breaking changes: no existing method signatures are modified, only new methods/classes added.
- No migration required.
- Deployment is a standard package release.
- Rollback: remove the 3 new/modified file changes.

---

## 13. Open Questions

- [ ] Should `StrategyTool` validate that `agent.strategy is self` (i.e., the strategy calling `as_tool()` is actually attached to the passed agent)? Current design does not enforce this, allowing any strategy to wrap any agent.
- [ ] Should `AgentTool` include a `metadata: dict` parameter so the outer agent can pass structured context through the tool call boundary? Currently excluded to keep the schema minimal.
- [ ] Should we export `AgentTool` / `StrategyTool` from `vidbyte/agents/__init__.py` and `vidbyte/strategies/__init__.py` as well (for discoverability), or keep them exclusively under `vidbyte.tools`?

---

## 14. Alternatives Considered

### Alternative 1: FunctionTool closure instead of dedicated classes
- **What:** `agent.as_tool()` returns `FunctionTool.from_function(lambda msg: agent.fork().arun(msg), name=agent.name, description=agent.description)`.
- **Why rejected:** Loses type fidelity — can't distinguish `AgentTool` from any other `FunctionTool` in a catalog. Makes introspection and `isinstance()` checks impossible. Closure captures `agent` by reference without making it explicit. The dedicated class is ~20 more lines but the semantics are significantly cleaner.

### Alternative 2: Single `AgentTool` class for both agent and strategy wrapping
- **What:** One class with a `strategy_only: bool` flag to select execution path.
- **Why rejected:** Two meaningfully different input schemas and execution paths warrant two distinct classes. A flag-based dispatch makes `spec()` conditional and confuses callers about which parameters are available.

### Alternative 3: `provider` parameter on `as_tool()`
- **What:** `agent.as_tool(provider="anthropic")` controls inner agent execution provider.
- **Why rejected:** Provider is already baked into `runner_config` at agent construction time. Adding it on `as_tool()` introduces a hidden override that makes behavior unpredictable and produces a non-obvious two-source-of-truth for provider configuration. If a different provider is needed, fork the agent first.

### Alternative 4: Eagerly validate runner in `StrategyTool.__init__`
- **What:** Resolve `_runner_for_modality()` at construction time and raise if no real runner.
- **Why rejected:** `_runner_for_modality()` may have side effects (stores the resolved runner in `agent.runners`). Doing this at construction time on every `as_tool()` call is surprising. Deferred to `execute()` time with a clear `ToolResult.failure` is preferable — the tool can be composed into a catalog without requiring a live runner at registration time.
